import cv2
import time
import base64
import requests
import threading
import serial
import serial.tools.list_ports
import geocoder
from ultralytics import YOLO

# --- LOCAL IP & HARDWARE CONFIGURATION ---
SERVER_BASE_URL = "http://localhost:8000"
BACKEND_URL = f"{SERVER_BASE_URL}/api/edge-trigger"
LIVE_STREAM_URL = f"{SERVER_BASE_URL}/api/yolo-stream"
SIGNAL_CONTROL_URL = f"{SERVER_BASE_URL}/api/signal-control"
BLOCKADES_API_URL = f"{SERVER_BASE_URL}/blockades/"
EDGE_API_KEY = "BLU-GUARD-2026"

# Explicit Traffic Signal Location Name (Spoken in Voice Alerts & Displayed on UI)
LOCATION_NAME = "Kumbakonam Central Traffic Signal - Pole 04 (Sector 1)"

# Fetch Laptop's Live Location via Network/IP Geolocation
print("🌐 [GEOLOCATION] Fetching laptop's current live location...")
try:
    g = geocoder.ip('me')
    if g.latlng:
        DEFAULT_LAT, DEFAULT_LNG = g.latlng
        print(f"✅ [GEOLOCATION LOCKED] Latitude: {DEFAULT_LAT}, Longitude: {DEFAULT_LNG}")
    else:
        DEFAULT_LAT, DEFAULT_LNG = 10.9601, 79.3845
        print(f"⚠️ [GEOLOCATION FALLBACK] Using default sector: {DEFAULT_LAT}, {DEFAULT_LNG}")
except Exception:
    DEFAULT_LAT, DEFAULT_LNG = 10.9601, 79.3845

live_lat = DEFAULT_LAT
live_lng = DEFAULT_LNG
gps_status = f"LAPTOP LIVE LOC ({live_lat:.4f}, {live_lng:.4f})"

# --- AUTO-DETECT OR CONNECT TO ESP8266 ON COM8 / CH340 / CP210x ---
PREFERRED_PORT = 'COM8'
BAUD_RATE = 115200
serial_lock = threading.Lock()
ser = None


def connect_esp8266_serial():
    global ser
    ports_to_try = [PREFERRED_PORT]
    for p in serial.tools.list_ports.comports():
        if p.device not in ports_to_try:
            ports_to_try.append(p.device)

    for port_name in ports_to_try:
        try:
            s = serial.Serial(port_name, BAUD_RATE, timeout=0.05, write_timeout=0.2)
            s.dtr = False
            s.rts = False
            time.sleep(2.0)
            s.reset_input_buffer()
            ser = s
            print(f"✅ [HARDWARE CONNECTED] ESP8266 linked on {port_name} @ {BAUD_RATE} baud")
            return
        except Exception:
            continue

    ser = None
    print(f"⚠️ [HARDWARE OFFLINE] Could not open {PREFERRED_PORT} (or any COM port).")
    print("💡 Make sure Arduino IDE Serial Monitor is CLOSED and NodeMCU USB is plugged in!")


connect_esp8266_serial()

# Load YOLOv8 model
model = YOLO("yolov8n.pt")
CLASS_NAMES = model.names
CONFIDENCE_THRESHOLD = 0.35

# Road hazard classes (Person, Bicycle, Car, Motorcycle, Bus, Truck, etc.)
HAZARD_CLASSES = {0, 1, 2, 3, 5, 7, 8}

# --- Thread-Safe Hardware & Control Room Sync State ---
last_sent_ai_cmd = None
last_sent_sig_cmd = None
last_ai_keepalive = 0.0
last_sig_keepalive = 0.0

remote_traffic_light = "C"     # 'C' = Auto Cycle, 'R' = Red, 'Y' = Yellow, 'G' = Green (108 Corridor)
remote_blue_override = "AUTO"  # 'AUTO' = YOLO Controlled, or manual '0', 'B', 'S', 'A'
last_control_version = -1

cloud_sync_banner_until = 0.0
last_live_stream_time = 0.0
stop_threads = False


def send_arduino_ai_command(cmd_char, force=False):
    """Thread-safe sender for Blue AI Strobe Pin D3 ('0', 'B', 'S', 'A')."""
    global last_sent_ai_cmd, last_ai_keepalive
    if cmd_char not in ('0', 'B', 'S', 'A'):
        return
    now = time.time()
    if ser and ser.is_open and (force or cmd_char != last_sent_ai_cmd or (now - last_ai_keepalive) > 1.5):
        with serial_lock:
            try:
                ser.write(cmd_char.encode('utf-8'))
                ser.flush()
                if force or cmd_char != last_sent_ai_cmd:
                    print(f"🔵 [SERIAL -> ESP8266 BLUE AI (D3)]: Sent '{cmd_char}'")
                last_sent_ai_cmd = cmd_char
                last_ai_keepalive = now
            except Exception as err:
                print(f"❌ Serial Blue AI write error: {err}")


def send_arduino_signal_command(sig_char, force=False):
    """Thread-safe sender for Traffic Light Pins D5/D2/D7 ('R', 'Y', 'G', 'C')."""
    global last_sent_sig_cmd, last_sig_keepalive
    if sig_char not in ('R', 'Y', 'G', 'C'):
        return
    now = time.time()
    if ser and ser.is_open and (force or sig_char != last_sent_sig_cmd or (now - last_sig_keepalive) > 1.5):
        with serial_lock:
            try:
                ser.write(sig_char.encode('utf-8'))
                ser.flush()
                if force or sig_char != last_sent_sig_cmd:
                    phase_names = {'R': 'RED LOCK', 'Y': 'YELLOW CAUTION', 'G': 'GREEN / 108 CORRIDOR', 'C': 'AUTO CYCLE'}
                    print(f"🚦 [SERIAL -> ESP8266 TRAFFIC LIGHT]: Sent '{sig_char}' ({phase_names.get(sig_char)})")
                last_sent_sig_cmd = sig_char
                last_sig_keepalive = now
            except Exception as err:
                print(f"❌ Serial Traffic Light write error: {err}")


def read_arduino_serial_feedback():
    """Reads GPS data & hardware state confirmations from ESP8266 without blocking."""
    global gps_status, live_lat, live_lng
    if ser and ser.is_open:
        with serial_lock:
            try:
                while ser.in_waiting > 0:
                    line = ser.readline().decode('utf-8', errors='ignore').strip()
                    if line.startswith("GPS:") and "SEARCHING" not in line:
                        val = line.split("GPS:")[1]
                        if "," in val:
                            parts = val.split(",")
                            live_lat = float(parts[0])
                            live_lng = float(parts[1])
                            gps_status = f"GPS LOCKED ({live_lat:.4f}, {live_lng:.4f})"
                    elif line.startswith("ACK:"):
                        print(f"⚡ [ESP8266 HARDWARE ACK]: {line}")
            except Exception:
                pass


def control_room_sync_worker():
    """
    Dedicated background thread that polls FastAPI Control Room every 250ms.
    Whenever you click Red, Yellow, Green, Auto, or Blue Blink/Steady/Strobe on the website,
    this thread immediately pushes the byte to the ESP8266 with zero camera lag.
    """
    global remote_traffic_light, remote_blue_override, last_control_version
    session = requests.Session()
    while not stop_threads:
        try:
            res = session.get(SIGNAL_CONTROL_URL, timeout=0.4)
            if res.status_code == 200:
                data = res.json()
                ver = data.get("version", 0)
                t_light = data.get("traffic_light", "C")
                b_mode = data.get("blue_mode", "AUTO")

                version_changed = (ver != last_control_version)
                last_control_version = ver
                remote_traffic_light = t_light
                remote_blue_override = b_mode

                # Immediately transmit Traffic Signal phase ('R', 'Y', 'G', 'C') to ESP8266
                send_arduino_signal_command(remote_traffic_light, force=version_changed)

                # If Control Room manually selected a Blue AI Lamp mode ('0', 'B', 'S', 'A'), send immediately
                if remote_blue_override in ('0', 'B', 'S', 'A') and version_changed:
                    send_arduino_ai_command(remote_blue_override, force=True)
        except Exception:
            pass
        time.sleep(0.25)


def push_live_yolo_visuals(frame_copy, stage_text, timer_sec, hazard_count, hazards_summary, blue_code):
    """Streams live annotated YOLOv8 visuals to FastAPI every ~350ms for Website & Mobile App."""
    global last_live_stream_time
    now = time.time()
    if now - last_live_stream_time < 0.35:
        return
    last_live_stream_time = now

    def _stream_worker():
        try:
            small = cv2.resize(frame_copy, (480, 270))
            _, buffer = cv2.imencode('.jpg', small, [int(cv2.IMWRITE_JPEG_QUALITY), 60])
            b64_frame = base64.b64encode(buffer).decode('utf-8')
            payload = {
                "api_key": EDGE_API_KEY,
                "frame": f"data:image/jpeg;base64,{b64_frame}",
                "location_name": LOCATION_NAME,
                "latitude": live_lat,
                "longitude": live_lng,
                "stage": stage_text,
                "blue_code": blue_code,
                "traffic_light": remote_traffic_light,
                "timer": round(timer_sec, 1),
                "objects": hazard_count,
                "hazards": hazards_summary,
                "timestamp": time.strftime("%H:%M:%S")
            }
            requests.post(LIVE_STREAM_URL, json=payload, timeout=0.7)
        except Exception:
            pass

    threading.Thread(target=_stream_worker, daemon=True).start()


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
            "notes": f"[{stage_label}] {detected_summary} obstructing traffic signal at {LOCATION_NAME} for {int(duration_sec)}s | Blue Strobe Active",
            "image_base64": f"data:image/jpeg;base64,{img_base64}"
        }

        res = requests.post(BACKEND_URL, json=payload, timeout=10)
        if res.status_code == 200:
            cloud_sync_banner_until = time.time() + 8.0
            print(f"🚨 [CONTROL ROOM ALERT DISPATCHED] >45s Strobe Alert synced for {LOCATION_NAME}!")
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
    global stop_threads, remote_blue_override, remote_traffic_light

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("❌ Error: Could not open webcam.")
        return

    # Start background thread for instant Control Room signal override polling
    sync_thread = threading.Thread(target=control_room_sync_worker, daemon=True)
    sync_thread.start()

    obstruction_start_time = None
    strobe_alert_sent = False
    manual_simulation_mode = False

    print("=========================================================================")
    print("🛡️ BLU Guard AI - YOLOv8 + Control Room Live Traffic Signal Hardware Sync")
    print(f"📍 Signal Location: {LOCATION_NAME}")
    print("👉 Keyboard: [m] Toggle Sim | [t] Force >45s Alert | [a] Reset to AI Auto | [q] Quit")
    print("=========================================================================")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        read_arduino_serial_feedback()

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
        elif key == ord('a'):
            remote_blue_override = "AUTO"
            remote_traffic_light = "C"
            send_arduino_signal_command('C', force=True)
            print("🔄 Restored Autonomous Traffic & AI Mode")
        elif key == ord('t'):
            send_arduino_ai_command('A', force=True)
            push_yolo_alert_nonblocking(frame, 46, "FORCED >45s STROBE TEST", "Simulated Obstruction")

        is_obstructed = (len(zone_hazards) > 0) or manual_simulation_mode

        zone_color = (0, 0, 255) if is_obstructed else (0, 255, 255)
        cv2.rectangle(frame, (rx1, ry1), (rx2, ry2), zone_color, 2)
        cv2.putText(frame, f"AI DETECTION ZONE (ROI) | Hazards: {len(zone_hazards)} | Signal Phase: {remote_traffic_light}",
                    (rx1, ry1 - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.48, zone_color, 2)

        cv2.rectangle(frame, (0, 0), (width, 52), (15, 23, 42), -1)

        if is_obstructed:
            if obstruction_start_time is None:
                obstruction_start_time = time.time()
                strobe_alert_sent = False

            elapsed = time.time() - obstruction_start_time
            detected_summary = ", ".join(set(zone_hazards)) if zone_hazards else "MANUAL SIMULATION"

            if elapsed < 15.0:
                blue_code = 'B'
                blue_mode_text = "BLINKING ('B') [0-15s]"
                hud_color = (0, 255, 255)
            elif elapsed < 45.0:
                blue_code = 'S'
                blue_mode_text = "STEADY LOCK ('S') [15-45s]"
                hud_color = (0, 165, 255)
            else:
                blue_code = 'A'
                blue_mode_text = "EMERGENCY STROBE ('A') [>45s]"
                hud_color = (0, 0, 255)

            # Respect Control Room manual Blue AI Lamp override if set
            if remote_blue_override in ('0', 'B', 'S', 'A'):
                blue_code = remote_blue_override
                blue_mode_text = f"CONTROL ROOM OVERRIDE ('{blue_code}')"

            send_arduino_ai_command(blue_code)

            cv2.putText(frame, f"TIMER: {elapsed:.1f}s | BLUE LED: {blue_mode_text}",
                        (12, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.52, hud_color, 2)
            cv2.putText(frame, f"SIGNAL: {LOCATION_NAME} | {detected_summary}",
                        (12, 44), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (200, 230, 255), 1)

            if elapsed >= 45.0 and not strobe_alert_sent:
                push_yolo_alert_nonblocking(frame, elapsed, "CRITICAL >45s STROBE ESCALATION", detected_summary)
                strobe_alert_sent = True

            push_live_yolo_visuals(frame, blue_mode_text, elapsed, len(zone_hazards), detected_summary, blue_code)
        else:
            obstruction_start_time = None
            strobe_alert_sent = False

            # If Control Room clicked Blink ('B'), Steady ('S'), or Strobe ('A'), keep it active!
            if remote_blue_override in ('0', 'B', 'S', 'A'):
                blue_code = remote_blue_override
                stage_label = f"CONTROL ROOM BLUE ('{blue_code}')"
            else:
                blue_code = '0'
                stage_label = "STAGE 0: CLEAR ('0')"

            send_arduino_ai_command(blue_code)

            cv2.putText(frame, f"ZONE CLEAR | Light: {remote_traffic_light} | Blue: {blue_code}",
                        (12, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
            cv2.putText(frame, f"LOC: {gps_status} | [m] Sim | [t] Alert | [a] Auto",
                        (12, 44), cv2.FONT_HERSHEY_SIMPLEX, 0.44, (200, 200, 200), 1)

            push_live_yolo_visuals(frame, stage_label, 0.0, 0, "CLEAR", blue_code)

        if time.time() < cloud_sync_banner_until or strobe_alert_sent:
            cv2.rectangle(frame, (int(width * 0.08), int(height * 0.78)),
                          (int(width * 0.92), int(height * 0.87)), (0, 0, 180), -1)
            cv2.rectangle(frame, (int(width * 0.08), int(height * 0.78)),
                          (int(width * 0.92), int(height * 0.87)), (0, 255, 255), 2)
            cv2.putText(frame, "ALERT SENT TO CONTROL ROOM WITH SIGNAL LOCATION!",
                        (int(width * 0.09), int(height * 0.835)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.52, (255, 255, 255), 2)

        cv2.imshow("BLU Guard AI - Live Edge Monitor", frame)

    stop_threads = True
    send_arduino_ai_command('0', force=True)
    send_arduino_signal_command('C', force=True)
    if ser and ser.is_open:
        ser.close()
    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()