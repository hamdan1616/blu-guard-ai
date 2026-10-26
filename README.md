# 🛡️ BLU Guard AI (நான்காம் காவல் நண்பன்)
**Integrated Edge-AI Traffic Blockade Detection, ESP8266 Strobe Hardware & Geofenced Police Tactical Command System**  
*Built for MY Bharat — Hack for Social Cause (Theme: Governance & Civic Technology)*  
**Designed & Developed by:** Mohamed Hamdan

---

## 🏗️ 1. System Architecture & Technical Design

    +-------------------------------------------------------------------------+
    |                   TIER 1: EDGE-AI & IoT HARDWARE NODE                   |
    |  [Webcam YOLOv8 (80 Classes)] <──(USB Serial COM7)──> [ESP8266 NodeMCU] |
    |   • ROI Hazard Timer (0-15s Blink 'B' | 15-45s Steady 'S' | >45s 'A')   |
    |   • NEO-6M GPS Stream (D6) + Autonomous Traffic Matrix (D5, D2, D7)     |
    |   • External Blue AI Strobe LED on Pin D3                               |
    +------------------------------------+------------------------------------+
                                         │
             (At >= 45.0s: HTTP POST Snapshot + GPS + API Key: BLU-GUARD-2026)
                                         ▼
    +-------------------------------------------------------------------------+
    |               TIER 2: FASTAPI BACKEND & SQLITE DATABASE                 |
    |  • Server: http://192.168.137.1:8000 | DB: tactical_8002.db             |
    |  • Role-Based Access Control (Admin TN-ADMIN-01 vs. Field Officers)     |
    |  • Pending Approval Security Lock & Department Clearance Audit Trail    |
    +-----------------+-------------------------------------+-----------------+
                      │                                     │
          (Live Polling & Web Speech)           (2.5s Sync + Expo Location)
                      ▼                                     ▼
    +-----------------------------------+ +-----------------------------------+
    | TIER 3: WEB GEO-RADAR COMMAND     | | TIER 4: REACT NATIVE MOBILE APP   |
    | • Leaflet.js Dark Geo-Radar Grid  | | • Role-Filtered Voice Dispatch    |
    | • Admin Officer Approval & Editor | | • Live Phone GPS Route Streaming  |
    | • Pulsing Officer Shield Tracking | | • 100m Haversine Geofence Lock    |
    | • Master Wireless Telemetry Log   | | • Mandatory Live Camera Clearance |
    +-----------------------------------+ +-----------------------------------+

---

## ⚙️ 2. Environment Variables & Configuration

| Variable / Constant | Value / Default | Location | Description |
| :--- | :--- | :--- | :--- |
| `EDGE_API_KEY` | `BLU-GUARD-2026` | `main.py` & `yolo_live_detector.py` | Authenticates Edge-AI hazard triggers |
| `SQLALCHEMY_DATABASE_URL` | `sqlite:///./tactical_8002.db` | `main.py` | Local SQLite database path |
| `API_BASE_URL` | `http://192.168.137.1:8000` | `App.js` & `yolo_live_detector.py` | Local Hotspot IP of FastAPI server |
| `SERIAL_PORT` / `BAUD_RATE` | `COM7` / `115200` | `yolo_live_detector.py` | USB Serial bridge to ESP8266 |

---

## 🚀 3. Step-by-Step Setup Instructions

### A. Hardware & Arduino Setup (`esp8266_traffic_ai.ino`)
1. Connect LEDs to ESP8266: Red (`D5`), Yellow (`D2`), Green (`D7`), External Blue Strobe (`D3`), GPS TX (`D6`).
2. Flash `esp8266_traffic_ai.ino` via Arduino IDE (`NodeMCU 1.0 ESP-12E`, `115200` baud).

### B. FastAPI Backend & Web Command Center (`main.py`)
    pip install fastapi uvicorn sqlalchemy pydantic python-multipart requests opencv-python ultralytics pyserial numpy
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload

* Open `http://localhost:8000` (Admin Login: `TN-ADMIN-01` / `Admin@123` | Officer Login: `test1` / `password`).

### C. YOLOv8 Edge-AI Detector (`yolo_live_detector.py`)
    python yolo_live_detector.py

* Press `m` to toggle simulation timer, `t` to force an instant >45s cloud alert, or `q` to quit.

### D. Expo Mobile App (`App.js`)
    npx expo install @react-native-async-storage/async-storage expo-image-picker expo-speech expo-location
    npx expo start -c

---

## 🚨 4. AI Detection Zone (ROI) & 3-Stage Blue Light Hardware Escalation

Whenever a road hazard (`person`, `bicycle`, `car`, `motorcycle`, `bus`, `truck`) enters the **AI Detection Zone**, `yolo_live_detector.py` communicates over USB Serial (`COM7` @ `115200` baud) with the ESP8266 to drive the **External Blue AI Strobe LED (`Pin D3` / `GPIO 0`)** through 4 distinct tactical states:

| Detection Zone Timer | Serial Command | Pin `D3` Blue Light Behavior | Tactical & System Action |
| :--- | :---: | :--- | :--- |
| **Zone Clear (`0.0s`)** | `'0'` | **OFF (`LOW`)** | Normal traffic flow; Green HUD (`ZONE CLEAR`); autonomous R/Y/G signal cycling. |
| **Stage 1 (`0.1s – 15.0s`)** | `'B'` | **Slow Blink (`300ms` cadence)** | Early local visual warning to approaching motorists that an object is inside the Detection Zone. |
| **Stage 2 (`15.0s – 45.0s`)** | `'S'` | **Steady Lock (`HIGH`)** | Sustained obstruction lock; Orange HUD warning indicates potential congestion forming. |
| **Stage 3 (`>= 45.0s`)** | `'A'` | **Emergency Strobe (`70ms` rapid flash)** | **Critical Escalation:** High-intensity police strobe on `D3` + non-blocking HTTP POST of Base64 live snapshot & sector GPS coordinates to Central Command & Field Officer Mobile App. |

---

## 🧪 5. Sample Data & Test Cases

| Test ID | Test Case Scenario | Input / Action | Expected System Outcome | Status |
| :--- | :--- | :--- | :--- | :--- |
| **TC-01** | Edge-AI >45s Escalation | Hazard inside ROI for >= 45s (or press `t`) | ESP8266 Pin `D3` strobes (`'A'`); POSTs Base64 snapshot & GPS to `/api/edge-trigger` | PASS |
| **TC-02** | Officer OTP Enrolment & Lock | Register new badge `TN-POLICE-99` with 6-digit OTP | Account created with `status = "PENDING APPROVAL"`; field dispatch buttons locked | PASS |
| **TC-03** | Admin Approval & Profile Edit | Login as `TN-ADMIN-01` -> Click `Approve` on `TN-POLICE-99` | Officer status updates to `ACTIVE`; mobile dispatch controls unlock immediately | PASS |
| **TC-04** | Live GPS Dispatch Telemetry | Officer taps `🚓 Dispatch Unit` on mobile app | Status -> `ASSIGNED`; phone streams GPS every 4s; pulsing icon + route line appear on Web Map | PASS |
| **TC-05** | 100m Geofenced Arrival Check | Production officer taps `📍 Mark Arrived` >100m away | Blocked by Haversine Geofence Lock warning (`test1` demo account bypasses for live presentation) | PASS |
| **TC-06** | Mandatory Live Camera Proof | Officer taps `📷 Camera Clear` & captures live photo | Gallery upload blocked; status -> `RESOLVED` (Green pin); logged in officer's Last 10 Clearances | PASS |

---

## 📄 6. Copyright & License
Copyright (c) 2026 Mohamed Hamdan. All rights reserved. See `LICENSE` for details.