import cv2
import time
import base64
import requests
import threading
import serial
import numpy as np
import geocoder
from ultralytics import YOLO

# --- LOCAL IP & HARDWARE CONFIGURATION ---
BACKEND_URL = "http://192.168.137.1:8000/api/edge-trigger"
EDGE_API_KEY = "BLU-GUARD-2026"
LOCATION_NAME = "Live Edge-AI Junction (Laptop Geolocation)"

# Fetch Laptop's Live Location via Network/IP Geolocation
print("🌐 [GEOLOCATION] Fetching laptop's current live location...")
g = geocoder.ip('me')
if g.latlng:
    DEFAULT_LAT, DEFAULT_LNG = g.latlng
    print(f"✅ [GEOLOCATION LOCKED] Latitude: {DEFAULT_LAT}, Longitude: {DEFAULT_LNG}")
else:
    DEFAULT_LAT, DEFAULT_LNG = 10.9601, 79.3845 # Fallback to Kumbakonam
    print(f"⚠️ [GEOLOCATION FALLBACK] Using default sector: {DEFAULT_LAT}, {DEFAULT_LNG}")

live_lat = DEFAULT_LAT
live_lng = DEFAULT_LNG
gps_status = f"LAPTOP LIVE LOC ({live_lat:.4f}, {live_lng:.4f})"

# USB Serial configuration matching Arduino code (115200 baud, COM7)
SERIAL_PORT = 'COM7'
BAUD_RATE = 115200

ser = None
try:
    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0.05)
    ser.dtr = False
    ser.rts = False
    time.sleep(2.5)
    print(f"✅ [HARDWARE CONNECTED] ESP8266 linked on {SERIAL_PORT} @ {BAUD_RATE} baud")
except Exception as e:
    ser = None
    print(f"⚠️ [HARDWARE OFFLINE] Could not open {SERIAL_PORT}: {e}")
    print("💡 Make sure Arduino IDE Serial Monitor is CLOSED!")

# Load YOLOv8 model (Supports all 80 COCO dataset classes by default)
model = YOLO("yolov8n.pt")
CLASS_NAMES = model.names
CONFIDENCE_THRESHOLD = 0.35

# Road hazard classes
HAZARD_CLASSES = {0, 1, 2, 3, 5, 7, 8}

last_sent_cmd = None
last_cmd_time = 0
cloud_sync_banner_until = 0

def send_arduino_command(cmd_char):
    """Send single-character state command ('0', 'B', 'S', 'A') to ESP8266."""
    global last_sent_cmd, last_cmd_time
    now = time.time()
    if ser and ser.is_open and (cmd_char != last_sent_cmd or (now - last_cmd_time) > 1.0):
        try:
            ser.write(cmd_char.encode('utf-8'))
            ser.flush()
            if cmd_char != last_sent_cmd:
                print(f"📡 [SERIAL -> ESP8266]: Sent Mode '{cmd_char}'")
            last_sent_cmd = cmd_char
            last_cmd_time = now
        except Exception as err:
            print(f"❌ Serial write error: {err}")

def read_arduino_gps():
    """Optional GPS reader; keeps serial buffer clear even if GPS has no satellites."""
    global gps_status
    if ser and ser.is_open:
        try:
            while ser.in_waiting > 0:
                line = ser.readline().decode('utf-8', errors='ignore').strip()
                if line.startswith("GPS:") and "SEARCHING" not in line:
                    val = line.split("GPS:")[1]
                    if "," in val:
                        parts = val.split(",")
                        global live_lat, live_lng
                        live_lat = float(parts[0])
                        live_lng = float(parts[1])
                        gps_status = f"GPS LOCKED ({live_lat:.4f}, {live_lng:.4f})"
        except Exception:
            pass

def _async_post_alert(frame_copy, duration_sec, stage_label, detected_summary):
    global cloud_sync_banner_until
    try:
        resized = cv2.resize(frame_copy, (480, 320))
        _, buffer = cv2.imencode('.jpg', resized, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
        img_base64 = base64.b64encode(buffer).decode('utf-8')

        payload = {
            "api_key": EDGE_API_KEY,
            "location_name": LOCATION_NAME,
            "latitude": live_lat,
            "longitude": live_lng,
            "severity": "CRITICAL",
            "notes": f"[{stage_label}] {detected_summary} obstructing zone for {int(duration_sec)}s | Blue Strobe Active",
            "image_base64": f"data:image/jpeg;base64,{img_base64}"
        }

        res = requests.post(BACKEND_URL, json=payload, timeout=10)
        if res.status_code == 200:
            cloud_sync_banner_until = time.time() + 8.0
            print(f"🚨 [CLOUD ALERT DISPATCHED] >45s Strobe Alert synced with Laptop GPS ({live_lat}, {live_lng})! (HTTP {res.status_code})")
        else:
            print(f"⚠️ [SERVER RESPONSE]: HTTP {res.status_code} - {res.text}")
    except Exception as e:
        print(f"❌ [NETWORK ERROR]: Failed to reach {BACKEND_URL} -> {e}")

def push_yolo_alert_nonblocking(frame, duration_sec, stage_label, detected_summary="Object Obstruction"):
    threading.Thread(
        target=_async_post_alert,
        args=(frame.copy(), duration_sec, stage_label, detected_summary),
        daemon=True
    ).start()

def is_box_in_roi(box_xyxy, roi_coords):
    x1, y1, x2, y2 = box_xyxy
    cx = int((x1 + x2) / 2)
    cy = int((y1 + y2) / 2)
    rx1, ry1, rx2, ry2 = roi_coords
    return (rx1 <= cx <= rx2) and (ry1 <= cy <= ry2), (cx, cy)

def main():
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("❌ Error: Could not open webcam.")
        return

    obstruction_start_time = None
    strobe_alert_sent = False
    manual_simulation_mode = False

    print("=========================================================================")
    print("🛡️ BLU Guard AI - YOLOv8 + Laptop Live Geolocation Active")
    print("👉 Controls: [m] Toggle Manual Simulation | [t] Force >45s Alert | [q] Quit")
    print("=========================================================================")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        read_arduino_gps()
        height, width, _ = frame.shape

        rx1, ry1 = int(width * 0.12), int(height * 0.14)
        rx2, ry2 = int(width * 0.88), int(height * 0.88)
        roi_coords = (rx1, ry1, rx2, ry2)

        results = model(frame, verbose=False)[0]
        zone_hazards = []

        for box in results.boxes:
            cls_id = int(box.cls[0])
            conf = float(box.conf[0])
            
            if conf >= CONFIDENCE_THRESHOLD:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                class_name = CLASS_NAMES.get(cls_id, f"ID:{cls_id}").upper()

                in_zone, center_pt = is_box_in_roi((x1, y1, x2, y2), roi_coords)

                if cls_id in HAZARD_CLASSES:
                    if in_zone:
                        zone_hazards.append(class_name)
                        box_color = (0, 0, 255)
                        status_tag = "[HAZARD IN ZONE]"
                    else:
                        box_color = (0, 165, 255)
                        status_tag = "[HAZARD OUTSIDE]"
                else:
                    box_color = (255, 200, 0)
                    status_tag = "[OBJECT]"

                cv2.rectangle(frame, (x1, y1), (x2, y2), box_color, 2)
                cv2.circle(frame, center_pt, 4, box_color, -1)

                label = f"{class_name} {int(conf * 100)}% {status_tag}"
                (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
                cv2.rectangle(frame, (x1, max(y1 - th - 8, 0)), (x1 + tw + 6, y1), box_color, -1)
                cv2.putText(frame, label, (x1 + 3, max(y1 - 5, 12)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        elif key == ord('m'):
            manual_simulation_mode = not manual_simulation_mode
            print(f"🔄 Manual Simulation Mode: {'ON' if manual_simulation_mode else 'OFF'}")
        elif key == ord('t'):
            send_arduino_command('A')
            push_yolo_alert_nonblocking(frame, 46, "FORCED >45s STROBE TEST", "Simulated Obstruction")

        is_obstructed = (len(zone_hazards) > 0) or manual_simulation_mode

        zone_color = (0, 0, 255) if is_obstructed else (0, 255, 255)
        cv2.rectangle(frame, (rx1, ry1), (rx2, ry2), zone_color, 2)
        cv2.putText(frame, f"AI DETECTION ZONE (ROI) | Hazards in Zone: {len(zone_hazards)}",
                    (rx1, ry1 - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.5, zone_color, 2)

        cv2.rectangle(frame, (0, 0), (width, 52), (15, 23, 42), -1)

        if is_obstructed:
            if obstruction_start_time is None:
                obstruction_start_time = time.time()
                strobe_alert_sent = False

            elapsed = time.time() - obstruction_start_time
            detected_summary = ", ".join(set(zone_hazards)) if zone_hazards else "MANUAL SIMULATION"

            if elapsed < 15.0:
                blue_mode_text = "BLINKING ('B') [0-15s]"
                hud_color = (0, 255, 255)
                send_arduino_command('B')
            elif elapsed < 45.0:
                blue_mode_text = "STEADY LOCK ('S') [15-45s]"
                hud_color = (0, 165, 255)
                send_arduino_command('S')
            else:
                blue_mode_text = "EMERGENCY STROBE ('A') [>45s]"
                hud_color = (0, 0, 255)
                send_arduino_command('A')

            cv2.putText(frame, f"TIMER: {elapsed:.1f}s | BLUE LED: {blue_mode_text}",
                        (12, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.55, hud_color, 2)
            cv2.putText(frame, f"HAZARDS: {detected_summary} | LOC: {gps_status}",
                        (12, 44), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 230, 255), 1)

            if elapsed >= 45.0 and not strobe_alert_sent:
                push_yolo_alert_nonblocking(frame, elapsed, "CRITICAL >45s STROBE ESCALATION", detected_summary)
                strobe_alert_sent = True
        else:
            obstruction_start_time = None
            strobe_alert_sent = False
            send_arduino_command('0')
            cv2.putText(frame, f"ZONE CLEAR | LOC: {gps_status} | All Classes Active",
                        (12, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
            cv2.putText(frame, f"Press 'm' to Simulate | Press 't' for Instant Alert",
                        (12, 44), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1)

        if time.time() < cloud_sync_banner_until or strobe_alert_sent:
            cv2.rectangle(frame, (int(width * 0.08), int(height * 0.78)),
                          (int(width * 0.92), int(height * 0.87)), (0, 0, 180), -1)
            cv2.rectangle(frame, (int(width * 0.08), int(height * 0.78)),
                          (int(width * 0.92), int(height * 0.87)), (0, 255, 255), 2)
            cv2.putText(frame, "ALERT SENT TO COMMAND CENTER WITH LAPTOP GPS!",
                        (int(width * 0.11), int(height * 0.835)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)

        cv2.imshow("BLU Guard AI - Live Edge Monitor", frame)

    send_arduino_command('0')
    if ser and ser.is_open:
        ser.close()
    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()