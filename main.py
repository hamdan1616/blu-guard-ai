from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File, Form, Body
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse, Response
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, text
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from datetime import datetime
from typing import Optional
import os
import random
import base64
import urllib.parse
import urllib.request

# --- SQLite Database Setup ---
SQLALCHEMY_DATABASE_URL = "sqlite:///./tactical_8002.db"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, 
    connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- Database Models ---
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    password = Column(String)
    name = Column(String)
    designation = Column(String, default="Sub-Inspector (SI)")
    email = Column(String)
    mobile = Column(String)
    badge_number = Column(String, unique=True, index=True)
    profile_photo = Column(String, nullable=True)
    status = Column(String, default="ACTIVE")

class Blockade(Base):
    __tablename__ = "blockades"
    id = Column(Integer, primary_key=True, index=True)
    location_name = Column(String, index=True)
    latitude = Column(Float)
    longitude = Column(Float)
    severity = Column(String)
    status = Column(String, default="ACTIVE")
    notes = Column(String, nullable=True)
    image_url = Column(String, nullable=True)
    clearance_photo = Column(String, nullable=True)
    resolved_by = Column(String, nullable=True)
    officer_lat = Column(Float, nullable=True)
    officer_lng = Column(Float, nullable=True)
    green_corridor = Column(Boolean, default=False)
    signal_color = Column(String, default="C") # 'C'=Auto, 'R'=Red, 'Y'=Yellow, 'G'=Green
    blue_mode = Column(String, default="B")    # '0'=Off, 'B'=Blink, 'S'=Steady, 'A'=Strobe
    created_at = Column(DateTime, default=datetime.utcnow)

class Notification(Base):
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True, index=True)
    message = Column(String)
    image_thumb = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class Feedback(Base):
    __tablename__ = "feedbacks"
    id = Column(Integer, primary_key=True, index=True)
    badge_number = Column(String, index=True)
    officer_name = Column(String)
    designation = Column(String)
    rating = Column(Integer, default=5)
    message = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

class VoiceNote(Base):
    __tablename__ = "voice_notes"
    id = Column(String, primary_key=True, index=True)
    officer_name = Column(String)
    badge_number = Column(String)
    location_name = Column(String)
    transcript = Column(String)
    is_listened = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(bind=engine)

# Auto-migrate new columns if upgrading an existing tactical_8002.db
with engine.connect() as conn:
    for stmt in [
        "ALTER TABLE users ADD COLUMN designation VARCHAR DEFAULT 'Sub-Inspector (SI)'",
        "ALTER TABLE blockades ADD COLUMN green_corridor BOOLEAN DEFAULT 0",
        "ALTER TABLE blockades ADD COLUMN signal_color VARCHAR DEFAULT 'C'",
        "ALTER TABLE blockades ADD COLUMN blue_mode VARCHAR DEFAULT 'B'",
        "ALTER TABLE blockades ADD COLUMN created_at DATETIME"
    ]:
        try:
            conn.execute(text(stmt))
            conn.commit()
        except Exception:
            pass

app = FastAPI(
    title="நான்காம் காவல் நண்பன் | Naangham Kaaval Nanban - TN Police Control Room", 
    version="70.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")
EDGE_API_KEY = "BLU-GUARD-2026"

# --- Global Hardware Signal Control State (Synced with ESP8266 via yolo_live_detector.py) ---
GLOBAL_SIGNAL_CONTROL = {
    "traffic_light": "C",  # 'C' = Auto Cycle, 'R' = Red, 'Y' = Yellow, 'G' = Green
    "blue_mode": "AUTO",   # 'AUTO', '0' = Off, 'B' = Blink (0-15s), 'S' = Steady (15-45s), 'A' = Strobe (>45s)
    "version": 1,          # Increments on every button click so yolo_live_detector.py never misses a command
    "updated_by": "CONTROL ROOM"
}

# --- Multi-Junction Live YOLOv8 Stream Store ---
LATEST_YOLO_STREAM = {
    "frame": None,
    "location_name": "Kumbakonam Central Traffic Signal - Pole 04",
    "latitude": 10.9601,
    "longitude": 79.3845,
    "stage": "WAITING FOR YOLO DETECTOR...",
    "blue_code": "0",
    "traffic_light": "C",
    "timer": 0.0,
    "objects": 0,
    "hazards": "NONE",
    "timestamp": "--:--:--"
}

ALL_SIGNAL_STREAMS = {
    "Kumbakonam Central Traffic Signal - Pole 04 (Sector 1)": {
        "frame": None,
        "location_name": "Kumbakonam Central Traffic Signal - Pole 04 (Sector 1)",
        "latitude": 10.9601,
        "longitude": 79.3845,
        "stage": "STAGE 0: CLEAR ('0')",
        "blue_code": "0",
        "traffic_light": "C",
        "timer": 0.0,
        "objects": 0,
        "hazards": "CLEAR",
        "timestamp": "LIVE EDGE NODE"
    },
    "Kumbakonam Bypass Traffic Signal - Sector 2": {
        "frame": "https://images.unsplash.com/photo-1542282088-72c9c27ed0cd?w=480&q=80",
        "location_name": "Kumbakonam Bypass Traffic Signal - Sector 2",
        "latitude": 10.9601,
        "longitude": 79.3845,
        "stage": "EMERGENCY STROBE ('A') [>45s]",
        "blue_code": "A",
        "traffic_light": "R",
        "timer": 52.4,
        "objects": 3,
        "hazards": "CAR, TRUCK",
        "timestamp": "SIGNAL CAM #02"
    },
    "Mahamaham Tank West Traffic Signal": {
        "frame": "https://images.unsplash.com/photo-1506521781263-d8422e82f27a?w=480&q=80",
        "location_name": "Mahamaham Tank West Traffic Signal",
        "latitude": 10.9576,
        "longitude": 79.3789,
        "stage": "STEADY LOCK ('S') [15-45s]",
        "blue_code": "S",
        "traffic_light": "Y",
        "timer": 22.0,
        "objects": 2,
        "hazards": "CAR",
        "timestamp": "SIGNAL CAM #03"
    },
    "Mayiladuthurai Highway Signal Pole 02": {
        "frame": "https://images.unsplash.com/photo-1519003722824-194d4455a60c?w=480&q=80",
        "location_name": "Mayiladuthurai Highway Signal Pole 02",
        "latitude": 11.1018,
        "longitude": 79.6524,
        "stage": "BLINKING ('B') [0-15s]",
        "blue_code": "B",
        "traffic_light": "G",
        "timer": 8.2,
        "objects": 1,
        "hazards": "BUS",
        "timestamp": "SIGNAL CAM #04"
    }
}

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class RegisterRequest(BaseModel):
    name: str
    designation: Optional[str] = "Sub-Inspector (SI)"
    email: str
    mobile: str
    badge_number: str
    password: str

class AdminEditOfficerRequest(BaseModel):
    name: str
    designation: Optional[str] = "Sub-Inspector (SI)"
    email: str
    mobile: str
    status: str
    password: Optional[str] = None

class EdgeModelTrigger(BaseModel):
    api_key: str
    location_name: str
    latitude: float
    longitude: float
    severity: str = "CRITICAL"
    notes: str
    image_base64: Optional[str] = None

class TelemetryUpdate(BaseModel):
    latitude: float
    longitude: float

class FeedbackCreateRequest(BaseModel):
    rating: int = 5
    message: str

class BackupRequestPayload(BaseModel):
    target_badge: Optional[str] = "ALL UNITS"
    reason: Optional[str] = "High congestion - Multiple officers required"

class GreenCorridorPayload(BaseModel):
    active: bool

class SignalPhasePayload(BaseModel):
    signal_color: Optional[str] = None  # 'R', 'Y', 'G', 'C'
    blue_mode: Optional[str] = None     # '0', 'B', 'S', 'A', 'AUTO'
    location_name: Optional[str] = None

class VoiceNoteCreatePayload(BaseModel):
    id: Optional[str] = None
    officer_name: Optional[str] = "Field Officer"
    badge_number: Optional[str] = "TN-POLICE"
    location_name: str
    transcript: str

@app.on_event("startup")
def seed_initial_data():
    db = SessionLocal()
    admin_user = db.query(User).filter(User.username == "TN-ADMIN-01").first()
    if not admin_user:
        db.add(User(
            username="TN-ADMIN-01",
            password="Admin@123",
            name="Control Room Commander",
            designation="Control Room Supervisor",
            email="controlroom@tnpolice.gov.in",
            mobile="9999999999",
            badge_number="TN-ADMIN-01",
            status="ACTIVE"
        ))
    else:
        admin_user.name = "Control Room Commander"
        admin_user.designation = "Control Room Supervisor"

    if not db.query(User).filter(User.username == "test1").first():
        db.add(User(
            username="test1",
            password="password",
            name="K. Murugan",
            designation="Inspector",
            email="tnpolice007@tn.gov.in",
            mobile="9876543210",
            badge_number="TN-POLICE-007",
            status="ACTIVE"
        ))
    if not db.query(User).filter(User.username == "TN-POLICE-008").first():
        db.add(User(
            username="TN-POLICE-008",
            password="password",
            name="S. Anbuarasu",
            designation="Sub-Inspector (SI)",
            email="anbu008@tn.gov.in",
            mobile="9840011223",
            badge_number="TN-POLICE-008",
            status="ACTIVE"
        ))
    
    if db.query(Blockade).filter(Blockade.status != "RESOLVED").count() == 0:
        db.add(Blockade(
            location_name="Kumbakonam Bypass Traffic Signal - Sector 2",
            latitude=10.9601,
            longitude=79.3845,
            severity="CRITICAL",
            status="ACTIVE",
            notes="Multi-vehicle collision blocking north signal lane",
            image_url="https://images.unsplash.com/photo-1542282088-72c9c27ed0cd?w=400&q=80",
            green_corridor=False,
            signal_color="R",
            blue_mode="A",
            created_at=datetime.utcnow()
        ))

    if db.query(VoiceNote).count() == 0:
        db.add(VoiceNote(
            id="ptt-seed-1",
            officer_name="Inspector K. Murugan (TN-POLICE-007)",
            badge_number="TN-POLICE-007",
            location_name="Kumbakonam Bypass Traffic Signal - Sector 2",
            transcript="Tow Crane required immediately at signal junction to clear north lane.",
            is_listened=False,
            created_at=datetime.utcnow()
        ))
    db.commit()
    db.close()

@app.get("/logo.png", include_in_schema=False)
def get_logo():
    if os.path.exists("logo.png"):
        return FileResponse("logo.png")
    raise HTTPException(status_code=404, detail="Logo not found")

# --- Native Indian Female Voice TTS Proxy (Produces the Exact Same Lady Voice as the Android/Expo App!) ---
@app.get("/api/tts-lady", tags=["Female Tamil/English Voice Synthesis"])
def get_lady_voice_tts(text: str, lang: str = "ta"):
    try:
        encoded = urllib.parse.quote(text)
        url = f"https://translate.googleapis.com/translate_tts?client=tw-ob&ie=UTF-8&tl={lang}&q={encoded}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=4) as response:
            audio_bytes = response.read()
            return Response(content=audio_bytes, media_type="audio/mpeg")
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

# --- Direct Traffic Signal Hardware Control Endpoints (Red / Yellow / Green / Auto + Blue Strobe) ---
@app.get("/api/signal-control", tags=["Direct Traffic Signal Control"])
def get_signal_control_state():
    return GLOBAL_SIGNAL_CONTROL

@app.post("/api/signal-control", tags=["Direct Traffic Signal Control"])
def set_global_signal_control(
    payload: SignalPhasePayload,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    global GLOBAL_SIGNAL_CONTROL, ALL_SIGNAL_STREAMS, LATEST_YOLO_STREAM
    stage_map = {
        "0": "STAGE 0: CLEAR ('0')",
        "B": "BLINKING ('B') [0-15s]",
        "S": "STEADY LOCK ('S') [15-45s]",
        "A": "EMERGENCY STROBE ('A') [>45s]"
    }

    if payload.signal_color in ("R", "Y", "G", "C"):
        GLOBAL_SIGNAL_CONTROL["traffic_light"] = payload.signal_color
        LATEST_YOLO_STREAM["traffic_light"] = payload.signal_color
        if payload.location_name and payload.location_name in ALL_SIGNAL_STREAMS:
            ALL_SIGNAL_STREAMS[payload.location_name]["traffic_light"] = payload.signal_color
        else:
            for k in ALL_SIGNAL_STREAMS:
                ALL_SIGNAL_STREAMS[k]["traffic_light"] = payload.signal_color

    if payload.blue_mode in ("0", "B", "S", "A", "AUTO"):
        GLOBAL_SIGNAL_CONTROL["blue_mode"] = payload.blue_mode
        effective_blue = payload.blue_mode if payload.blue_mode != "AUTO" else "0"
        LATEST_YOLO_STREAM["blue_code"] = effective_blue
        LATEST_YOLO_STREAM["stage"] = stage_map.get(effective_blue, "ACTIVE")
        if payload.location_name and payload.location_name in ALL_SIGNAL_STREAMS:
            ALL_SIGNAL_STREAMS[payload.location_name]["blue_code"] = effective_blue
            ALL_SIGNAL_STREAMS[payload.location_name]["stage"] = stage_map.get(effective_blue, "ACTIVE")
        else:
            for k in ALL_SIGNAL_STREAMS:
                ALL_SIGNAL_STREAMS[k]["blue_code"] = effective_blue
                ALL_SIGNAL_STREAMS[k]["stage"] = stage_map.get(effective_blue, "ACTIVE")

    GLOBAL_SIGNAL_CONTROL["version"] = int(GLOBAL_SIGNAL_CONTROL.get("version", 1)) + 1
    GLOBAL_SIGNAL_CONTROL["updated_by"] = token
    return {"status": "ok", "control": GLOBAL_SIGNAL_CONTROL}

@app.post("/blockades/{blockade_id}/signal-phase", tags=["Direct Traffic Signal Control"])
def set_incident_signal_phase(
    blockade_id: int,
    payload: SignalPhasePayload,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    global GLOBAL_SIGNAL_CONTROL, ALL_SIGNAL_STREAMS, LATEST_YOLO_STREAM
    b = db.query(Blockade).filter(Blockade.id == blockade_id).first()
    if not b:
        raise HTTPException(status_code=404, detail="Incident not found")

    if payload.signal_color in ("R", "Y", "G", "C"):
        b.signal_color = payload.signal_color
        b.green_corridor = (payload.signal_color == "G")
        GLOBAL_SIGNAL_CONTROL["traffic_light"] = payload.signal_color
        LATEST_YOLO_STREAM["traffic_light"] = payload.signal_color
        if b.location_name in ALL_SIGNAL_STREAMS:
            ALL_SIGNAL_STREAMS[b.location_name]["traffic_light"] = payload.signal_color

    if payload.blue_mode in ("0", "B", "S", "A", "AUTO"):
        b.blue_mode = payload.blue_mode if payload.blue_mode != "AUTO" else "B"
        GLOBAL_SIGNAL_CONTROL["blue_mode"] = payload.blue_mode
        LATEST_YOLO_STREAM["blue_code"] = b.blue_mode
        if b.location_name in ALL_SIGNAL_STREAMS:
            ALL_SIGNAL_STREAMS[b.location_name]["blue_code"] = b.blue_mode

    GLOBAL_SIGNAL_CONTROL["version"] = int(GLOBAL_SIGNAL_CONTROL.get("version", 1)) + 1
    GLOBAL_SIGNAL_CONTROL["updated_by"] = token
    db.commit()
    return {
        "status": "ok",
        "id": b.id,
        "signal_color": b.signal_color,
        "blue_mode": b.blue_mode,
        "green_corridor": b.green_corridor,
        "version": GLOBAL_SIGNAL_CONTROL["version"]
    }

@app.post("/api/yolo-stream", tags=["Live Project Model Integration"])
def update_yolo_stream(data: dict = Body(...)):
    global LATEST_YOLO_STREAM, ALL_SIGNAL_STREAMS
    LATEST_YOLO_STREAM.update(data)
    loc_name = data.get("location_name") or "Kumbakonam Central Traffic Signal - Pole 04 (Sector 1)"
    ALL_SIGNAL_STREAMS[loc_name] = dict(LATEST_YOLO_STREAM)
    return {"status": "ok"}

@app.get("/api/yolo-stream", tags=["Live Project Model Integration"])
def get_yolo_stream(location_name: Optional[str] = None):
    if location_name and location_name in ALL_SIGNAL_STREAMS:
        stream_item = dict(ALL_SIGNAL_STREAMS[location_name])
        if not stream_item.get("frame") and LATEST_YOLO_STREAM.get("frame"):
            stream_item["frame"] = LATEST_YOLO_STREAM["frame"]
        return stream_item
    return LATEST_YOLO_STREAM

@app.get("/api/yolo-streams-all", tags=["Live Project Model Integration"])
def get_all_yolo_streams():
    result = []
    for k, v in ALL_SIGNAL_STREAMS.items():
        item = dict(v)
        if not item.get("frame") and LATEST_YOLO_STREAM.get("frame"):
            item["frame"] = LATEST_YOLO_STREAM["frame"]
            item["stage"] = LATEST_YOLO_STREAM.get("stage", item["stage"])
            item["blue_code"] = LATEST_YOLO_STREAM.get("blue_code", item.get("blue_code", "0"))
            item["traffic_light"] = LATEST_YOLO_STREAM.get("traffic_light", item.get("traffic_light", "C"))
            item["timer"] = LATEST_YOLO_STREAM.get("timer", item["timer"])
            item["objects"] = LATEST_YOLO_STREAM.get("objects", item["objects"])
            item["hazards"] = LATEST_YOLO_STREAM.get("hazards", item["hazards"])
            item["timestamp"] = LATEST_YOLO_STREAM.get("timestamp", item["timestamp"])
        result.append(item)
    return result

@app.post("/blockades/{blockade_id}/green-corridor", tags=["Tactical Blockades"])
def toggle_green_corridor(
    blockade_id: int,
    payload: GreenCorridorPayload,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    global GLOBAL_SIGNAL_CONTROL
    b = db.query(Blockade).filter(Blockade.id == blockade_id).first()
    if not b:
        raise HTTPException(status_code=404, detail="Blockade not found")
    b.green_corridor = payload.active
    b.signal_color = "G" if payload.active else "C"
    GLOBAL_SIGNAL_CONTROL["traffic_light"] = "G" if payload.active else "C"
    GLOBAL_SIGNAL_CONTROL["version"] = int(GLOBAL_SIGNAL_CONTROL.get("version", 1)) + 1

    if payload.active:
        msg = f"[GREEN CORRIDOR] 🚑 108 ஆம்புலன்ஸ் பசுமை வழித்தடம் | Green Signal Priority ON @ {b.location_name}"
    else:
        msg = f"[SIGNAL NORMAL] 🚦 Green Corridor deactivated @ {b.location_name}"
    db.add(Notification(message=msg, image_thumb=b.image_url))
    db.commit()
    return {"status": "ok", "green_corridor": b.green_corridor, "signal_color": b.signal_color}

@app.get("/api/voice-notes", tags=["Walkie-Talkie PTT Voice Notes"])
def get_voice_notes(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    return db.query(VoiceNote).order_by(VoiceNote.created_at.desc()).all()

@app.post("/api/voice-notes", tags=["Walkie-Talkie PTT Voice Notes"])
def create_voice_note(
    payload: VoiceNoteCreatePayload,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.username == token).first()
    sender_name = payload.officer_name
    badge = payload.badge_number
    if user:
        sender_name = f"{user.designation or 'Officer'} {user.name} ({user.badge_number})"
        badge = user.badge_number

    vn_id = payload.id or f"ptt-{int(datetime.utcnow().timestamp() * 1000)}"
    existing = db.query(VoiceNote).filter(VoiceNote.id == vn_id).first()
    if not existing:
        new_vn = VoiceNote(
            id=vn_id,
            officer_name=sender_name,
            badge_number=badge,
            location_name=payload.location_name,
            transcript=payload.transcript.strip(),
            is_listened=False,
            created_at=datetime.utcnow()
        )
        db.add(new_vn)
        db.add(Notification(
            message=f"[PTT VOICE] 🎙️ New Walkie-Talkie Voice Note queued by {sender_name} @ {payload.location_name} (Open PTT Voice Tab to Play)"
        ))
        db.commit()
    return {"status": "queued", "id": vn_id}

@app.post("/api/voice-notes/{voice_id}/listen", tags=["Walkie-Talkie PTT Voice Notes"])
def mark_voice_note_listened(
    voice_id: str,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    vn = db.query(VoiceNote).filter(VoiceNote.id == voice_id).first()
    if vn:
        vn.is_listened = True
        db.commit()
    return {"status": "listened", "id": voice_id}

@app.get("/api/officers/active", tags=["Officer Backup & Assistance"])
def get_active_officers_for_backup(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    officers = db.query(User).filter(User.status == "ACTIVE", User.username != "TN-ADMIN-01").all()
    return [
        {
            "id": o.id,
            "name": o.name,
            "designation": o.designation or "Officer",
            "badge_number": o.badge_number,
            "mobile": o.mobile
        }
        for o in officers
    ]

@app.post("/blockades/{blockade_id}/request-backup", tags=["Officer Backup & Assistance"])
def request_officer_backup(
    blockade_id: int,
    payload: BackupRequestPayload,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    requester = db.query(User).filter(User.username == token).first()
    b = db.query(Blockade).filter(Blockade.id == blockade_id).first()
    if not b:
        raise HTTPException(status_code=404, detail="Blockade not found")

    if payload.target_badge and "[PTT VOICE]" in payload.target_badge:
        parts = payload.target_badge.split("|")
        sender = parts[1].strip() if len(parts) > 1 else token
        transcript = payload.reason or "Field voice status update."
        vn_id = f"ptt-{int(datetime.utcnow().timestamp() * 1000)}"
        db.add(VoiceNote(
            id=vn_id,
            officer_name=sender,
            badge_number=token,
            location_name=b.location_name,
            transcript=transcript,
            is_listened=False,
            created_at=datetime.utcnow()
        ))
        db.add(Notification(message=f"[PTT VOICE] 🎙️ Voice Note queued by {sender} @ {b.location_name}"))
        db.commit()
        return {"status": "voice_queued"}

    req_name = f"{requester.designation} {requester.name}" if requester else token
    target_str = payload.target_badge or "ALL UNITS"
    short_msg = (
        f"[BACKUP SOS] 🆘 உதவி அழைப்பு! {b.location_name} சிக்னலில் கூடுதல் காவலர்கள் தேவை "
        f"| Backup needed by {req_name} -> {target_str} @ {b.location_name}"
    )
    b.notes = f"{b.notes or ''} | [🆘 BACKUP REQUESTED: {target_str}]"
    db.add(Notification(message=short_msg, image_thumb=b.image_url))
    db.commit()
    return {"status": "backup_dispatched", "message": short_msg}

@app.post("/api/feedback", tags=["Officer Feedback"])
def submit_officer_feedback(payload: FeedbackCreateRequest, token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == token).first()
    if not user:
        raise HTTPException(status_code=404, detail="Officer not found")
    fb = Feedback(
        badge_number=user.badge_number,
        officer_name=user.name,
        designation=user.designation or "Officer",
        rating=max(1, min(5, payload.rating)),
        message=payload.message.strip()
    )
    db.add(fb)
    db.add(Notification(message=f"[OFFICER FEEDBACK] {user.designation} {user.name} ({user.badge_number}) submitted a {fb.rating}★ app review."))
    db.commit()
    return {"message": "Feedback submitted to Control Room"}

@app.get("/api/feedback", tags=["Officer Feedback"])
def get_all_feedbacks(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    if token.upper() == "TN-ADMIN-01":
        return db.query(Feedback).order_by(Feedback.id.desc()).all()
    user = db.query(User).filter(User.username == token).first()
    badge = user.badge_number if user else token
    return db.query(Feedback).filter(Feedback.badge_number == badge).order_by(Feedback.id.desc()).all()

@app.get("/", response_class=HTMLResponse, tags=["Frontend UI"])
def serve_frontend():
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>நான்காம் காவல் நண்பன் | TN Police Control Room</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
        <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
        <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
        <style>
            .leaflet-layer, .leaflet-control-zoom-in, .leaflet-control-zoom-out, .leaflet-control-attribution {
                filter: invert(100%) hue-rotate(190deg) brightness(95%) contrast(92%);
            }
            .leaflet-container { background: #060b16; }
            .tn-police-stripe {
                background: linear-gradient(90deg, #b91c1c 0%, #b91c1c 50%, #1e3a8a 50%, #1e3a8a 100%);
            }
            .gold-glow { box-shadow: 0 0 30px rgba(245, 158, 11, 0.22); }
            .glass-card { background: rgba(13, 24, 46, 0.96); }

            /* TINY THEME-MATCHED SCROLLBARS */
            * {
                scrollbar-width: thin;
                scrollbar-color: #f59e0b #071022;
            }
            ::-webkit-scrollbar { width: 6px; height: 6px; }
            ::-webkit-scrollbar-track {
                background: #071022;
                border-radius: 8px;
                border: 1px solid rgba(51, 65, 85, 0.4);
            }
            ::-webkit-scrollbar-thumb {
                background: linear-gradient(180deg, #f59e0b 0%, #2563eb 100%);
                border-radius: 8px;
            }
            ::-webkit-scrollbar-thumb:hover { background: #fbbf24; }
            .tactical-scroll { overflow-y: scroll !important; }

            /* REALISTIC TRAFFIC SIGNAL HOUSING & 4-LAMP EFFECTS */
            .signal-housing {
                background: linear-gradient(180deg, #090d16 0%, #03060c 100%);
                border: 2px solid #334155;
                border-radius: 18px;
                padding: 8px 10px;
                box-shadow: inset 0 2px 6px rgba(0,0,0,0.9), 0 4px 12px rgba(0,0,0,0.6);
            }
            .signal-lamp {
                width: 24px;
                height: 24px;
                border-radius: 50%;
                border: 2px solid #1e293b;
                transition: transform 0.12s ease, background-color 0.12s ease;
                cursor: pointer;
                position: relative;
            }
            .signal-lamp:active { transform: scale(0.9); }
            .lamp-red-off { background: #3b0d0d; }
            .lamp-red-on {
                background: #ef4444;
                border-color: #fca5a5;
                box-shadow: 0 0 16px #ef4444, 0 0 28px #dc2626;
            }
            .lamp-yellow-off { background: #3b2a0a; }
            .lamp-yellow-on {
                background: #f59e0b;
                border-color: #fde68a;
                box-shadow: 0 0 16px #f59e0b, 0 0 28px #d97706;
            }
            .lamp-green-off { background: #093524; }
            .lamp-green-on {
                background: #10b981;
                border-color: #a7f3d0;
                box-shadow: 0 0 16px #10b981, 0 0 28px #059669;
            }
            .lamp-blue-off { background: #0a2246; }
            .lamp-blue-steady {
                background: #3b82f6;
                border-color: #93c5fd;
                box-shadow: 0 0 18px #3b82f6, 0 0 32px #2563eb;
            }
            @keyframes blue-slow-blink {
                0%, 100% {
                    background: #3b82f6;
                    border-color: #93c5fd;
                    box-shadow: 0 0 16px #3b82f6, 0 0 28px #60a5fa;
                }
                50% {
                    background: #0a2246;
                    border-color: #1e293b;
                    box-shadow: none;
                }
            }
            @keyframes blue-rapid-strobe {
                0%, 100% {
                    background: #38bdf8;
                    border-color: #ffffff;
                    box-shadow: 0 0 22px #38bdf8, 0 0 40px #2563eb;
                    transform: scale(1.08);
                }
                50% {
                    background: #0a2246;
                    border-color: #1e293b;
                    box-shadow: none;
                    transform: scale(1.0);
                }
            }
            .lamp-blue-blink { animation: blue-slow-blink 0.8s infinite; }
            .lamp-blue-strobe { animation: blue-rapid-strobe 0.18s infinite; }

            @keyframes pulse-ring {
                0% { transform: scale(0.8); opacity: 0.8; }
                100% { transform: scale(2.2); opacity: 0; }
            }
            .officer-pulse::before {
                content: '';
                position: absolute;
                width: 36px;
                height: 36px;
                border-radius: 50%;
                background: rgba(59, 130, 246, 0.6);
                animation: pulse-ring 1.5s infinite;
                z-index: -1;
            }
        </style>
    </head>
    <body class="bg-[#060c1a] text-slate-100 min-h-screen overflow-y-auto font-sans flex flex-col">

        <div class="h-1.5 w-full tn-police-stripe shrink-0 sticky top-0 z-40"></div>

        <!-- LOGIN / REGISTER MODAL -->
        <div id="login-modal" class="fixed inset-0 bg-[#050b16]/95 backdrop-blur-md z-50 flex items-center justify-center p-4 overflow-y-auto">
            <div class="bg-[#0d182e] border border-amber-500/40 rounded-2xl w-full max-w-md p-6 gold-glow relative overflow-hidden">
                <div class="absolute top-0 left-0 right-0 h-1.5 tn-police-stripe"></div>

                <div class="text-center mb-4">
                    <div class="inline-flex items-center justify-center w-24 h-24 mb-2 rounded-full bg-[#070e1c] border-2 border-amber-400 p-1 shadow-2xl relative overflow-hidden">
                        <img src="/logo.png" alt="TN Police Logo" class="w-full h-full object-contain rounded-full">
                    </div>
                    <div class="text-[10px] font-bold uppercase tracking-widest text-amber-400">தமிழ்நாடு காவல்துறை • Tamil Nadu Police</div>
                    <h1 class="text-lg font-extrabold tracking-tight text-white mt-0.5">நான்காம் காவல் நண்பன்</h1>
                    <p class="text-[11px] font-semibold text-amber-300/90">CONTROL ROOM & FIELD COMMAND</p>
                </div>

                <div class="grid grid-cols-2 gap-1 bg-[#070e1c] p-1 rounded-xl mb-4 border border-amber-500/20">
                    <button type="button" onclick="switchTab('login')" id="tab-login" class="py-1.5 text-xs font-bold rounded-lg bg-amber-500 text-slate-950 transition cursor-pointer">Control Room / Officer Login</button>
                    <button type="button" onclick="switchTab('register')" id="tab-register" class="py-1.5 text-xs font-bold rounded-lg text-slate-300 hover:text-white transition cursor-pointer">New Officer Registration</button>
                </div>

                <!-- LOGIN FORM -->
                <form id="form-login" onsubmit="handleLogin(event)" class="space-y-3">
                    <div>
                        <label class="block text-[11px] font-semibold text-amber-400/90 uppercase mb-1">Control Room ID / Officer Badge</label>
                        <input type="text" id="login-username" required placeholder="Enter TN-ADMIN-01 (Control Room) or test1" class="w-full bg-[#070e1c] border border-amber-500/30 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-amber-400">
                    </div>
                    <div>
                        <label class="block text-[11px] font-semibold text-amber-400/90 uppercase mb-1">Password</label>
                        <div class="relative">
                            <input type="password" id="login-password" required placeholder="Enter Password" class="w-full bg-[#070e1c] border border-amber-500/30 rounded-lg px-3 py-2 pr-10 text-xs text-white focus:outline-none focus:border-amber-400">
                            <button type="button" onclick="togglePasswordVisibility('login-password', 'login-eye')" class="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-amber-400 cursor-pointer">
                                <i id="login-eye" class="fa-solid fa-eye text-xs"></i>
                            </button>
                        </div>
                    </div>
                    <button type="submit" class="w-full bg-gradient-to-r from-red-700 to-blue-800 hover:from-red-600 hover:to-blue-700 border border-amber-400/50 text-white font-bold py-2 rounded-lg transition text-xs cursor-pointer shadow-md">
                        <i class="fa-solid fa-shield-halved mr-1 text-amber-300"></i> Enter Control Room Grid
                    </button>
                    <div id="login-error" class="text-center text-xs text-red-400 hidden"></div>
                </form>

                <!-- REGISTRATION FORM -->
                <div id="form-register" class="hidden space-y-2.5 max-h-80 overflow-y-auto pr-1">
                    <div id="reg-step-1" class="space-y-2">
                        <div class="grid grid-cols-2 gap-2">
                            <div>
                                <label class="block text-[10px] font-semibold text-amber-400 uppercase mb-0.5">Officer Full Name</label>
                                <input type="text" id="reg-name" placeholder="K. Murugan" class="w-full bg-[#070e1c] border border-amber-500/30 rounded-lg px-2.5 py-1.5 text-xs text-white">
                            </div>
                            <div>
                                <label class="block text-[10px] font-semibold text-amber-400 uppercase mb-0.5">Rank / Designation</label>
                                <select id="reg-designation" class="w-full bg-[#070e1c] border border-amber-500/30 rounded-lg px-2 py-1.5 text-xs text-white">
                                    <option value="Inspector">Inspector</option>
                                    <option value="Sub-Inspector (SI)" selected>Sub-Inspector (SI)</option>
                                    <option value="Assistant Commissioner (ACP)">Assistant Commissioner (ACP)</option>
                                    <option value="Traffic Head Constable">Traffic Head Constable</option>
                                    <option value="Traffic Constable">Traffic Constable</option>
                                </select>
                            </div>
                        </div>
                        <div class="grid grid-cols-2 gap-2">
                            <div>
                                <label class="block text-[10px] font-semibold text-amber-400 uppercase mb-0.5">Badge ID</label>
                                <input type="text" id="reg-badge" placeholder="TN-POLICE-99" class="w-full bg-[#070e1c] border border-amber-500/30 rounded-lg px-2.5 py-1.5 text-xs text-white">
                            </div>
                            <div>
                                <label class="block text-[10px] font-semibold text-amber-400 uppercase mb-0.5">Mobile Number</label>
                                <input type="tel" id="reg-mobile" placeholder="9876543210" class="w-full bg-[#070e1c] border border-amber-500/30 rounded-lg px-2.5 py-1.5 text-xs text-white">
                            </div>
                        </div>
                        <div>
                            <label class="block text-[10px] font-semibold text-amber-400 uppercase mb-0.5">Official Email</label>
                            <input type="email" id="reg-email" placeholder="officer@tn.gov.in" class="w-full bg-[#070e1c] border border-amber-500/30 rounded-lg px-2.5 py-1.5 text-xs text-white">
                        </div>
                        <div>
                            <label class="block text-[10px] font-semibold text-amber-400 uppercase mb-0.5">Set Password</label>
                            <div class="relative">
                                <input type="password" id="reg-password" placeholder="••••••••" class="w-full bg-[#070e1c] border border-amber-500/30 rounded-lg px-2.5 py-1.5 pr-9 text-xs text-white">
                                <button type="button" onclick="togglePasswordVisibility('reg-password', 'reg-eye')" class="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-amber-400 cursor-pointer text-xs">
                                    <i id="reg-eye" class="fa-solid fa-eye"></i>
                                </button>
                            </div>
                        </div>
                        <button type="button" onclick="requestOTP()" class="w-full bg-amber-600 hover:bg-amber-500 text-slate-950 font-bold py-2 rounded-lg transition text-xs cursor-pointer shadow">
                            <i class="fa-solid fa-paper-plane mr-1"></i> Send Verification OTP (Mail/SMS)
                        </button>
                    </div>

                    <div id="reg-step-2" class="hidden space-y-2.5">
                        <div class="bg-blue-950/40 border border-blue-500/30 p-2 rounded-lg text-center">
                            <p class="text-[11px] text-blue-300">OTP dispatched to registered mobile & email.</p>
                            <p id="otp-hint" class="text-[11px] text-amber-400 font-mono mt-0.5 font-bold"></p>
                        </div>
                        <div>
                            <label class="block text-[11px] font-semibold text-amber-400 uppercase mb-1 text-center">Enter 6-Digit OTP Code</label>
                            <input type="text" id="reg-otp" maxlength="6" placeholder="123456" class="w-full text-center tracking-widest font-mono bg-[#070e1c] border border-amber-500/50 rounded-lg px-3 py-1.5 text-sm text-amber-300">
                        </div>
                        <button type="button" onclick="verifyAndRegister()" class="w-full bg-emerald-600 hover:bg-emerald-500 text-white font-bold py-2 rounded-lg transition text-xs cursor-pointer shadow">
                            <i class="fa-solid fa-check-circle mr-1"></i> Verify OTP & Create Account
                        </button>
                        <div class="flex justify-between items-center pt-1">
                            <button type="button" onclick="resendOTP()" class="text-[10px] text-amber-400 hover:underline font-bold cursor-pointer">
                                <i class="fa-solid fa-rotate-right mr-1"></i> Resend OTP
                            </button>
                            <button type="button" onclick="backToRegStep1()" class="text-[10px] text-slate-400 hover:text-white cursor-pointer">
                                ← Edit Details
                            </button>
                        </div>
                    </div>
                    <div id="reg-error" class="text-center text-xs text-red-400 hidden"></div>
                </div>

                <div class="mt-4 pt-2.5 border-t border-slate-800 text-center">
                    <p class="text-[10px] text-slate-500 italic">Designed & Developed by Mohamed Hamdan</p>
                </div>
            </div>
        </div>

        <!-- MAIN TACTICAL CONTROL ROOM DASHBOARD -->
        <div id="dashboard" class="hidden flex-1 flex flex-col">
            <!-- STICKY TOP CONTROL ROOM HEADER -->
            <header class="bg-[#0a1326] border-b border-amber-500/35 px-5 py-2.5 flex flex-wrap justify-between items-center gap-2 shrink-0 sticky top-1.5 z-30 shadow-lg">
                <div class="flex items-center space-x-3">
                    <img src="/logo.png" class="w-9 h-9 object-contain rounded-full border border-amber-400/60 bg-slate-900" alt="Emblem">
                    <div>
                        <div class="flex items-center space-x-2">
                            <h2 class="font-extrabold text-sm tracking-wide text-white">நான்காம் காவல் நண்பன்</h2>
                            <span class="text-[10px] font-bold text-amber-300 bg-amber-500/15 border border-amber-400/30 px-2 py-0.5 rounded">TN POLICE CONTROL ROOM</span>
                            <span id="grid-status-badge" class="text-[10px] font-semibold px-2 py-0.5 rounded flex items-center gap-1 transition-all bg-emerald-500/10 border border-emerald-500/30 text-emerald-400">
                                <span id="grid-dot" class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-ping"></span> <span id="grid-text">GRID LIVE</span>
                            </span>
                        </div>
                        <p class="text-[10px] text-slate-400">Tamil Nadu Police Integrated Traffic Signal & Edge-AI Control Room • सत्यमेव जयते</p>
                    </div>
                </div>

                <div class="flex items-center flex-wrap gap-2">
                    <!-- LADY VOICE TAMIL/ENGLISH AUDIO TEST BUTTON -->
                    <button type="button" onclick="playTacticalSirenAndVoice('[LIVE YOLO MODEL ALERT] போக்குவரத்து தடை @ Kumbakonam Central Traffic Signal')" class="bg-blue-900/40 hover:bg-blue-800/60 border border-amber-400/50 text-amber-300 px-2.5 py-1.5 rounded-lg text-xs font-bold transition cursor-pointer flex items-center gap-1 shadow" title="Test Tamil + English Lady Voice Alert">
                        🔊 தமிழ்/EN Lady Voice Test
                    </button>

                    <!-- WALKIE-TALKIE PTT VOICE NOTES BUTTON -->
                    <button type="button" onclick="toggleVoiceNotesModal(true)" class="bg-amber-500/15 hover:bg-amber-500/30 border border-amber-400/50 text-amber-200 px-3 py-1.5 rounded-lg text-xs font-bold transition cursor-pointer flex items-center gap-1.5 shadow">
                        <i class="fa-solid fa-walkie-talkie text-amber-400"></i> 🎙️ PTT Voice
                        <span id="header-unread-ptt" class="hidden bg-red-600 text-white text-[10px] font-extrabold px-1.5 rounded-full">0</span>
                    </button>

                    <!-- CONTROL ROOM ACTION BUTTONS -->
                    <div id="admin-action-btns" class="hidden flex items-center space-x-2">
                        <button type="button" onclick="toggleSupervisorDrawer()" id="btn-sup-drawer" class="bg-purple-600/25 hover:bg-purple-600/40 border border-purple-400/50 text-purple-200 px-3 py-1.5 rounded-lg text-xs font-bold transition cursor-pointer flex items-center gap-1.5 shadow">
                            <i class="fa-solid fa-sliders text-purple-300"></i> Control Room Hub <i id="sup-chevron" class="fa-solid fa-chevron-up text-[9px] ml-0.5"></i>
                        </button>
                        <button type="button" onclick="toggleYoloModal(true, null)" class="bg-cyan-600/25 hover:bg-cyan-600/45 border border-cyan-400/50 text-cyan-200 px-3 py-1.5 rounded-lg text-xs font-bold transition cursor-pointer flex items-center gap-1.5 shadow">
                            <i class="fa-solid fa-traffic-light text-cyan-300"></i> All Signals Matrix & Control
                        </button>
                        <button type="button" onclick="resetDatabase()" class="bg-blue-700/25 hover:bg-blue-700/45 border border-blue-400/40 text-blue-200 px-3 py-1.5 rounded-lg text-xs font-bold transition cursor-pointer flex items-center gap-1.5">
                            <i class="fa-solid fa-rotate-right"></i> Reset
                        </button>
                        <button type="button" onclick="simulateAITrigger()" class="bg-red-700/25 hover:bg-red-700/45 border border-amber-400/40 text-amber-300 px-3 py-1.5 rounded-lg text-xs font-bold transition cursor-pointer flex items-center gap-1.5">
                            <i class="fa-solid fa-satellite-dish text-red-400"></i> Simulate AI
                        </button>
                    </div>
                    <a href="/docs" target="_blank" class="text-xs text-amber-400 hover:underline px-1.5 font-medium">API ↗</a>
                    
                    <div class="relative">
                        <button type="button" onclick="toggleProfileMenu()" class="bg-slate-800/90 hover:bg-slate-700 border border-amber-500/40 text-amber-300 px-3 py-1.5 rounded-lg text-xs font-semibold transition cursor-pointer flex items-center gap-1.5">
                            <i class="fa-solid fa-building-shield"></i> <span id="user-badge">Control Room</span> <i class="fa-solid fa-caret-down text-[9px]"></i>
                        </button>
                        <div id="profile-dropdown" class="hidden absolute right-0 mt-1.5 w-52 bg-[#0d182e] border border-amber-500/40 rounded-xl shadow-2xl z-50 overflow-hidden py-1">
                            <button type="button" onclick="openProfileModal()" class="w-full text-left px-3.5 py-2 text-xs text-slate-200 hover:bg-amber-500/20 hover:text-amber-300 transition flex items-center gap-2 cursor-pointer">
                                <i class="fa-solid fa-id-card text-amber-400"></i> View & Edit Profile
                            </button>
                            <button type="button" id="menu-my-clearances" onclick="openClearancesModal()" class="w-full text-left px-3.5 py-2 text-xs text-slate-200 hover:bg-amber-500/20 hover:text-amber-300 transition flex items-center gap-2 cursor-pointer">
                                <i class="fa-solid fa-clipboard-check text-emerald-400"></i> My Last 10 Clearances
                            </button>
                            <div class="border-t border-slate-700 my-1"></div>
                            <button type="button" onclick="logout()" class="w-full text-left px-3.5 py-2 text-xs text-red-400 hover:bg-red-950/40 transition flex items-center gap-2 cursor-pointer">
                                <i class="fa-solid fa-right-from-bracket"></i> Logout
                            </button>
                        </div>
                    </div>
                </div>
            </header>

            <!-- PENDING APPROVAL WARNING BANNER -->
            <div id="pending-banner" class="hidden bg-amber-600/20 border-b border-amber-500/50 py-1.5 px-6 text-center text-xs font-bold text-amber-300 shrink-0">
                ⏳ YOUR ACCOUNT STATUS IS "PENDING APPROVAL" BY THE CONTROL ROOM. FIELD ACTIONS ARE RESTRICTED.
            </div>

            <!-- PRIMARY WORKSPACE: INCIDENTS & INTERACTIVE TRAFFIC SIGNAL CONTROLLER AT THE TOP -->
            <div class="flex-1 grid grid-cols-1 lg:grid-cols-12 gap-4 p-4">
                
                <!-- LEFT COLUMN (4 COLS): ACTIVE FIELD INCIDENTS + REALISTIC TRAFFIC SIGNAL CONTROLLER -->
                <div class="lg:col-span-4 glass-card border border-amber-500/35 rounded-xl p-3.5 flex flex-col shadow-xl h-[700px]">
                    <div class="flex items-center justify-between border-b border-slate-800 pb-2 shrink-0">
                        <div class="flex items-center gap-2">
                            <span class="w-2 h-2 rounded-full bg-red-500 animate-ping"></span>
                            <h3 class="font-extrabold text-xs uppercase tracking-wider text-amber-400">Live Traffic Signals & Direct Control</h3>
                        </div>
                        <div class="flex items-center space-x-2">
                            <button type="button" id="btn-clear-resolved" onclick="clearResolved()" class="hidden text-[11px] text-slate-400 hover:text-red-400 cursor-pointer">Clear Resolved</button>
                            <button type="button" onclick="loadBlockades(true)" class="text-amber-400 hover:text-amber-300 text-xs cursor-pointer"><i class="fa-solid fa-rotate"></i></button>
                        </div>
                    </div>

                    <!-- GOLDEN-HOUR SLA BAR -->
                    <div class="bg-[#060c18] border border-emerald-500/35 rounded-lg px-3 py-2 my-2 flex justify-between items-center shrink-0">
                        <div class="flex items-center gap-2">
                            <i class="fa-solid fa-stopwatch text-emerald-400 text-xs"></i>
                            <span class="text-[11px] font-bold text-slate-300">Golden-Hour Avg Clearance: <strong class="text-emerald-400">03m 24s</strong></span>
                        </div>
                        <span class="bg-emerald-500/20 border border-emerald-500/40 text-emerald-300 text-[10px] font-black px-2 py-0.5 rounded">98.4% SLA</span>
                    </div>

                    <!-- ALWAYS-VISIBLE CUSTOM SCROLLBAR INCIDENT LIST -->
                    <div id="blockade-list" class="tactical-scroll flex-1 space-y-3 pr-2"></div>
                </div>

                <!-- RIGHT COLUMN (8 COLS): GEO-RADAR MAP AT TOP + CONTROL ROOM HUB & WIRELESS LOG BELOW -->
                <div class="lg:col-span-8 flex flex-col gap-4">
                    
                    <!-- TOP HERO: TN POLICE GEO-RADAR GRID -->
                    <div class="glass-card border border-amber-500/35 rounded-xl p-3 flex flex-col shadow-xl h-[395px]">
                        <div class="flex flex-wrap justify-between items-center mb-2 px-1 gap-2 shrink-0">
                            <span class="text-xs font-extrabold uppercase tracking-wider text-amber-400 flex items-center gap-1.5">
                                <i class="fa-solid fa-satellite text-red-500"></i> TN Police Control Room Geo-Radar Grid (Live Officer, 108 Corridor & Signal Tracking)
                            </span>
                            <div class="flex items-center gap-3 text-[11px] bg-[#060c18] px-3 py-1 rounded-lg border border-slate-800">
                                <span class="flex items-center gap-1"><span class="w-2.5 h-2.5 rounded-full bg-red-500 inline-block"></span> Red / Critical</span>
                                <span class="flex items-center gap-1"><span class="w-2.5 h-2.5 rounded-full bg-amber-400 inline-block"></span> Yellow</span>
                                <span class="flex items-center gap-1"><span class="w-2.5 h-2.5 rounded-full bg-emerald-400 inline-block"></span> 🚑 Green / 108 Corridor</span>
                                <span class="flex items-center gap-1"><i class="fa-solid fa-shield-halved text-blue-400"></i> Dispatched Unit</span>
                            </div>
                        </div>
                        <div id="map" class="w-full flex-1 rounded-lg border border-amber-500/20 z-10"></div>
                    </div>

                    <!-- BOTTOM ROW (288px HEIGHT): WIRELESS LOG + CONTROL ROOM HUB -->
                    <div class="grid grid-cols-1 lg:grid-cols-12 gap-4">
                        
                        <!-- WIRELESS & BLOCKADE ALERT FEED -->
                        <div id="wireless-col" class="lg:col-span-5 glass-card border border-amber-500/35 rounded-xl p-3.5 flex flex-col h-[288px] shadow-xl">
                            <div class="flex justify-between items-center mb-2 shrink-0">
                                <h3 id="wireless-log-heading" class="font-extrabold text-xs uppercase tracking-wider text-amber-400">
                                    <i class="fa-solid fa-walkie-talkie text-red-400 mr-1.5"></i>Control Room Wireless Log (தமிழ்/EN)
                                </h3>
                                <span class="text-[10px] text-amber-300 bg-amber-500/10 border border-amber-400/30 px-2 py-0.5 rounded font-semibold">Live Receiver</span>
                            </div>
                            <div id="notification-box" class="tactical-scroll flex-1 bg-[#060c18] border border-slate-800 rounded-lg p-2.5 space-y-2 font-mono text-xs text-slate-200 pr-2"></div>
                        </div>

                        <!-- SPACIOUS TABBED CONTROL ROOM HUB -->
                        <div id="admin-panel" class="hidden lg:col-span-7 glass-card border-2 border-purple-500/45 rounded-xl p-3.5 flex flex-col h-[288px] shadow-xl">
                            <div class="flex flex-wrap justify-between items-center gap-1.5 mb-2.5 border-b border-slate-800 pb-2 shrink-0">
                                <div class="flex items-center flex-wrap gap-1.5">
                                    <span class="text-xs font-extrabold text-amber-400 uppercase mr-1 flex items-center gap-1">
                                        <i class="fa-solid fa-building-shield text-amber-300"></i> Control Room:
                                    </span>
                                    <button type="button" onclick="switchSupervisorTab('officers')" id="sup-tab-officers" class="px-2.5 py-1 rounded-lg text-xs font-bold bg-amber-500 text-slate-950 cursor-pointer transition shadow">
                                        👮 Officers <span id="sup-count-officers" class="ml-0.5 text-[10px]">(0)</span>
                                    </button>
                                    <button type="button" onclick="switchSupervisorTab('ptt')" id="sup-tab-ptt" class="px-2.5 py-1 rounded-lg text-xs font-bold bg-[#060c18] border border-slate-700 text-slate-200 hover:text-white cursor-pointer transition">
                                        🎙️ PTT Queue <span id="sup-count-ptt" class="ml-0.5 text-[10px] text-amber-300">(0)</span>
                                    </button>
                                    <button type="button" onclick="switchSupervisorTab('clearances')" id="sup-tab-clearances" class="px-2.5 py-1 rounded-lg text-xs font-bold bg-[#060c18] border border-slate-700 text-slate-200 hover:text-white cursor-pointer transition">
                                        ✅ Clearances <span id="sup-count-clearances" class="ml-0.5 text-[10px] text-emerald-300">(0)</span>
                                    </button>
                                    <button type="button" onclick="switchSupervisorTab('feedbacks')" id="sup-tab-feedbacks" class="px-2.5 py-1 rounded-lg text-xs font-bold bg-[#060c18] border border-slate-700 text-slate-200 hover:text-white cursor-pointer transition">
                                        💬 Feedbacks <span id="sup-count-feedbacks" class="ml-0.5 text-[10px] text-cyan-300">(0)</span>
                                    </button>
                                </div>
                                <div class="flex items-center gap-2">
                                    <button type="button" onclick="toggleExpandSupervisorWidth()" id="btn-expand-sup" class="bg-slate-800 hover:bg-slate-700 border border-purple-400/40 text-purple-200 text-[10px] font-bold px-2 py-1 rounded cursor-pointer" title="Toggle Full Width">
                                        ⤢ Expand
                                    </button>
                                    <button type="button" onclick="toggleSupervisorDrawer()" class="text-xs text-slate-400 hover:text-white px-1 cursor-pointer" title="Hide Control Room Hub">✕</button>
                                </div>
                            </div>

                            <div id="sup-content-officers" class="tactical-scroll flex-1 bg-[#060c18] border border-slate-800 rounded-lg p-3 space-y-2 text-xs text-slate-200 pr-2">
                                <div id="admin-officers-list" class="space-y-2"></div>
                            </div>
                            <div id="sup-content-ptt" class="hidden tactical-scroll flex-1 bg-[#060c18] border border-slate-800 rounded-lg p-3 space-y-2 text-xs text-slate-200 pr-2">
                                <div id="admin-ptt-list" class="space-y-2"></div>
                            </div>
                            <div id="sup-content-clearances" class="hidden tactical-scroll flex-1 bg-[#060c18] border border-slate-800 rounded-lg p-3 space-y-2 text-xs text-slate-200 pr-2">
                                <div id="admin-clearances-list" class="space-y-2"></div>
                            </div>
                            <div id="sup-content-feedbacks" class="hidden tactical-scroll flex-1 bg-[#060c18] border border-slate-800 rounded-lg p-3 space-y-2 text-xs text-slate-200 pr-2">
                                <div id="admin-feedbacks-list" class="space-y-2"></div>
                            </div>
                        </div>

                    </div>
                </div>
            </div>

            <footer class="bg-[#0a1326] border-t border-amber-500/20 py-2 text-center text-xs text-slate-400 shrink-0">
                நான்காம் காவல் நண்பன் • <span class="text-amber-400 font-semibold">Designed & Developed by Mohamed Hamdan</span>
            </footer>
        </div>

        <!-- DEDICATED WALKIE-TALKIE PTT VOICE NOTES MODAL -->
        <div id="voice-notes-modal" class="fixed inset-0 bg-black/85 backdrop-blur-sm z-50 flex items-center justify-center p-4 hidden">
            <div class="bg-[#0d182e] border-2 border-amber-500/60 rounded-2xl max-w-3xl w-full p-5 space-y-3 shadow-2xl flex flex-col max-h-[86vh]">
                <div class="flex justify-between items-center border-b border-slate-800 pb-2.5">
                    <div>
                        <h3 class="font-bold text-sm text-amber-400 uppercase flex items-center gap-2">
                            <i class="fa-solid fa-walkie-talkie text-amber-300"></i> 🎙️ Control Room Walkie-Talkie PTT Voice Queue (On-Demand Playback)
                        </h3>
                        <p class="text-[11px] text-slate-400 mt-0.5">Voice notes never play automatically. Click "Play Voice Note" to listen and mark as Listened.</p>
                    </div>
                    <button type="button" onclick="toggleVoiceNotesModal(false)" class="text-slate-400 hover:text-white text-xs cursor-pointer"><i class="fa-solid fa-xmark text-lg"></i></button>
                </div>

                <div class="grid grid-cols-2 gap-3 text-center">
                    <div class="bg-[#070e1c] border border-amber-500/40 rounded-xl py-2">
                        <div id="ptt-new-count" class="text-lg font-black text-amber-400">0</div>
                        <div class="text-[10px] font-bold text-red-400 uppercase">🔴 NEW / UNHEARD VOICE NOTES</div>
                    </div>
                    <div class="bg-[#070e1c] border border-emerald-500/40 rounded-xl py-2">
                        <div id="ptt-listened-count" class="text-lg font-black text-emerald-400">0</div>
                        <div class="text-[10px] font-bold text-emerald-400 uppercase">✅ ALREADY LISTENED</div>
                    </div>
                </div>

                <div class="bg-[#070e1c] border border-cyan-500/30 rounded-xl p-2.5 space-y-2">
                    <div class="text-[10px] font-bold text-cyan-300 uppercase">🎙️ Transmit Tactical PTT Voice Note to Control Room Queue:</div>
                    <div class="flex flex-wrap gap-1.5">
                        <button type="button" onclick="sendWebVoiceNote('Tow Crane required immediately at signal junction.')" class="bg-slate-800 hover:bg-slate-700 border border-cyan-500/40 text-[10px] text-slate-200 px-2 py-1 rounded cursor-pointer">🎙️ "Tow Crane Required"</button>
                        <button type="button" onclick="sendWebVoiceNote('108 Emergency Ambulance approaching — clearing green corridor.')" class="bg-slate-800 hover:bg-slate-700 border border-cyan-500/40 text-[10px] text-slate-200 px-2 py-1 rounded cursor-pointer">🎙️ "108 Ambulance Approaching"</button>
                        <button type="button" onclick="sendWebVoiceNote('Heavy multi-lane congestion — diverting traffic to bypass.')" class="bg-slate-800 hover:bg-slate-700 border border-cyan-500/40 text-[10px] text-slate-200 px-2 py-1 rounded cursor-pointer">🎙️ "Diverting Traffic"</button>
                    </div>
                    <div class="flex gap-2 pt-0.5">
                        <input type="text" id="web-ptt-input" placeholder="Or type custom Walkie-Talkie voice dispatch..." class="flex-1 bg-[#0d182e] border border-amber-500/30 rounded-lg px-3 py-1 text-xs text-white">
                        <button type="button" onclick="sendWebVoiceNote(null)" class="bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold px-3 py-1 rounded-lg text-xs cursor-pointer">📡 Queue Voice Note</button>
                    </div>
                </div>

                <div id="voice-notes-modal-list" class="tactical-scroll flex-1 space-y-2 pr-2"></div>
            </div>
        </div>

        <!-- LIVE YOLOv8 VISUALS + DIRECT TRAFFIC SIGNAL CONTROL MODAL -->
        <div id="yolo-live-modal" class="fixed inset-0 bg-black/85 backdrop-blur-sm z-50 flex items-center justify-center p-4 hidden">
            <div class="bg-[#0d182e] border-2 border-cyan-500/60 rounded-2xl max-w-5xl w-full p-5 space-y-3 shadow-2xl relative max-h-[92vh] overflow-y-auto">
                <div class="flex justify-between items-center border-b border-slate-800 pb-2.5">
                    <div>
                        <h3 id="yolo-modal-heading" class="font-bold text-sm text-cyan-400 uppercase flex items-center gap-2">
                            <i class="fa-solid fa-traffic-light text-amber-400"></i> Control Room Live YOLOv8 Visuals & Direct Traffic Signal Controller
                        </h3>
                        <p id="yolo-live-location" class="text-xs text-amber-300 font-semibold mt-0.5">📍 Traffic Signal: Connecting...</p>
                    </div>
                    <button type="button" onclick="toggleYoloModal(false, null)" class="text-slate-400 hover:text-white text-xs cursor-pointer"><i class="fa-solid fa-xmark text-lg"></i></button>
                </div>

                <!-- SINGLE SIGNAL VIEW + INTERACTIVE 4-LAMP TRAFFIC SIGNAL CONTROLLER -->
                <div id="yolo-single-container" class="space-y-3">
                    <div class="grid grid-cols-1 md:grid-cols-12 gap-3 items-center bg-[#070e1c] p-3 rounded-xl border border-slate-800">
                        <div class="md:col-span-5 flex items-center gap-4 border-r border-slate-800 pr-3">
                            <div class="signal-housing flex flex-col items-center gap-2">
                                <div id="modal-lamp-blue" onclick="setGlobalSignalControl(null, 'A')" title="Blue AI Lamp (Off / Blink / Steady / Strobe)" class="signal-lamp lamp-blue-off"></div>
                                <div class="w-full h-[1px] bg-slate-700"></div>
                                <div id="modal-lamp-red" onclick="setGlobalSignalControl('R', null)" title="Click to Force RED" class="signal-lamp lamp-red-off"></div>
                                <div id="modal-lamp-yellow" onclick="setGlobalSignalControl('Y', null)" title="Click to Force YELLOW" class="signal-lamp lamp-yellow-off"></div>
                                <div id="modal-lamp-green" onclick="setGlobalSignalControl('G', null)" title="Click to Force GREEN (108 Corridor)" class="signal-lamp lamp-green-on"></div>
                            </div>
                            <div class="space-y-1.5 flex-1">
                                <div class="text-[10px] font-extrabold text-amber-400 uppercase">🚦 Direct Signal Phase Control</div>
                                <div class="grid grid-cols-2 gap-1.5">
                                    <button type="button" onclick="setGlobalSignalControl('R', null)" class="bg-red-700/40 hover:bg-red-600 border border-red-500 text-red-200 hover:text-white text-[10px] font-bold py-1 px-2 rounded cursor-pointer">🔴 Force RED</button>
                                    <button type="button" onclick="setGlobalSignalControl('Y', null)" class="bg-amber-600/40 hover:bg-amber-500 border border-amber-400 text-amber-200 hover:text-slate-950 text-[10px] font-bold py-1 px-2 rounded cursor-pointer">🟡 YELLOW</button>
                                    <button type="button" onclick="setGlobalSignalControl('G', null)" class="bg-emerald-700/40 hover:bg-emerald-600 border border-emerald-400 text-emerald-200 hover:text-white text-[10px] font-bold py-1 px-2 rounded cursor-pointer">🟢 GREEN (108)</button>
                                    <button type="button" onclick="setGlobalSignalControl('C', 'AUTO')" class="bg-slate-700 hover:bg-slate-600 border border-slate-500 text-slate-200 text-[10px] font-bold py-1 px-2 rounded cursor-pointer">🔄 Auto Cycle</button>
                                </div>
                                <div class="text-[10px] font-extrabold text-cyan-400 uppercase pt-1">🔵 Blue AI Lamp Mode</div>
                                <div class="flex flex-wrap gap-1">
                                    <button type="button" onclick="setGlobalSignalControl(null, '0')" class="bg-slate-800 hover:bg-slate-700 text-[9px] text-slate-300 px-2 py-0.5 rounded border border-slate-700 cursor-pointer">Off ('0')</button>
                                    <button type="button" onclick="setGlobalSignalControl(null, 'B')" class="bg-blue-900/50 hover:bg-blue-700 text-[9px] text-blue-200 px-2 py-0.5 rounded border border-blue-500/40 cursor-pointer">Blink ('B')</button>
                                    <button type="button" onclick="setGlobalSignalControl(null, 'S')" class="bg-blue-700/60 hover:bg-blue-600 text-[9px] text-white px-2 py-0.5 rounded border border-blue-400 cursor-pointer">Steady ('S')</button>
                                    <button type="button" onclick="setGlobalSignalControl(null, 'A')" class="bg-cyan-600/70 hover:bg-cyan-500 text-[9px] text-slate-950 font-black px-2 py-0.5 rounded border border-white cursor-pointer">Strobe ('A')</button>
                                </div>
                            </div>
                        </div>

                        <div class="md:col-span-7 grid grid-cols-3 gap-2 text-center text-xs">
                            <div class="bg-[#0d182e] p-2.5 rounded-lg border border-slate-800">
                                <span class="text-slate-400 block text-[10px]">BLUE AI LAMP STATUS</span>
                                <strong id="yolo-live-stage" class="text-cyan-300 text-xs">--</strong>
                            </div>
                            <div class="bg-[#0d182e] p-2.5 rounded-lg border border-slate-800">
                                <span class="text-slate-400 block text-[10px]">OBSTRUCTION TIMER</span>
                                <strong id="yolo-live-timer" class="text-amber-400 text-sm">0.0s</strong>
                            </div>
                            <div class="bg-[#0d182e] p-2.5 rounded-lg border border-slate-800">
                                <span class="text-slate-400 block text-[10px]">OBJECTS IN ROI</span>
                                <strong id="yolo-live-objects" class="text-red-400 text-xs">0</strong>
                            </div>
                        </div>
                    </div>

                    <div class="bg-black rounded-xl overflow-hidden border border-cyan-500/30 flex items-center justify-center min-h-[300px] relative">
                        <img id="yolo-live-img" src="" alt="Waiting for yolo_live_detector.py..." class="w-full max-h-[380px] object-contain hidden">
                        <div id="yolo-live-placeholder" class="text-center p-6 text-slate-400 text-xs">
                            <i class="fa-solid fa-satellite-dish text-2xl text-cyan-400 mb-2 block animate-bounce"></i>
                            Waiting for live frames from <code>python yolo_live_detector.py</code>...
                        </div>
                    </div>
                </div>

                <!-- MULTI-SIGNAL MATRIX + INDIVIDUAL SIGNAL CONTROLLERS -->
                <div id="yolo-matrix-container" class="hidden grid grid-cols-1 md:grid-cols-2 gap-3"></div>
            </div>
        </div>

        <!-- OFFICER SELF PROFILE EDIT & FEEDBACK MODAL -->
        <div id="profile-modal" class="fixed inset-0 bg-black/85 backdrop-blur-sm z-50 flex items-center justify-center p-4 hidden">
            <div class="bg-[#0d182e] border-2 border-amber-500/50 rounded-2xl max-w-md w-full p-5 space-y-3 shadow-2xl relative max-h-[90vh] overflow-y-auto">
                <div class="flex justify-between items-center border-b border-slate-800 pb-2.5">
                    <h3 class="font-bold text-sm text-amber-400 uppercase"><i class="fa-solid fa-id-card mr-2"></i>Profile & Settings</h3>
                    <button type="button" onclick="closeProfileModal()" class="text-slate-400 hover:text-white text-xs cursor-pointer"><i class="fa-solid fa-xmark text-base"></i></button>
                </div>
                <form id="profile-form" onsubmit="updateProfile(event)" class="space-y-2.5">
                    <div class="flex flex-col items-center justify-center space-y-1.5">
                        <div class="w-16 h-16 rounded-full bg-[#070e1c] border-2 border-amber-400 overflow-hidden flex items-center justify-center">
                            <img id="profile-avatar-preview" src="/logo.png" class="w-full h-full object-cover">
                        </div>
                        <label class="text-[10px] text-amber-300 cursor-pointer hover:underline">
                            Change Profile Photo <input type="file" id="profile-photo-input" accept="image/*" class="hidden" onchange="previewAvatar(event)">
                        </label>
                    </div>
                    <div class="grid grid-cols-2 gap-2">
                        <div>
                            <label class="block text-[10px] font-semibold text-amber-400 uppercase mb-0.5">Full Name</label>
                            <input type="text" id="profile-name" required class="w-full bg-[#070e1c] border border-amber-500/30 rounded-lg px-2.5 py-1.5 text-xs text-white">
                        </div>
                        <div>
                            <label class="block text-[10px] font-semibold text-amber-400 uppercase mb-0.5">Designation</label>
                            <select id="profile-designation" class="w-full bg-[#070e1c] border border-amber-500/30 rounded-lg px-2 py-1.5 text-xs text-white">
                                <option value="Inspector">Inspector</option>
                                <option value="Sub-Inspector (SI)">Sub-Inspector (SI)</option>
                                <option value="Assistant Commissioner (ACP)">Assistant Commissioner (ACP)</option>
                                <option value="Traffic Head Constable">Traffic Head Constable</option>
                                <option value="Traffic Constable">Traffic Constable</option>
                                <option value="Control Room Supervisor">Control Room Supervisor</option>
                            </select>
                        </div>
                    </div>
                    <div class="grid grid-cols-2 gap-2">
                        <div>
                            <label class="block text-[10px] font-semibold text-amber-400 uppercase mb-0.5">Badge ID</label>
                            <input type="text" id="profile-badge" disabled class="w-full bg-[#070e1c]/50 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs text-slate-400 cursor-not-allowed">
                        </div>
                        <div>
                            <label class="block text-[10px] font-semibold text-amber-400 uppercase mb-0.5">Mobile Number</label>
                            <input type="tel" id="profile-mobile" required class="w-full bg-[#070e1c] border border-amber-500/30 rounded-lg px-2.5 py-1.5 text-xs text-white">
                        </div>
                    </div>
                    <div>
                        <label class="block text-[10px] font-semibold text-amber-400 uppercase mb-0.5">Official Email</label>
                        <input type="email" id="profile-email" required class="w-full bg-[#070e1c] border border-amber-500/30 rounded-lg px-2.5 py-1.5 text-xs text-white">
                    </div>
                    <div>
                        <label class="block text-[10px] font-semibold text-amber-400 uppercase mb-0.5">New Password (Optional)</label>
                        <div class="relative">
                            <input type="password" id="profile-password" placeholder="Leave blank to keep current" class="w-full bg-[#070e1c] border border-amber-500/30 rounded-lg px-2.5 py-1.5 pr-9 text-xs text-white">
                            <button type="button" onclick="togglePasswordVisibility('profile-password', 'profile-eye')" class="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-amber-400 cursor-pointer text-xs">
                                <i id="profile-eye" class="fa-solid fa-eye"></i>
                            </button>
                        </div>
                    </div>
                    <div class="flex space-x-2 pt-1.5">
                        <button type="submit" class="flex-1 bg-amber-600 hover:bg-amber-500 text-slate-950 font-bold py-1.5 rounded-lg text-xs cursor-pointer shadow">Save Changes</button>
                        <button type="button" onclick="closeProfileModal()" class="bg-slate-700 hover:bg-slate-600 text-white px-4 py-1.5 rounded-lg text-xs cursor-pointer">Cancel</button>
                    </div>
                    <div id="profile-msg" class="text-center text-xs text-emerald-400 hidden"></div>
                </form>

                <div id="officer-feedback-box" class="border-t border-slate-800 pt-2.5 space-y-2">
                    <h4 class="text-[11px] font-bold text-cyan-400 uppercase"><i class="fa-solid fa-comment-medical mr-1"></i>Submit App Feedback to Control Room</h4>
                    <div class="flex gap-1.5">
                        <select id="web-fb-rating" class="bg-[#070e1c] border border-cyan-500/40 rounded px-2 py-1 text-xs text-amber-300">
                            <option value="5">★★★★★ (5)</option>
                            <option value="4">★★★★☆ (4)</option>
                            <option value="3">★★★☆☆ (3)</option>
                            <option value="2">★★☆☆☆ (2)</option>
                            <option value="1">★☆☆☆☆ (1)</option>
                        </select>
                        <input type="text" id="web-fb-msg" placeholder="Share feedback..." class="flex-1 bg-[#070e1c] border border-cyan-500/40 rounded px-2.5 py-1 text-xs text-white">
                        <button type="button" onclick="submitWebFeedback()" class="bg-cyan-600 hover:bg-cyan-500 text-white font-bold px-3 py-1 rounded text-xs cursor-pointer">Send</button>
                    </div>
                </div>
            </div>
        </div>

        <!-- CONTROL ROOM EDIT OR DELETE ANY OFFICER PROFILE MODAL -->
        <div id="admin-edit-modal" class="fixed inset-0 bg-black/85 backdrop-blur-sm z-50 flex items-center justify-center p-4 hidden">
            <div class="bg-[#0d182e] border-2 border-blue-500/50 rounded-2xl max-w-md w-full p-5 space-y-3 shadow-2xl relative">
                <div class="flex justify-between items-center border-b border-slate-800 pb-2.5">
                    <h3 class="font-bold text-sm text-blue-400 uppercase"><i class="fa-solid fa-user-pen mr-2"></i>Control Room: Edit Officer Profile</h3>
                    <button type="button" onclick="closeAdminEditModal()" class="text-slate-400 hover:text-white text-xs cursor-pointer"><i class="fa-solid fa-xmark text-base"></i></button>
                </div>
                <form onsubmit="submitAdminOfficerEdit(event)" class="space-y-2.5">
                    <div class="grid grid-cols-2 gap-2">
                        <div>
                            <label class="block text-[10px] font-semibold text-amber-400 uppercase mb-0.5">Target Badge ID</label>
                            <input type="text" id="admin-edit-badge" disabled class="w-full bg-[#070e1c]/60 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs text-slate-400">
                        </div>
                        <div>
                            <label class="block text-[10px] font-semibold text-amber-400 uppercase mb-0.5">Rank / Designation</label>
                            <select id="admin-edit-designation" class="w-full bg-[#070e1c] border border-amber-500/30 rounded-lg px-2 py-1.5 text-xs text-white">
                                <option value="Inspector">Inspector</option>
                                <option value="Sub-Inspector (SI)">Sub-Inspector (SI)</option>
                                <option value="Assistant Commissioner (ACP)">Assistant Commissioner (ACP)</option>
                                <option value="Traffic Head Constable">Traffic Head Constable</option>
                                <option value="Traffic Constable">Traffic Constable</option>
                                <option value="Control Room Supervisor">Control Room Supervisor</option>
                            </select>
                        </div>
                    </div>
                    <div>
                        <label class="block text-[10px] font-semibold text-amber-400 uppercase mb-0.5">Officer Full Name</label>
                        <input type="text" id="admin-edit-name" required class="w-full bg-[#070e1c] border border-amber-500/30 rounded-lg px-2.5 py-1.5 text-xs text-white">
                    </div>
                    <div class="grid grid-cols-2 gap-2">
                        <div>
                            <label class="block text-[10px] font-semibold text-amber-400 uppercase mb-0.5">Mobile Number</label>
                            <input type="text" id="admin-edit-mobile" required class="w-full bg-[#070e1c] border border-amber-500/30 rounded-lg px-2.5 py-1.5 text-xs text-white">
                        </div>
                        <div>
                            <label class="block text-[10px] font-semibold text-amber-400 uppercase mb-0.5">Account Status</label>
                            <select id="admin-edit-status" class="w-full bg-[#070e1c] border border-amber-500/30 rounded-lg px-2 py-1.5 text-xs text-white">
                                <option value="ACTIVE">ACTIVE</option>
                                <option value="PENDING APPROVAL">PENDING APPROVAL</option>
                            </select>
                        </div>
                    </div>
                    <div>
                        <label class="block text-[10px] font-semibold text-amber-400 uppercase mb-0.5">Official Email</label>
                        <input type="email" id="admin-edit-email" required class="w-full bg-[#070e1c] border border-amber-500/30 rounded-lg px-2.5 py-1.5 text-xs text-white">
                    </div>
                    <div>
                        <label class="block text-[10px] font-semibold text-amber-400 uppercase mb-0.5">Reset Password (Optional)</label>
                        <div class="relative">
                            <input type="password" id="admin-edit-password" placeholder="Leave blank to keep existing" class="w-full bg-[#070e1c] border border-amber-500/30 rounded-lg px-2.5 py-1.5 pr-9 text-xs text-white">
                            <button type="button" onclick="togglePasswordVisibility('admin-edit-password', 'admin-edit-eye')" class="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-amber-400 cursor-pointer text-xs">
                                <i id="admin-edit-eye" class="fa-solid fa-eye"></i>
                            </button>
                        </div>
                    </div>
                    <div class="flex space-x-2 pt-1.5">
                        <button type="submit" class="flex-1 bg-blue-600 hover:bg-blue-500 text-white font-bold py-1.5 rounded-lg text-xs cursor-pointer shadow">Update Officer</button>
                        <button type="button" onclick="deleteOfficerFromModal()" class="bg-red-600 hover:bg-red-500 text-white font-bold px-3 py-1.5 rounded-lg text-xs cursor-pointer shadow flex items-center gap-1">
                            <i class="fa-solid fa-trash"></i> Delete
                        </button>
                        <button type="button" onclick="closeAdminEditModal()" class="bg-slate-700 hover:bg-slate-600 text-white px-3 py-1.5 rounded-lg text-xs cursor-pointer">Cancel</button>
                    </div>
                </form>
            </div>
        </div>

        <!-- CLEARANCES MODAL (OFFICERS ONLY) -->
        <div id="clearances-modal" class="fixed inset-0 bg-black/85 backdrop-blur-sm z-50 flex items-center justify-center p-4 hidden">
            <div class="bg-[#0d182e] border-2 border-emerald-500/50 rounded-2xl max-w-2xl w-full p-5 space-y-3 shadow-2xl flex flex-col max-h-[85vh]">
                <div class="flex justify-between items-center border-b border-slate-800 pb-2.5">
                    <h3 class="font-bold text-sm text-emerald-400 uppercase"><i class="fa-solid fa-clipboard-check mr-2"></i>My Last 10 Blockade Clearances</h3>
                    <button type="button" onclick="closeClearancesModal()" class="text-slate-400 hover:text-white text-xs cursor-pointer"><i class="fa-solid fa-xmark text-base"></i></button>
                </div>
                <div id="clearances-list" class="tactical-scroll flex-1 space-y-2.5 pr-2"></div>
            </div>
        </div>

        <!-- CAMERA CLEARANCE MODAL -->
        <div id="photo-modal" class="fixed inset-0 bg-black/85 backdrop-blur-sm z-50 flex items-center justify-center p-4 hidden">
            <div class="bg-[#0d182e] border-2 border-emerald-500/50 rounded-xl max-w-sm w-full p-5 space-y-4">
                <div class="text-center">
                    <div class="inline-flex p-3 bg-emerald-500/20 text-emerald-400 rounded-full mb-2 text-xl">
                        <i class="fa-solid fa-camera-retro"></i>
                    </div>
                    <h3 class="font-bold text-sm text-amber-400 uppercase">Mandatory Live Camera Capture</h3>
                    <p class="text-xs text-slate-300 mt-1">Gallery uploads are disabled to prevent false clearance. Take a live photo of the cleared road.</p>
                </div>
                
                <input type="file" id="clearance-file" accept="image/*" capture="environment" class="w-full text-xs text-slate-300 bg-[#070e1c] border border-emerald-500/40 rounded p-2.5">
                
                <div class="flex space-x-2 pt-2">
                    <button type="button" onclick="submitClearancePhoto()" class="flex-1 bg-emerald-600 hover:bg-emerald-500 text-white font-bold py-2 rounded text-xs cursor-pointer shadow">Submit Live Proof</button>
                    <button type="button" onclick="closePhotoModal()" class="bg-slate-700 hover:bg-slate-600 text-white px-3 py-2 rounded text-xs cursor-pointer">Cancel</button>
                </div>
            </div>
        </div>

        <script>
            let authToken = localStorage.getItem('token_8002') || '';
            let currentUserStatus = 'ACTIVE';
            let map, markersLayer;
            let generatedOTP = '';
            let tempRegData = {};
            let activeResolvingId = null;
            let lastSeenNotificationId = null;
            let cachedOfficers = [];
            let yoloPollInterval = null;
            let targetYoloLocation = null;
            let cachedVoiceNotes = [];
            let isSupExpandedFull = false;
            let activeAudioObj = null;
            let localListenedPtt = JSON.parse(localStorage.getItem('listened_ptt_web_8002') || '{}');

            let lastBlockadesHash = '';
            let lastNotifsHash = '';
            let lastVoiceHash = '';
            let lastAdminHash = '';

            if ('speechSynthesis' in window) {
                window.speechSynthesis.getVoices();
                window.speechSynthesis.onvoiceschanged = () => window.speechSynthesis.getVoices();
            }

            // ============================================================================
            // NATURAL INDIAN LADY TAMIL + ENGLISH VOICE ENGINE (Matches Mobile App Lady Voice!)
            // ============================================================================
            function playLadyTtsSequence(segments) {
                if (!segments || segments.length === 0) return;
                if (activeAudioObj) {
                    try { activeAudioObj.pause(); } catch (e) {}
                }
                if ('speechSynthesis' in window) {
                    window.speechSynthesis.cancel();
                }

                let idx = 0;
                function playNext() {
                    if (idx >= segments.length) return;
                    const seg = segments[idx++];
                    const url = `/api/tts-lady?lang=${encodeURIComponent(seg.lang)}&text=${encodeURIComponent(seg.text)}`;
                    const audio = new Audio(url);
                    activeAudioObj = audio;
                    audio.playbackRate = seg.rate || 1.0;
                    audio.onended = () => playNext();
                    audio.onerror = () => {
                        // Fallback to female-pitched browser voice if offline
                        if ('speechSynthesis' in window) {
                            const voices = window.speechSynthesis.getVoices();
                            const femaleVoice = voices.find(v =>
                                v.name.toLowerCase().includes('heera') ||
                                v.name.toLowerCase().includes('zira') ||
                                v.name.toLowerCase().includes('female') ||
                                v.name.toLowerCase().includes('google') ||
                                (v.lang && v.lang.toLowerCase().includes('ta'))
                            ) || voices[0];
                            const u = new SpeechSynthesisUtterance(seg.fallbackText || seg.text);
                            if (femaleVoice) u.voice = femaleVoice;
                            u.lang = seg.lang === 'ta' ? 'ta-IN' : 'en-IN';
                            u.pitch = 1.2;
                            u.rate = 0.92;
                            u.onend = () => playNext();
                            window.speechSynthesis.speak(u);
                        }
                    };
                    audio.play().catch(() => audio.onerror());
                }
                playNext();
            }

            function playTacticalSirenAndVoice(customMessage) {
                if (!customMessage) return;
                if (customMessage.includes('[PTT VOICE]') || customMessage.includes('[VOICE NOTE]')) {
                    return;
                }

                const isBlockadeAlert =
                    customMessage.includes('[LIVE YOLO MODEL ALERT]') ||
                    customMessage.includes('[EDGE-AI YOLO]') ||
                    customMessage.includes('[SIMULATED AI]') ||
                    customMessage.includes('[YOLO AI]');
                const isBackupAlert = customMessage.includes('[BACKUP SOS]');
                const isGreenCorridor = customMessage.includes('[GREEN CORRIDOR]');

                if (isBlockadeAlert || isBackupAlert || isGreenCorridor) {
                    try {
                        const sirenAudio = new Audio('https://assets.mixkit.co/active_storage/sfx/2869/2869-preview.mp3');
                        sirenAudio.volume = 0.55;
                        sirenAudio.play().catch(err => {});
                    } catch (e) {}
                }

                let signalLocation = 'Traffic Signal';
                if (customMessage.includes('@')) {
                    signalLocation = customMessage.split('@')[1].split('(')[0].trim();
                }

                if (isBlockadeAlert) {
                    playLadyTtsSequence([
                        {
                            lang: 'ta',
                            text: 'காவல்துறை அவசர எச்சரிக்கை. சிக்னலில் போக்குவரத்து தடை ஏற்பட்டுள்ளது. உடனடியாக செல்லவும்.',
                            fallbackText: 'Kaaval thurai avasara echarikkai. Signal-il pokkuvarathu thadai. Udanadiyaaga sellavum.',
                            rate: 1.0
                        },
                        {
                            lang: 'en-IN',
                            text: `Police Emergency Alert! Blockade at ${signalLocation}.`,
                            rate: 1.0
                        }
                    ]);
                } else if (isBackupAlert) {
                    playLadyTtsSequence([
                        {
                            lang: 'ta',
                            text: 'காவல்துறை அவசர உதவி அழைப்பு. சிக்னலில் கூடுதல் காவலர்கள் உடனடியாக உதவிக்கு வரவும்.',
                            fallbackText: 'Kaaval thurai avasara udhavi azhaippu. Signal-il kooduthal kaavalargal udanadiyaaga udhavikku varavum.',
                            rate: 1.0
                        },
                        {
                            lang: 'en-IN',
                            text: `Officer Backup requested at ${signalLocation}.`,
                            rate: 1.0
                        }
                    ]);
                } else if (isGreenCorridor) {
                    playLadyTtsSequence([
                        {
                            lang: 'ta',
                            text: 'நூற்றி எட்டு ஆம்புலன்ஸ் பசுமை வழித்தடம் செயல்படுத்தப்பட்டது.',
                            fallbackText: '108 Ambulance Green Corridor Activated.',
                            rate: 1.0
                        },
                        {
                            lang: 'en-IN',
                            text: `Green Corridor open at ${signalLocation}.`,
                            rate: 1.0
                        }
                    ]);
                }
            }

            // ============================================================================
            // ZERO-LAG SURGICAL DOM SIGNAL CONTROL (Updates Lamps in 0.1ms Without Freezing Page!)
            // ============================================================================
            function getBlueLampCssClass(blueCode) {
                if (blueCode === 'A') return 'lamp-blue-strobe';
                if (blueCode === 'S') return 'lamp-blue-steady';
                if (blueCode === 'B') return 'lamp-blue-blink';
                return 'lamp-blue-off';
            }

            function getBlueLampLabel(blueCode) {
                if (blueCode === 'A') return '🚨 STROBE (>45s)';
                if (blueCode === 'S') return '🔵 STEADY (15-45s)';
                if (blueCode === 'B') return '⚡ BLINK (0-15s)';
                return '⚪ CLEAR (OFF)';
            }

            function updateSignalDomInstantly(blockadeId, signalColor, blueMode) {
                if (signalColor) {
                    const rEl = document.getElementById(`inc-lamp-r-${blockadeId}`);
                    const yEl = document.getElementById(`inc-lamp-y-${blockadeId}`);
                    const gEl = document.getElementById(`inc-lamp-g-${blockadeId}`);
                    if (rEl) rEl.className = `signal-lamp ${signalColor === 'R' ? 'lamp-red-on' : 'lamp-red-off'}`;
                    if (yEl) yEl.className = `signal-lamp ${signalColor === 'Y' ? 'lamp-yellow-on' : 'lamp-yellow-off'}`;
                    if (gEl) gEl.className = `signal-lamp ${(signalColor === 'G' || signalColor === 'C') ? 'lamp-green-on' : 'lamp-green-off'}`;
                }
                if (blueMode) {
                    const bEl = document.getElementById(`inc-lamp-b-${blockadeId}`);
                    const lblEl = document.getElementById(`inc-blue-lbl-${blockadeId}`);
                    const effBlue = blueMode === 'AUTO' ? 'B' : blueMode;
                    if (bEl) bEl.className = `signal-lamp ${getBlueLampCssClass(effBlue)}`;
                    if (lblEl) lblEl.innerText = `🔵 ${getBlueLampLabel(effBlue)}`;
                }
            }

            function setIncidentSignalPhase(blockadeId, signalColor, blueMode) {
                // 1. Update lamps in DOM immediately (0ms lag, no full DOM rebuild!)
                updateSignalDomInstantly(blockadeId, signalColor, blueMode);

                // 2. Fire non-blocking request to FastAPI + ESP8266 serial bridge
                fetch(`/blockades/${blockadeId}/signal-phase`, {
                    method: 'POST',
                    headers: {
                        'Authorization': 'Bearer ' + authToken,
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        signal_color: signalColor,
                        blue_mode: blueMode
                    })
                }).catch(() => {});
            }

            function setGlobalSignalControl(signalColor, blueMode, locName = null) {
                // 1. Update modal lamps immediately (0ms lag!)
                if (signalColor) {
                    const mr = document.getElementById('modal-lamp-red');
                    const my = document.getElementById('modal-lamp-yellow');
                    const mg = document.getElementById('modal-lamp-green');
                    if (mr) mr.className = `signal-lamp ${signalColor === 'R' ? 'lamp-red-on' : 'lamp-red-off'}`;
                    if (my) my.className = `signal-lamp ${signalColor === 'Y' ? 'lamp-yellow-on' : 'lamp-yellow-off'}`;
                    if (mg) mg.className = `signal-lamp ${(signalColor === 'G' || signalColor === 'C') ? 'lamp-green-on' : 'lamp-green-off'}`;
                }
                if (blueMode) {
                    const mb = document.getElementById('modal-lamp-blue');
                    const effBlue = blueMode === 'AUTO' ? '0' : blueMode;
                    if (mb) mb.className = `signal-lamp ${getBlueLampCssClass(effBlue)}`;
                }

                // 2. Send non-blocking command to backend
                const targetLoc = locName || targetYoloLocation || null;
                fetch('/api/signal-control', {
                    method: 'POST',
                    headers: {
                        'Authorization': 'Bearer ' + authToken,
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        signal_color: signalColor,
                        blue_mode: blueMode,
                        location_name: targetLoc
                    })
                }).catch(() => {});
            }

            function switchSupervisorTab(tabName) {
                ['officers', 'ptt', 'clearances', 'feedbacks'].forEach(t => {
                    const btn = document.getElementById('sup-tab-' + t);
                    const box = document.getElementById('sup-content-' + t);
                    if (!btn || !box) return;
                    if (t === tabName) {
                        btn.className = 'px-2.5 py-1 rounded-lg text-xs font-bold bg-amber-500 text-slate-950 cursor-pointer transition shadow';
                        box.classList.remove('hidden');
                    } else {
                        btn.className = 'px-2.5 py-1 rounded-lg text-xs font-bold bg-[#060c18] border border-slate-700 text-slate-200 hover:text-white cursor-pointer transition';
                        box.classList.add('hidden');
                    }
                });
            }

            function toggleExpandSupervisorWidth() {
                const panel = document.getElementById('admin-panel');
                const wirelessCol = document.getElementById('wireless-col');
                const btn = document.getElementById('btn-expand-sup');
                isSupExpandedFull = !isSupExpandedFull;
                if (isSupExpandedFull) {
                    panel.classList.remove('lg:col-span-7');
                    panel.classList.add('lg:col-span-12', 'h-[360px]');
                    wirelessCol.classList.remove('lg:col-span-5');
                    wirelessCol.classList.add('lg:col-span-12');
                    if (btn) btn.innerText = '⤡ Split View';
                } else {
                    panel.classList.remove('lg:col-span-12', 'h-[360px]');
                    panel.classList.add('lg:col-span-7');
                    wirelessCol.classList.remove('lg:col-span-12');
                    wirelessCol.classList.add('lg:col-span-5');
                    if (btn) btn.innerText = '⤢ Expand';
                }
            }

            function toggleSupervisorDrawer() {
                const panel = document.getElementById('admin-panel');
                const wirelessCol = document.getElementById('wireless-col');
                const chevron = document.getElementById('sup-chevron');
                if (panel.classList.contains('hidden')) {
                    panel.classList.remove('hidden');
                    wirelessCol.classList.remove('lg:col-span-12');
                    wirelessCol.classList.add(isSupExpandedFull ? 'lg:col-span-12' : 'lg:col-span-5');
                    if (chevron) chevron.className = 'fa-solid fa-chevron-up text-[9px] ml-0.5';
                } else {
                    panel.classList.add('hidden');
                    wirelessCol.classList.remove('lg:col-span-5');
                    wirelessCol.classList.add('lg:col-span-12');
                    if (chevron) chevron.className = 'fa-solid fa-chevron-down text-[9px] ml-0.5';
                }
                if (map) setTimeout(() => map.invalidateSize(), 150);
            }

            function togglePasswordVisibility(inputId, iconId) {
                const input = document.getElementById(inputId);
                const icon = document.getElementById(iconId);
                if (input.type === 'password') {
                    input.type = 'text';
                    icon.classList.remove('fa-eye');
                    icon.classList.add('fa-eye-slash');
                } else {
                    input.type = 'password';
                    icon.classList.remove('fa-eye-slash');
                    icon.classList.add('fa-eye');
                }
            }

            function showWebPopupBanner(message) {
                const isPttVoice = message.includes('[PTT VOICE]');
                const isBlockadeAlert = message.includes('[LIVE YOLO MODEL ALERT]') ||
                                        message.includes('[EDGE-AI YOLO]') ||
                                        message.includes('[SIMULATED AI]') ||
                                        message.includes('[YOLO AI]');
                const isBackupAlert = message.includes('[BACKUP SOS]');
                const isGreenCorridor = message.includes('[GREEN CORRIDOR]');

                const headerTitle = isPttVoice
                    ? '🎙️ NEW PTT VOICE NOTE QUEUED (CLICK PTT TAB TO PLAY)'
                    : isBlockadeAlert
                    ? '🚨 காவல்துறை அவசர எச்சரிக்கை | POLICE EMERGENCY ALERT'
                    : isBackupAlert
                    ? '🆘 கூடுதல் காவலர் உதவி அழைப்பு | OFFICER BACKUP SOS'
                    : isGreenCorridor
                    ? '🚑 108 ஆம்புலன்ஸ் பசுமை வழித்தடம் | GREEN CORRIDOR'
                    : 'ℹ️ தகவல் | CONTROL ROOM UPDATE';
                const boxColor = (isBlockadeAlert || isBackupAlert) ? 'bg-red-900/95 border-amber-400' : isGreenCorridor ? 'bg-emerald-900/95 border-emerald-400' : 'bg-slate-900/95 border-cyan-400';

                const toast = document.createElement('div');
                toast.className = `fixed top-14 right-5 z-50 ${boxColor} border-2 text-white px-3.5 py-2.5 rounded-xl shadow-2xl max-w-sm animate-bounce`;
                toast.innerHTML = `<div class="text-[11px] font-extrabold text-amber-300 uppercase">${headerTitle}</div><div class="text-[11px] mt-0.5">${message}</div>`;
                document.body.appendChild(toast);
                playTacticalSirenAndVoice(message);
                setTimeout(() => toast.remove(), 7500);
            }

            function toggleVoiceNotesModal(show) {
                const modal = document.getElementById('voice-notes-modal');
                if (show) {
                    modal.classList.remove('hidden');
                    loadVoiceNotes(true);
                } else {
                    modal.classList.add('hidden');
                }
            }

            async function loadVoiceNotes(forceRender = false) {
                try {
                    const res = await fetch('/api/voice-notes', { headers: { 'Authorization': 'Bearer ' + authToken } });
                    if (!res.ok) return;
                    const data = await res.json();
                    const currentHash = JSON.stringify(data) + JSON.stringify(localListenedPtt);
                    if (!forceRender && currentHash === lastVoiceHash) return;
                    lastVoiceHash = currentHash;
                    cachedVoiceNotes = data;

                    let unreadCount = 0;
                    let listenedCount = 0;
                    cachedVoiceNotes.forEach(v => {
                        const isHeard = v.is_listened || localListenedPtt[v.id];
                        if (isHeard) listenedCount++;
                        else unreadCount++;
                    });

                    const supPttCount = document.getElementById('sup-count-ptt');
                    if (supPttCount) supPttCount.innerText = `(${cachedVoiceNotes.length})`;

                    const badgeEl = document.getElementById('header-unread-ptt');
                    if (badgeEl) {
                        if (unreadCount > 0) {
                            badgeEl.innerText = unreadCount;
                            badgeEl.classList.remove('hidden');
                        } else {
                            badgeEl.classList.add('hidden');
                        }
                    }

                    const newCountEl = document.getElementById('ptt-new-count');
                    const listCountEl = document.getElementById('ptt-listened-count');
                    if (newCountEl) newCountEl.innerText = unreadCount;
                    if (listCountEl) listCountEl.innerText = listenedCount;

                    const adminPttBox = document.getElementById('admin-ptt-list');
                    if (adminPttBox) {
                        adminPttBox.innerHTML = '';
                        if (cachedVoiceNotes.length === 0) {
                            adminPttBox.innerHTML = '<p class="text-xs text-slate-500 py-4 text-center">No PTT voice notes queued yet.</p>';
                        } else {
                            cachedVoiceNotes.forEach(vn => {
                                const isHeard = vn.is_listened || localListenedPtt[vn.id];
                                const statusBadge = isHeard
                                    ? `<span class="bg-emerald-500/20 text-emerald-400 border border-emerald-500/40 text-[10px] px-2 py-0.5 rounded font-bold">✅ LISTENED</span>`
                                    : `<span class="bg-red-500/25 text-red-300 border border-red-500/40 text-[10px] px-2 py-0.5 rounded font-bold animate-pulse">🔴 NEW VOICE</span>`;
                                const safeId = (vn.id || '').replace(/'/g, "\\'");
                                adminPttBox.innerHTML += `
                                    <div class="border ${isHeard ? 'border-slate-800 bg-[#0a1326]/70 opacity-85' : 'border-amber-500/60 bg-[#0d182e]'} rounded-xl p-2.5 flex items-center justify-between gap-3">
                                        <div class="space-y-0.5 flex-1">
                                            <div class="flex items-center gap-2">
                                                ${statusBadge}
                                                <strong class="text-white text-xs">👮 ${vn.officer_name}</strong>
                                                <span class="text-[10px] text-cyan-300">🚦 ${vn.location_name}</span>
                                            </div>
                                            <div class="text-xs text-slate-200 italic">"${vn.transcript}"</div>
                                        </div>
                                        <button type="button" onclick="playWebVoiceNote('${safeId}')" class="${isHeard ? 'bg-slate-700 hover:bg-slate-600 text-slate-200' : 'bg-amber-500 hover:bg-amber-400 text-slate-950'} text-xs font-bold px-3 py-1.5 rounded-lg shrink-0 cursor-pointer shadow">
                                            ${isHeard ? '🔄 Replay' : '▶️ Play Voice'}
                                        </button>
                                    </div>
                                `;
                            });
                        }
                    }

                    const modalList = document.getElementById('voice-notes-modal-list');
                    if (modalList) {
                        modalList.innerHTML = '';
                        if (cachedVoiceNotes.length === 0) {
                            modalList.innerHTML = '<p class="text-xs text-slate-400 text-center py-6">No Walkie-Talkie PTT voice notes transmitted yet.</p>';
                        } else {
                            cachedVoiceNotes.forEach(vn => {
                                const isHeard = vn.is_listened || localListenedPtt[vn.id];
                                const safeId = (vn.id || '').replace(/'/g, "\\'");
                                modalList.innerHTML += `
                                    <div class="border ${isHeard ? 'border-slate-800 bg-[#070e1c] opacity-80' : 'border-amber-500 bg-[#0d182e]'} rounded-xl p-3 flex flex-wrap justify-between items-center gap-3">
                                        <div class="space-y-0.5 flex-1">
                                            <div class="flex items-center gap-2">
                                                <span class="${isHeard ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/40' : 'bg-red-500/20 text-red-400 border-red-500/40'} border text-[9px] font-black px-2 py-0.5 rounded">
                                                    ${isHeard ? '✅ ALREADY LISTENED' : '🔴 NEW VOICE NOTE'}
                                                </span>
                                                <span class="text-xs font-bold text-white">👮 ${vn.officer_name}</span>
                                                <span class="text-[10px] text-slate-400 font-mono">${vn.created_at ? new Date(vn.created_at).toLocaleTimeString() : ''}</span>
                                            </div>
                                            <div class="text-[11px] font-semibold text-cyan-300">🚦 Signal: ${vn.location_name}</div>
                                            <p class="text-xs text-slate-200 italic">"${vn.transcript}"</p>
                                        </div>
                                        <button type="button" onclick="playWebVoiceNote('${safeId}')" class="${isHeard ? 'bg-slate-700 hover:bg-slate-600 text-white' : 'bg-amber-500 hover:bg-amber-400 text-slate-950'} font-bold text-xs px-3.5 py-1.5 rounded-lg cursor-pointer shadow">
                                            ${isHeard ? '🔄 Replay Voice Note' : '▶️ Play Voice Note'}
                                        </button>
                                    </div>
                                `;
                            });
                        }
                    }
                } catch (e) {}
            }

            async function playWebVoiceNote(voiceId) {
                const vn = cachedVoiceNotes.find(v => v.id === voiceId);
                if (!vn) return;

                playLadyTtsSequence([
                    {
                        lang: 'en-IN',
                        text: `Walkie Talkie Dispatch from ${vn.officer_name} at ${vn.location_name}. ${vn.transcript}`,
                        rate: 1.0
                    }
                ]);

                localListenedPtt[voiceId] = true;
                localStorage.setItem('listened_ptt_web_8002', JSON.stringify(localListenedPtt));

                await fetch(`/api/voice-notes/${encodeURIComponent(voiceId)}/listen`, {
                    method: 'POST',
                    headers: { 'Authorization': 'Bearer ' + authToken }
                }).catch(() => {});

                loadVoiceNotes(true);
            }

            async function sendWebVoiceNote(presetText, specificLocation) {
                const inputEl = document.getElementById('web-ptt-input');
                const transcript = (presetText || (inputEl ? inputEl.value : '')).trim();
                if (!transcript) {
                    alert('Please enter or select a voice note message.');
                    return;
                }
                const loc = specificLocation || 'Kumbakonam Bypass Traffic Signal - Sector 2';
                const res = await fetch('/api/voice-notes', {
                    method: 'POST',
                    headers: { 'Authorization': 'Bearer ' + authToken, 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        location_name: loc,
                        transcript: transcript
                    })
                });
                if (res.ok) {
                    if (inputEl) inputEl.value = '';
                    loadVoiceNotes(true);
                    loadNotifications(true);
                    alert('🎙️ PTT Voice Note queued silently! Control Room can play it on demand.');
                }
            }

            async function toggleGreenCorridorWeb(blockadeId, nextState) {
                updateSignalDomInstantly(blockadeId, nextState ? 'G' : 'C', null);
                const res = await fetch(`/blockades/${blockadeId}/green-corridor`, {
                    method: 'POST',
                    headers: { 'Authorization': 'Bearer ' + authToken, 'Content-Type': 'application/json' },
                    body: JSON.stringify({ active: nextState })
                });
                if (res.ok) {
                    loadBlockades(true);
                    loadNotifications(true);
                }
            }

            function toggleYoloModal(show, specificLocation) {
                const modal = document.getElementById('yolo-live-modal');
                targetYoloLocation = specificLocation || null;
                if (show) {
                    modal.classList.remove('hidden');
                    pollYoloLiveStream(true);
                    if (yoloPollInterval) clearInterval(yoloPollInterval);
                    yoloPollInterval = setInterval(() => pollYoloLiveStream(false), 900);
                } else {
                    modal.classList.add('hidden');
                    if (yoloPollInterval) clearInterval(yoloPollInterval);
                }
            }

            async function pollYoloLiveStream(forceBuild = false) {
                const singleBox = document.getElementById('yolo-single-container');
                const matrixBox = document.getElementById('yolo-matrix-container');

                if (!targetYoloLocation && authToken.toUpperCase() === 'TN-ADMIN-01') {
                    singleBox.classList.add('hidden');
                    matrixBox.classList.remove('hidden');
                    document.getElementById('yolo-live-location').innerText = '📡 Control Room Multi-Signal YOLOv8 Matrix & Direct Hardware Override';
                    try {
                        const res = await fetch('/api/yolo-streams-all');
                        if (!res.ok) return;
                        const streams = await res.json();

                        if (forceBuild || matrixBox.children.length !== streams.length) {
                            matrixBox.innerHTML = '';
                            streams.forEach((s, idx) => {
                                const safeLoc = (s.location_name || '').replace(/'/g, "\\'");
                                const sigCol = s.traffic_light || 'C';
                                const blueCode = s.blue_code || '0';
                                const blueCss = getBlueLampCssClass(blueCode);

                                matrixBox.innerHTML += `
                                    <div class="bg-[#070e1c] border border-cyan-500/35 rounded-xl p-3 space-y-2">
                                        <div class="flex justify-between items-center">
                                            <div class="text-xs font-bold text-amber-300">🚦 ${s.location_name}</div>
                                            <span id="mat-lbl-${idx}" class="text-[10px] text-cyan-300 font-mono">${getBlueLampLabel(blueCode)}</span>
                                        </div>
                                        <div class="flex gap-3 items-center">
                                            <div class="signal-housing flex flex-col items-center gap-1.5 shrink-0">
                                                <div id="mat-b-${idx}" onclick="setGlobalSignalControl(null, 'A', '${safeLoc}')" class="signal-lamp ${blueCss}"></div>
                                                <div class="w-full h-[1px] bg-slate-700"></div>
                                                <div id="mat-r-${idx}" onclick="setGlobalSignalControl('R', null, '${safeLoc}')" class="signal-lamp ${sigCol === 'R' ? 'lamp-red-on' : 'lamp-red-off'}"></div>
                                                <div id="mat-y-${idx}" onclick="setGlobalSignalControl('Y', null, '${safeLoc}')" class="signal-lamp ${sigCol === 'Y' ? 'lamp-yellow-on' : 'lamp-yellow-off'}"></div>
                                                <div id="mat-g-${idx}" onclick="setGlobalSignalControl('G', null, '${safeLoc}')" class="signal-lamp ${(sigCol === 'G' || sigCol === 'C') ? 'lamp-green-on' : 'lamp-green-off'}"></div>
                                            </div>
                                            <div class="flex-1 space-y-1.5">
                                                <img id="mat-img-${idx}" src="${s.frame || ''}" class="w-full h-36 object-contain bg-black rounded border border-slate-800">
                                                <div class="flex flex-wrap justify-between items-center gap-1">
                                                    <div class="flex gap-1">
                                                        <button type="button" onclick="setGlobalSignalControl('R', null, '${safeLoc}')" class="bg-red-700/50 hover:bg-red-600 text-[9px] text-white font-bold px-2 py-0.5 rounded cursor-pointer">RED</button>
                                                        <button type="button" onclick="setGlobalSignalControl('Y', null, '${safeLoc}')" class="bg-amber-600/50 hover:bg-amber-500 text-[9px] text-white font-bold px-2 py-0.5 rounded cursor-pointer">YLW</button>
                                                        <button type="button" onclick="setGlobalSignalControl('G', null, '${safeLoc}')" class="bg-emerald-700/50 hover:bg-emerald-600 text-[9px] text-white font-bold px-2 py-0.5 rounded cursor-pointer">GRN</button>
                                                        <button type="button" onclick="setGlobalSignalControl('C', 'AUTO', '${safeLoc}')" class="bg-slate-700 text-[9px] text-slate-200 px-2 py-0.5 rounded cursor-pointer">AUTO</button>
                                                    </div>
                                                    <div class="flex gap-1">
                                                        <button type="button" onclick="setGlobalSignalControl(null, 'B', '${safeLoc}')" class="bg-blue-900/60 text-[9px] text-blue-200 px-1.5 py-0.5 rounded border border-blue-500/40 cursor-pointer">🔵 Blink</button>
                                                        <button type="button" onclick="setGlobalSignalControl(null, 'S', '${safeLoc}')" class="bg-blue-700/60 text-[9px] text-white px-1.5 py-0.5 rounded border border-blue-400 cursor-pointer">🔵 Steady</button>
                                                        <button type="button" onclick="setGlobalSignalControl(null, 'A', '${safeLoc}')" class="bg-cyan-500 text-[9px] text-slate-950 font-black px-1.5 py-0.5 rounded cursor-pointer">🚨 Strobe</button>
                                                    </div>
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                `;
                            });
                        } else {
                            // Update in place without destroying buttons!
                            streams.forEach((s, idx) => {
                                const sigCol = s.traffic_light || 'C';
                                const blueCode = s.blue_code || '0';
                                const bEl = document.getElementById(`mat-b-${idx}`);
                                const rEl = document.getElementById(`mat-r-${idx}`);
                                const yEl = document.getElementById(`mat-y-${idx}`);
                                const gEl = document.getElementById(`mat-g-${idx}`);
                                const imgEl = document.getElementById(`mat-img-${idx}`);
                                const lblEl = document.getElementById(`mat-lbl-${idx}`);
                                if (bEl) bEl.className = `signal-lamp ${getBlueLampCssClass(blueCode)}`;
                                if (rEl) rEl.className = `signal-lamp ${sigCol === 'R' ? 'lamp-red-on' : 'lamp-red-off'}`;
                                if (yEl) yEl.className = `signal-lamp ${sigCol === 'Y' ? 'lamp-yellow-on' : 'lamp-yellow-off'}`;
                                if (gEl) gEl.className = `signal-lamp ${(sigCol === 'G' || sigCol === 'C') ? 'lamp-green-on' : 'lamp-green-off'}`;
                                if (imgEl && s.frame) imgEl.src = s.frame;
                                if (lblEl) lblEl.innerText = getBlueLampLabel(blueCode);
                            });
                        }
                    } catch (e) {}
                } else {
                    singleBox.classList.remove('hidden');
                    matrixBox.classList.add('hidden');
                    try {
                        const q = targetYoloLocation ? `?location_name=${encodeURIComponent(targetYoloLocation)}` : '';
                        const res = await fetch(`/api/yolo-stream${q}`);
                        if (!res.ok) return;
                        const data = await res.json();
                        document.getElementById('yolo-live-location').innerText = `📍 Traffic Signal: ${targetYoloLocation || data.location_name}`;
                        document.getElementById('yolo-live-stage').innerText = data.stage || 'IDLE';
                        document.getElementById('yolo-live-timer').innerText = `${data.timer || 0}s`;
                        document.getElementById('yolo-live-objects').innerText = `${data.objects || 0} (${data.hazards || 'CLEAR'})`;

                        const sigCol = data.traffic_light || 'C';
                        const blueCode = data.blue_code || '0';
                        document.getElementById('modal-lamp-red').className = `signal-lamp ${sigCol === 'R' ? 'lamp-red-on' : 'lamp-red-off'}`;
                        document.getElementById('modal-lamp-yellow').className = `signal-lamp ${sigCol === 'Y' ? 'lamp-yellow-on' : 'lamp-yellow-off'}`;
                        document.getElementById('modal-lamp-green').className = `signal-lamp ${(sigCol === 'G' || sigCol === 'C') ? 'lamp-green-on' : 'lamp-green-off'}`;
                        document.getElementById('modal-lamp-blue').className = `signal-lamp ${getBlueLampCssClass(blueCode)}`;

                        const imgEl = document.getElementById('yolo-live-img');
                        const placeEl = document.getElementById('yolo-live-placeholder');
                        if (data.frame) {
                            imgEl.src = data.frame;
                            imgEl.classList.remove('hidden');
                            placeEl.classList.add('hidden');
                        }
                    } catch (e) {}
                }
            }

            setInterval(async () => {
                if (!authToken || document.getElementById('dashboard').classList.contains('hidden')) return;
                const badge = document.getElementById('grid-status-badge');
                const dot = document.getElementById('grid-dot');
                const text = document.getElementById('grid-text');
                try {
                    checkMyProfileStatus();
                    await loadBlockades(false);
                    await loadNotifications(false);
                    await loadVoiceNotes(false);
                    if (authToken.toUpperCase() === 'TN-ADMIN-01') await loadAdminPanelData(false);

                    badge.className = 'text-[10px] font-semibold px-2 py-0.5 rounded flex items-center gap-1 bg-emerald-500/10 border border-emerald-500/30 text-emerald-400';
                    dot.className = 'w-1.5 h-1.5 rounded-full bg-emerald-400 animate-ping';
                    text.innerText = 'GRID LIVE';
                } catch (e) {
                    badge.className = 'text-[10px] font-semibold px-2 py-0.5 rounded flex items-center gap-1 bg-red-500/20 border border-red-500/40 text-red-400';
                    dot.className = 'w-1.5 h-1.5 rounded-full bg-red-500';
                    text.innerText = 'GRID OFFLINE';
                }
            }, 3000);

            async function checkMyProfileStatus() {
                try {
                    const res = await fetch('/api/profile', { headers: { 'Authorization': 'Bearer ' + authToken } });
                    if (res.ok) {
                        const prof = await res.json();
                        currentUserStatus = prof.status || 'ACTIVE';
                        const banner = document.getElementById('pending-banner');
                        if (currentUserStatus !== 'ACTIVE' && authToken.toUpperCase() !== 'TN-ADMIN-01') {
                            banner.classList.remove('hidden');
                        } else {
                            banner.classList.add('hidden');
                        }
                    }
                } catch (e) {}
            }

            async function resetDatabase() {
                const res = await fetch('/blockades/reset-all', {
                    method: 'POST',
                    headers: { 'Authorization': 'Bearer ' + authToken }
                });
                if (res.ok) {
                    loadBlockades(true);
                    loadNotifications(true);
                    if (authToken.toUpperCase() === 'TN-ADMIN-01') loadAdminPanelData(true);
                    alert('Control Room Database reset! Fresh active signal incident spawned.');
                } else {
                    alert('Unauthorized: Only Control Room can reset the database.');
                }
            }

            function toggleProfileMenu() {
                const dropdown = document.getElementById('profile-dropdown');
                dropdown.classList.toggle('hidden');
            }

            window.onclick = function(event) {
                if (!event.target.closest('#profile-dropdown') && !event.target.closest('button[onclick="toggleProfileMenu()"]')) {
                    const dd = document.getElementById('profile-dropdown');
                    if (dd) dd.classList.add('hidden');
                }
            }

            async function openProfileModal() {
                document.getElementById('profile-dropdown').classList.add('hidden');
                try {
                    const res = await fetch('/api/profile', { headers: { 'Authorization': 'Bearer ' + authToken } });
                    if (res.ok) {
                        const profile = await res.json();
                        document.getElementById('profile-name').value = profile.name || '';
                        document.getElementById('profile-designation').value = profile.designation || 'Sub-Inspector (SI)';
                        document.getElementById('profile-badge').value = profile.badge_number || '';
                        document.getElementById('profile-mobile').value = profile.mobile || '';
                        document.getElementById('profile-email').value = profile.email || '';
                        if (profile.profile_photo) {
                            document.getElementById('profile-avatar-preview').src = profile.profile_photo;
                        }
                    }
                } catch (e) { console.error(e); }
                document.getElementById('profile-modal').classList.remove('hidden');
            }

            function closeProfileModal() {
                document.getElementById('profile-modal').classList.add('hidden');
            }

            async function submitWebFeedback() {
                const rating = parseInt(document.getElementById('web-fb-rating').value || '5', 10);
                const message = document.getElementById('web-fb-msg').value.trim();
                if (!message) { alert('Please enter feedback text.'); return; }
                const res = await fetch('/api/feedback', {
                    method: 'POST',
                    headers: { 'Authorization': 'Bearer ' + authToken, 'Content-Type': 'application/json' },
                    body: JSON.stringify({ rating, message })
                });
                if (res.ok) {
                    document.getElementById('web-fb-msg').value = '';
                    alert('Feedback submitted to Control Room!');
                    if (authToken.toUpperCase() === 'TN-ADMIN-01') loadAdminPanelData(true);
                }
            }

            function previewAvatar(e) {
                const file = e.target.files[0];
                if (file) {
                    const reader = new FileReader();
                    reader.onload = function(evt) {
                        document.getElementById('profile-avatar-preview').src = evt.target.result;
                    }
                    reader.readAsDataURL(file);
                }
            }

            async function updateProfile(e) {
                e.preventDefault();
                const formData = new FormData();
                formData.append('name', document.getElementById('profile-name').value);
                formData.append('designation', document.getElementById('profile-designation').value);
                formData.append('mobile', document.getElementById('profile-mobile').value);
                formData.append('email', document.getElementById('profile-email').value);
                const pwd = document.getElementById('profile-password').value;
                if (pwd) formData.append('password', pwd);
                const photoFile = document.getElementById('profile-photo-input').files[0];
                if (photoFile) formData.append('file', photoFile);

                try {
                    const res = await fetch('/api/profile', {
                        method: 'PUT',
                        headers: { 'Authorization': 'Bearer ' + authToken },
                        body: formData
                    });
                    if (res.ok) {
                        const msg = document.getElementById('profile-msg');
                        msg.innerText = authToken.toUpperCase() === 'TN-ADMIN-01' ? 'Control Room profile updated!' : 'Profile updated! Status set to PENDING APPROVAL.';
                        msg.classList.remove('hidden');
                        checkMyProfileStatus();
                        setTimeout(() => { msg.classList.add('hidden'); closeProfileModal(); }, 1800);
                    } else {
                        alert('Failed to update profile.');
                    }
                } catch (err) { alert('Error: ' + err.message); }
            }

            function openAdminEditModal(badgeNum) {
                const officer = cachedOfficers.find(o => o.badge_number === badgeNum);
                if (!officer) return;
                document.getElementById('admin-edit-badge').value = officer.badge_number;
                document.getElementById('admin-edit-name').value = officer.name || '';
                document.getElementById('admin-edit-designation').value = officer.designation || 'Sub-Inspector (SI)';
                document.getElementById('admin-edit-mobile').value = officer.mobile || '';
                document.getElementById('admin-edit-email').value = officer.email || '';
                document.getElementById('admin-edit-status').value = officer.status || 'ACTIVE';
                document.getElementById('admin-edit-password').value = '';
                document.getElementById('admin-edit-modal').classList.remove('hidden');
            }

            function closeAdminEditModal() {
                document.getElementById('admin-edit-modal').classList.add('hidden');
            }

            async function submitAdminOfficerEdit(e) {
                e.preventDefault();
                const badge = document.getElementById('admin-edit-badge').value;
                const payload = {
                    name: document.getElementById('admin-edit-name').value,
                    designation: document.getElementById('admin-edit-designation').value,
                    mobile: document.getElementById('admin-edit-mobile').value,
                    email: document.getElementById('admin-edit-email').value,
                    status: document.getElementById('admin-edit-status').value,
                    password: document.getElementById('admin-edit-password').value || null
                };
                const res = await fetch(`/admin/officers/${badge}`, {
                    method: 'PUT',
                    headers: {
                        'Authorization': 'Bearer ' + authToken,
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(payload)
                });
                if (res.ok) {
                    closeAdminEditModal();
                    loadAdminPanelData(true);
                    alert(`Officer ${badge} profile updated by Control Room.`);
                } else {
                    alert('Failed to update officer profile.');
                }
            }

            async function deleteOfficerAccount(badge) {
                if (badge.toUpperCase() === 'TN-ADMIN-01') {
                    alert('Cannot delete primary Control Room account.');
                    return;
                }
                if (!confirm(`Are you sure you want to permanently DELETE Officer ${badge}?`)) return;
                const res = await fetch(`/admin/officers/${badge}`, {
                    method: 'DELETE',
                    headers: { 'Authorization': 'Bearer ' + authToken }
                });
                if (res.ok) {
                    closeAdminEditModal();
                    loadAdminPanelData(true);
                    alert(`Officer ${badge} permanently deleted.`);
                } else {
                    const err = await res.json();
                    alert(err.detail || 'Failed to delete officer.');
                }
            }

            function deleteOfficerFromModal() {
                const badge = document.getElementById('admin-edit-badge').value;
                if (badge) deleteOfficerAccount(badge);
            }

            async function requestBackupWeb(blockadeId) {
                const res = await fetch(`/blockades/${blockadeId}/request-backup`, {
                    method: 'POST',
                    headers: { 'Authorization': 'Bearer ' + authToken, 'Content-Type': 'application/json' },
                    body: JSON.stringify({ target_badge: 'ALL UNITS', reason: 'High congestion - Multiple units needed' })
                });
                if (res.ok) {
                    loadBlockades(true);
                    loadNotifications(true);
                    alert('🆘 உதவி அழைப்பு அனுப்பப்பட்டது! Backup SOS dispatched to all active officers.');
                }
            }

            async function openClearancesModal() {
                document.getElementById('profile-dropdown').classList.add('hidden');
                const list = document.getElementById('clearances-list');
                list.innerHTML = '<p class="text-xs text-slate-400 text-center py-4">Loading your personal clearance history...</p>';
                document.getElementById('clearances-modal').classList.remove('hidden');

                try {
                    const res = await fetch('/api/my-clearances', { headers: { 'Authorization': 'Bearer ' + authToken } });
                    if (res.ok) {
                        const data = await res.json();
                        list.innerHTML = '';
                        if (data.length === 0) {
                            list.innerHTML = '<p class="text-xs text-slate-400 text-center py-4">No blockade clearances recorded under your badge yet.</p>';
                            return;
                        }
                        data.forEach((b, idx) => {
                            list.innerHTML += `
                                <div class="bg-[#070e1c] border border-emerald-500/30 p-2.5 rounded-xl flex items-center justify-between gap-4">
                                    <div class="space-y-0.5">
                                        <div class="flex items-center gap-2">
                                            <span class="text-xs font-bold text-amber-400">#${idx + 1} - ${b.location_name}</span>
                                            <span class="text-[9px] bg-emerald-500/20 text-emerald-300 px-1.5 py-0.5 rounded font-bold">RESOLVED BY YOU</span>
                                        </div>
                                        <p class="text-[11px] text-slate-300">${b.notes || 'No notes'}</p>
                                    </div>
                                    ${b.clearance_photo ? `<img src="${b.clearance_photo}" class="w-14 h-14 object-cover rounded-lg border border-emerald-500/40 shrink-0">` : ''}
                                </div>
                            `;
                        });
                    }
                } catch (e) {
                    list.innerHTML = '<p class="text-xs text-red-400 text-center py-4">Failed to load clearances.</p>';
                }
            }

            function closeClearancesModal() {
                document.getElementById('clearances-modal').classList.add('hidden');
            }

            function switchTab(tab) {
                const loginTab = document.getElementById('tab-login');
                const regTab = document.getElementById('tab-register');
                const loginForm = document.getElementById('form-login');
                const regForm = document.getElementById('form-register');

                if (tab === 'login') {
                    loginTab.className = 'py-1.5 text-xs font-bold rounded-lg bg-amber-500 text-slate-950 transition cursor-pointer';
                    regTab.className = 'py-1.5 text-xs font-bold rounded-lg text-slate-300 hover:text-white transition cursor-pointer';
                    loginForm.classList.remove('hidden');
                    regForm.classList.add('hidden');
                } else {
                    regTab.className = 'py-1.5 text-xs font-bold rounded-lg bg-amber-500 text-slate-950 transition cursor-pointer';
                    loginTab.className = 'py-1.5 text-xs font-bold rounded-lg text-slate-300 hover:text-white transition cursor-pointer';
                    regForm.classList.remove('hidden');
                    loginForm.classList.add('hidden');
                }
            }

            async function requestOTP() {
                const name = document.getElementById('reg-name').value;
                const designation = document.getElementById('reg-designation').value;
                const badge = document.getElementById('reg-badge').value;
                const mobile = document.getElementById('reg-mobile').value;
                const email = document.getElementById('reg-email').value;
                const password = document.getElementById('reg-password').value;
                const errDiv = document.getElementById('reg-error');

                if (!name || !badge || !mobile || !email || !password) {
                    errDiv.innerText = 'Please fill in all officer registration fields.';
                    errDiv.classList.remove('hidden');
                    return;
                }
                errDiv.classList.add('hidden');

                tempRegData = { name, designation, badge_number: badge, mobile, email, password };
                generatedOTP = Math.floor(100000 + Math.random() * 900000).toString();

                await fetch('/auth/request-otp', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email, mobile, otp: generatedOTP })
                });

                document.getElementById('reg-step-1').classList.add('hidden');
                document.getElementById('reg-step-2').classList.remove('hidden');
                document.getElementById('otp-hint').innerText = `[SIMULATED SMS/MAIL OTP]: ${generatedOTP}`;
            }

            async function resendOTP() {
                if (!tempRegData.email || !tempRegData.mobile) return;
                generatedOTP = Math.floor(100000 + Math.random() * 900000).toString();
                await fetch('/auth/request-otp', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email: tempRegData.email, mobile: tempRegData.mobile, otp: generatedOTP })
                });
                document.getElementById('reg-otp').value = '';
                document.getElementById('otp-hint').innerText = `[RESENT SMS/MAIL OTP]: ${generatedOTP}`;
                alert(`A new 6-digit OTP has been dispatched: ${generatedOTP}`);
            }

            function backToRegStep1() {
                document.getElementById('reg-step-2').classList.add('hidden');
                document.getElementById('reg-step-1').classList.remove('hidden');
            }

            async function verifyAndRegister() {
                const enteredOTP = document.getElementById('reg-otp').value;
                const errDiv = document.getElementById('reg-error');

                if (enteredOTP !== generatedOTP) {
                    errDiv.innerText = 'Invalid OTP code. Please check simulation hint.';
                    errDiv.classList.remove('hidden');
                    return;
                }

                const res = await fetch('/auth/register', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(tempRegData)
                });

                if (!res.ok) {
                    const err = await res.json();
                    errDiv.innerText = err.detail || 'Registration failed.';
                    errDiv.classList.remove('hidden');
                    return;
                }

                alert('Officer account registered successfully! Awaiting Control Room approval.');
                switchTab('login');
                document.getElementById('login-username').value = tempRegData.badge_number;
            }

            function initMap() {
                if (map) return;
                map = L.map('map').setView([10.9601, 79.3845], 12);
                L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                    maxZoom: 19,
                    attribution: '© OpenStreetMap | நான்காம் காவல் நண்பன்'
                }).addTo(map);
                markersLayer = L.layerGroup().addTo(map);
            }

            if (authToken) { showDashboard(); }

            function showDashboard() {
                document.getElementById('login-modal').classList.add('hidden');
                document.getElementById('dashboard').classList.remove('hidden');
                const isControlRoom = authToken.toUpperCase() === 'TN-ADMIN-01';
                document.getElementById('user-badge').innerText = isControlRoom ? 'CONTROL ROOM' : authToken;

                const logHeading = document.getElementById('wireless-log-heading');
                const wirelessCol = document.getElementById('wireless-col');
                const adminPanel = document.getElementById('admin-panel');

                if (isControlRoom) {
                    adminPanel.classList.remove('hidden');
                    wirelessCol.classList.remove('lg:col-span-12');
                    wirelessCol.classList.add('lg:col-span-5');
                    document.getElementById('admin-action-btns').classList.remove('hidden');
                    document.getElementById('btn-clear-resolved').classList.remove('hidden');
                    document.getElementById('menu-my-clearances').classList.add('hidden');
                    logHeading.innerHTML = `<i class="fa-solid fa-walkie-talkie text-red-400 mr-1.5"></i>Control Room Master Wireless Log (தமிழ்/EN)`;
                    loadAdminPanelData(true);
                } else {
                    adminPanel.classList.add('hidden');
                    wirelessCol.classList.remove('lg:col-span-5');
                    wirelessCol.classList.add('lg:col-span-12');
                    document.getElementById('admin-action-btns').classList.add('hidden');
                    document.getElementById('btn-clear-resolved').classList.add('hidden');
                    document.getElementById('menu-my-clearances').classList.remove('hidden');
                    logHeading.innerHTML = `<i class="fa-solid fa-triangle-exclamation text-amber-400 mr-1.5"></i>Officer Blockade & Backup Alert Feed (தமிழ் & English)`;
                }

                setTimeout(() => {
                    initMap();
                    if (map) map.invalidateSize();
                    checkMyProfileStatus();
                    loadBlockades(true);
                    loadNotifications(true);
                    loadVoiceNotes(true);
                }, 100);
            }

            async function loadAdminPanelData(forceRender = false) {
                try {
                    const [offRes, fbRes, blockRes] = await Promise.all([
                        fetch('/admin/officers', { headers: { 'Authorization': 'Bearer ' + authToken } }),
                        fetch('/api/feedback', { headers: { 'Authorization': 'Bearer ' + authToken } }),
                        fetch('/blockades/')
                    ]);

                    if (!offRes.ok || !fbRes.ok || !blockRes.ok) return;

                    const officers = await offRes.json();
                    const feedbacks = await fbRes.json();
                    const blockades = await blockRes.json();
                    const resolved = blockades.filter(b => b.status === 'RESOLVED');

                    const combinedHash = JSON.stringify({
                        o: officers.map(x => [x.id, x.name, x.designation, x.status, x.mobile, x.email]),
                        f: feedbacks.map(x => x.id),
                        r: resolved.map(x => x.id)
                    });

                    if (!forceRender && combinedHash === lastAdminHash) return;
                    lastAdminHash = combinedHash;
                    cachedOfficers = officers;

                    const offCountEl = document.getElementById('sup-count-officers');
                    if (offCountEl) offCountEl.innerText = `(${cachedOfficers.length})`;

                    const offContainer = document.getElementById('admin-officers-list');
                    if (offContainer) {
                        offContainer.innerHTML = '';
                        cachedOfficers.forEach(o => {
                            let badgeStyle = o.status === 'ACTIVE' ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/40' : 'bg-amber-500/20 text-amber-400 border border-amber-500/40';
                            const isPrimaryControlRoom = o.badge_number.toUpperCase() === 'TN-ADMIN-01';
                            const displayBadge = isPrimaryControlRoom ? 'CONTROL-ROOM-01' : o.badge_number;
                            offContainer.innerHTML += `
                                <div class="bg-[#0d182e] border border-slate-800 rounded-xl p-2.5 flex items-center justify-between gap-2">
                                    <div>
                                        <div class="text-xs font-bold text-white">👮 ${o.name} <span class="text-[10px] text-amber-300 font-semibold">[${o.designation || 'Officer'}]</span></div>
                                        <div class="text-[11px] text-slate-400 mt-0.5">ID: <strong class="text-cyan-300">${displayBadge}</strong> • 📞 ${o.mobile} • ✉️ ${o.email}</div>
                                    </div>
                                    <div class="flex items-center gap-1.5 shrink-0">
                                        <span class="text-[10px] px-2 py-0.5 rounded font-bold ${badgeStyle}">${o.status}</span>
                                        ${o.status === 'PENDING APPROVAL' ? `<button type="button" onclick="approveOfficer('${o.badge_number}')" class="bg-emerald-600 hover:bg-emerald-500 text-white text-[10px] font-bold px-2.5 py-1 rounded cursor-pointer">Approve</button>` : ''}
                                        <button type="button" onclick="openAdminEditModal('${o.badge_number}')" class="bg-blue-600/40 hover:bg-blue-600 border border-blue-400/40 text-blue-200 text-[10px] font-bold px-2.5 py-1 rounded cursor-pointer"><i class="fa-solid fa-pen mr-1"></i>Edit</button>
                                        ${!isPrimaryControlRoom ? `<button type="button" onclick="deleteOfficerAccount('${o.badge_number}')" class="bg-red-600/40 hover:bg-red-600 border border-red-400/40 text-red-200 text-[10px] font-bold px-2.5 py-1 rounded cursor-pointer"><i class="fa-solid fa-trash"></i></button>` : ''}
                                    </div>
                                </div>
                            `;
                        });
                    }

                    const fbCountEl = document.getElementById('sup-count-feedbacks');
                    if (fbCountEl) fbCountEl.innerText = `(${feedbacks.length})`;

                    const fbContainer = document.getElementById('admin-feedbacks-list');
                    if (fbContainer) {
                        fbContainer.innerHTML = '';
                        if (feedbacks.length === 0) {
                            fbContainer.innerHTML = '<p class="text-xs text-slate-500 py-4 text-center">No officer app feedbacks submitted yet.</p>';
                        } else {
                            feedbacks.forEach(f => {
                                const stars = '★'.repeat(f.rating || 5) + '☆'.repeat(5 - (f.rating || 5));
                                fbContainer.innerHTML += `
                                    <div class="bg-[#0d182e] border border-slate-800 rounded-xl p-2.5 space-y-1">
                                        <div class="flex justify-between items-center">
                                            <strong class="text-amber-300 text-xs">${f.officer_name} (${f.designation}) • ${f.badge_number}</strong>
                                            <span class="text-amber-400 text-xs">${stars}</span>
                                        </div>
                                        <p class="text-xs text-slate-200">${f.message}</p>
                                    </div>
                                `;
                            });
                        }
                    }

                    const container = document.getElementById('admin-clearances-list');
                    if (container) {
                        container.innerHTML = '';
                        const clearCountEl = document.getElementById('sup-count-clearances');
                        if (clearCountEl) clearCountEl.innerText = `(${resolved.length})`;

                        if (resolved.length === 0) {
                            container.innerHTML = '<p class="text-xs text-slate-500 py-4 text-center">No clearances logged yet.</p>';
                        } else {
                            resolved.forEach((b) => {
                                container.innerHTML += `
                                    <div class="bg-[#0d182e] border border-emerald-500/30 rounded-xl p-2.5 flex items-center justify-between gap-3">
                                        <div>
                                            <div class="text-xs font-bold text-white">📍 ${b.location_name}</div>
                                            <div class="text-[11px] text-amber-300 mt-0.5">Resolved & Verified by: <strong>${b.resolved_by || 'Officer'}</strong></div>
                                        </div>
                                        ${b.clearance_photo ? `<a href="${b.clearance_photo}" target="_blank"><img src="${b.clearance_photo}" class="w-12 h-12 object-cover rounded-lg border border-emerald-500/40 shrink-0"></a>` : '<span class="text-[10px] text-slate-500">No Photo</span>'}
                                    </div>
                                `;
                            });
                        }
                    }
                } catch (e) { console.error(e); }
            }

            async function approveOfficer(badge) {
                await fetch(`/admin/officers/${badge}/approve`, {
                    method: 'POST',
                    headers: { 'Authorization': 'Bearer ' + authToken }
                });
                loadAdminPanelData(true);
            }

            async function handleLogin(e) {
                e.preventDefault();
                const username = document.getElementById('login-username').value;
                const password = document.getElementById('login-password').value;
                const formData = new URLSearchParams({ username, password });

                try {
                    const res = await fetch('/auth/login', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                        body: formData
                    });
                    if (!res.ok) throw new Error('Invalid credentials');
                    const data = await res.json();
                    authToken = data.access_token;
                    localStorage.setItem('token_8002', authToken);
                    showDashboard();
                } catch (err) {
                    const errDiv = document.getElementById('login-error');
                    errDiv.innerText = 'Incorrect Control Room ID / Badge ID or password.';
                    errDiv.classList.remove('hidden');
                }
            }

            async function simulateAITrigger() {
                const res = await fetch('/blockades/simulate-ai', {
                    method: 'POST',
                    headers: { 'Authorization': 'Bearer ' + authToken }
                });
                if (res.ok) {
                    loadBlockades(true);
                    loadNotifications(true);
                } else {
                    alert('Unauthorized: Only Control Room can simulate AI hazards.');
                }
            }

            async function loadBlockades(forceRender = false) {
                const res = await fetch('/blockades/');
                if (!res.ok) return;
                const data = await res.json();

                // Structural hash excludes signal_color/blue_mode so clicking signal buttons NEVER wipes & rebuilds the DOM
                const structuralSignature = JSON.stringify(data.map(b => [
                    b.id, b.status, b.green_corridor, b.notes, b.officer_lat, b.officer_lng, b.resolved_by
                ]));
                if (!forceRender && structuralSignature === lastBlockadesHash) {
                    data.forEach(b => updateSignalDomInstantly(b.id, b.signal_color || 'R', b.blue_mode || 'B'));
                    return;
                }
                lastBlockadesHash = structuralSignature;

                const container = document.getElementById('blockade-list');
                if (!container) return;
                container.innerHTML = '';

                if (markersLayer) markersLayer.clearLayers();
                const isControlRoom = authToken.toUpperCase() === 'TN-ADMIN-01';

                data.slice().reverse().forEach(b => {
                    const isResolved = b.status === 'RESOLVED';
                    const isCorridorOn = !!b.green_corridor || b.signal_color === 'G';
                    const sigColor = b.signal_color || (isResolved ? 'G' : 'R');
                    const blueMode = isResolved ? '0' : (b.blue_mode || 'B');
                    const blueCss = getBlueLampCssClass(blueMode);

                    const isAssignedOrArrived = b.status === 'ASSIGNED' || b.status === 'ARRIVED';
                    const badgeColor = b.severity === 'CRITICAL' ? 'bg-red-600/25 text-red-300 border-red-500/40' :
                                       b.severity === 'HIGH' ? 'bg-amber-500/20 text-amber-300 border-amber-500/40' :
                                       'bg-blue-600/25 text-blue-300 border-blue-500/40';

                    let slaBadge = `<span class="text-[10px] font-mono text-cyan-300">⏱️ SLA Active</span>`;
                    if (isResolved) {
                        slaBadge = `<span class="text-[10px] font-mono text-emerald-400">✅ SLA: 03m 18s</span>`;
                    } else if (b.created_at) {
                        const elapsedSec = Math.max(5, Math.floor((Date.now() - new Date(b.created_at).getTime()) / 1000));
                        const m = String(Math.floor(elapsedSec / 60)).padStart(2, '0');
                        const s = String(elapsedSec % 60).padStart(2, '0');
                        slaBadge = `<span class="text-[10px] font-mono text-cyan-300">⏱️ ${m}m ${s}s</span>`;
                    }

                    let corridorBannerHtml = isCorridorOn && !isResolved
                        ? `<div class="bg-emerald-500/20 border border-emerald-400 text-emerald-300 text-[10px] font-extrabold px-2 py-1 rounded text-center animate-pulse">🚑 108 GREEN CORRIDOR / GREEN SIGNAL LOCKED</div>`
                        : '';

                    const safeLoc = (b.location_name || '').replace(/'/g, "\\'");

                    let signalAndImageRow = `
                        <div class="flex gap-2.5 items-center bg-[#091326] p-2 rounded-xl border border-slate-800/90">
                            <div class="signal-housing flex flex-col items-center gap-1.5 shrink-0" title="Click any lamp to switch physical Traffic Signal">
                                <div id="inc-lamp-b-${b.id}" onclick="setIncidentSignalPhase(${b.id}, null, 'A')" class="signal-lamp ${blueCss}" title="Blue AI Lamp"></div>
                                <div class="w-full h-[1px] bg-slate-700"></div>
                                <div id="inc-lamp-r-${b.id}" onclick="setIncidentSignalPhase(${b.id}, 'R', null)" class="signal-lamp ${sigColor === 'R' ? 'lamp-red-on' : 'lamp-red-off'}" title="Click to turn Signal RED"></div>
                                <div id="inc-lamp-y-${b.id}" onclick="setIncidentSignalPhase(${b.id}, 'Y', null)" class="signal-lamp ${sigColor === 'Y' ? 'lamp-yellow-on' : 'lamp-yellow-off'}" title="Click to turn Signal YELLOW"></div>
                                <div id="inc-lamp-g-${b.id}" onclick="setIncidentSignalPhase(${b.id}, 'G', null)" class="signal-lamp ${(sigColor === 'G' || sigColor === 'C') ? 'lamp-green-on' : 'lamp-green-off'}" title="Click to turn Signal GREEN (108 Corridor)"></div>
                            </div>

                            <div class="flex-1 space-y-1.5">
                                ${b.image_url ? `<img src="${b.image_url}" class="w-full h-24 object-cover rounded-lg border border-slate-700/80">` : ''}
                                <div class="flex flex-wrap justify-between items-center gap-1">
                                    <div class="flex gap-1">
                                        <button type="button" onclick="setIncidentSignalPhase(${b.id}, 'R', null)" class="bg-red-700/60 hover:bg-red-600 text-white border border-red-400/50 text-[9px] font-bold px-1.5 py-0.5 rounded cursor-pointer">🔴 RED</button>
                                        <button type="button" onclick="setIncidentSignalPhase(${b.id}, 'Y', null)" class="bg-amber-600/60 hover:bg-amber-500 text-white border border-amber-400/50 text-[9px] font-bold px-1.5 py-0.5 rounded cursor-pointer">🟡 YLW</button>
                                        <button type="button" onclick="setIncidentSignalPhase(${b.id}, 'G', null)" class="bg-emerald-700/60 hover:bg-emerald-600 text-white border border-emerald-400/50 text-[9px] font-bold px-1.5 py-0.5 rounded cursor-pointer">🟢 GRN</button>
                                        <button type="button" onclick="setIncidentSignalPhase(${b.id}, 'C', null)" class="bg-slate-700 hover:bg-slate-600 text-slate-200 text-[9px] font-bold px-1.5 py-0.5 rounded cursor-pointer">🔄 AUTO</button>
                                    </div>
                                    <div class="flex gap-1">
                                        <button type="button" onclick="setIncidentSignalPhase(${b.id}, null, '0')" class="bg-slate-800 hover:bg-slate-700 text-slate-300 text-[9px] px-1.5 py-0.5 rounded border border-slate-600 cursor-pointer" title="Blue Off ('0')">⚪ Off</button>
                                        <button type="button" onclick="setIncidentSignalPhase(${b.id}, null, 'B')" class="bg-blue-900/70 hover:bg-blue-700 text-blue-200 text-[9px] px-1.5 py-0.5 rounded border border-blue-500/40 cursor-pointer" title="Blue Slow Blink (0-15s)">🔵 Blink</button>
                                        <button type="button" onclick="setIncidentSignalPhase(${b.id}, null, 'S')" class="bg-blue-700/70 hover:bg-blue-600 text-white text-[9px] px-1.5 py-0.5 rounded border border-blue-400/40 cursor-pointer" title="Blue Steady (15-45s)">🔵 Steady</button>
                                        <button type="button" onclick="setIncidentSignalPhase(${b.id}, null, 'A')" class="bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-black text-[9px] px-1.5 py-0.5 rounded cursor-pointer" title="Blue Rapid Strobe (>45s)">🚨 Strobe</button>
                                    </div>
                                </div>
                            </div>
                        </div>
                    `;

                    let clearanceHtml = b.clearance_photo ? `
                        <div class="p-2 bg-emerald-950/40 border border-emerald-500/30 rounded-lg">
                            <div class="text-[10px] text-emerald-400 font-bold mb-1"><i class="fa-solid fa-camera"></i> Cleared by ${b.resolved_by || 'Officer'}:</div>
                            <img src="${b.clearance_photo}" class="w-full h-20 object-cover rounded">
                        </div>` : '';

                    let corridorBtn = !isResolved
                        ? `<button type="button" onclick="toggleGreenCorridorWeb(${b.id}, ${!isCorridorOn})" class="${isCorridorOn ? 'bg-emerald-600 text-white border-emerald-300' : 'bg-emerald-900/40 hover:bg-emerald-700/50 text-emerald-300 border-emerald-500/40'} border text-[10px] px-2 py-0.5 rounded transition cursor-pointer font-bold">🚑 ${isCorridorOn ? '108 Corridor ON' : '108 Corridor'}</button>`
                        : '';
                    let navBtn = `<a href="https://www.google.com/maps/dir/?api=1&destination=${b.latitude},${b.longitude}" target="_blank" class="bg-blue-900/40 hover:bg-blue-700/50 border border-blue-400/40 text-blue-200 text-[10px] px-2 py-0.5 rounded transition cursor-pointer">🧭 Nav</a>`;
                    let liveYoloBtn = !isResolved
                        ? `<button type="button" onclick="toggleYoloModal(true, '${safeLoc}')" class="bg-cyan-700/40 hover:bg-cyan-600/60 border border-cyan-400/40 text-cyan-200 text-[10px] px-2 py-0.5 rounded transition cursor-pointer"><i class="fa-solid fa-eye"></i> Live Visuals & Signal</button>`
                        : '';
                    let backupBtn = !isResolved
                        ? `<button type="button" onclick="requestBackupWeb(${b.id})" class="bg-red-700/40 hover:bg-red-600/60 border border-red-400/40 text-red-200 text-[10px] px-2 py-0.5 rounded transition cursor-pointer">🆘 SOS</button>`
                        : '';

                    let actionBtnsHtml = '';
                    if (!isControlRoom) {
                        if (currentUserStatus !== 'ACTIVE') {
                            actionBtnsHtml = `<span class="text-[10px] text-amber-400 font-semibold">⏳ Pending Approval</span>`;
                        } else {
                            if (b.status === 'ACTIVE') actionBtnsHtml = `<button type="button" onclick="assignUnit(${b.id})" class="bg-blue-700/50 hover:bg-blue-600 border border-blue-400/40 text-white text-[11px] font-bold px-2.5 py-0.5 rounded transition cursor-pointer">Dispatch</button>`;
                            if (b.status === 'ASSIGNED') actionBtnsHtml = `<button type="button" onclick="markArrived(${b.id})" class="bg-amber-700/50 hover:bg-amber-600 border border-amber-400/40 text-white text-[11px] font-bold px-2.5 py-0.5 rounded transition cursor-pointer">Arrived</button>`;
                            if (b.status === 'ARRIVED') actionBtnsHtml = `<button type="button" onclick="openPhotoModal(${b.id})" class="bg-emerald-700/50 hover:bg-emerald-600 border border-emerald-400/40 text-white text-[11px] font-bold px-2.5 py-0.5 rounded transition cursor-pointer">Camera Clear</button>`;
                        }
                    } else {
                        actionBtnsHtml = `<span id="inc-blue-lbl-${b.id}" class="text-[10px] text-cyan-300 font-bold">🔵 ${getBlueLampLabel(blueMode)}</span>`;
                    }

                    container.innerHTML += `
                        <div class="bg-[#060c18] border ${isCorridorOn ? 'border-2 border-emerald-400' : isResolved ? 'border-emerald-500/40 opacity-85' : 'border-amber-500/30'} p-3 rounded-xl space-y-2 hover:border-amber-400/60 transition">
                            <div class="flex justify-between items-start gap-2">
                                <div onclick="focusMap(${b.latitude}, ${b.longitude})" class="cursor-pointer flex-1">
                                    <h4 class="font-bold text-xs text-white hover:text-amber-400 leading-tight">🚦 ${b.location_name}</h4>
                                    <p class="text-[11px] text-slate-400 mt-0.5">${b.notes || ''}</p>
                                </div>
                                <div class="flex flex-col items-end gap-1 shrink-0">
                                    <span class="text-[10px] font-bold px-2 py-0.5 border rounded ${badgeColor}">${b.severity}</span>
                                    ${slaBadge}
                                </div>
                            </div>
                            ${corridorBannerHtml}
                            ${signalAndImageRow}
                            <div class="flex flex-wrap gap-1.5 pt-0.5">
                                ${corridorBtn}
                                ${navBtn}
                                ${liveYoloBtn}
                                ${backupBtn}
                            </div>
                            ${clearanceHtml}
                            <div class="flex justify-between items-center pt-1.5 border-t border-slate-800/80">
                                <span class="text-[11px] text-slate-400">Status: <strong class="${isResolved ? 'text-emerald-400' : 'text-amber-300'}">${b.status}</strong></span>
                                <div class="space-x-1 flex items-center">${actionBtnsHtml}</div>
                            </div>
                        </div>`;

                    if (markersLayer && b.latitude && b.longitude) {
                        const markerColor = sigColor === 'G' ? '#10b981' : sigColor === 'Y' ? '#f59e0b' : isResolved ? '#10b981' : '#ef4444';
                        const circle = L.circleMarker([b.latitude, b.longitude], {
                            radius: isCorridorOn ? 12 : 9, fillColor: markerColor, color: '#fbbf24', weight: 2, opacity: 1, fillOpacity: 0.9
                        }).bindPopup(`<b>🚦 Signal: ${b.location_name}</b><br>Signal Phase: ${sigColor}<br>Blue AI Lamp: ${getBlueLampLabel(blueMode)}`);
                        markersLayer.addLayer(circle);

                        if (isAssignedOrArrived && b.officer_lat && b.officer_lng) {
                            const officerIcon = L.divIcon({
                                className: 'custom-officer-marker',
                                html: `<div class="officer-pulse" style="position:relative; background: linear-gradient(135deg, #1e3a8a, #b91c1c); border: 2px solid #fbbf24; border-radius: 50%; width: 32px; height: 32px; display: flex; align-items: center; justify-content: center; box-shadow: 0 0 15px rgba(251,191,36,0.9);">
                                          <i class="fa-solid fa-user-shield text-amber-300 text-xs"></i>
                                       </div>`,
                                iconSize: [32, 32],
                                iconAnchor: [16, 16]
                            });
                            const officerMarker = L.marker([b.officer_lat, b.officer_lng], { icon: officerIcon })
                                .bindPopup(`<b>🚓 TN Police Dispatched Unit</b><br>Target Signal: ${b.location_name}<br>Status: ${b.status}`);
                            markersLayer.addLayer(officerMarker);

                            const routeLine = L.polyline([[b.officer_lat, b.officer_lng], [b.latitude, b.longitude]], {
                                color: '#38bdf8', weight: 2.5, dashArray: '6, 6', opacity: 0.85
                            });
                            markersLayer.addLayer(routeLine);
                        }
                    }
                });
            }

            function focusMap(lat, lng) { if (map) map.setView([lat, lng], 14); }

            async function loadNotifications(forceRender = false) {
                const res = await fetch('/notifications/', { headers: { 'Authorization': 'Bearer ' + authToken } });
                if (!res.ok) return;
                const data = await res.json();

                if (data.length > 0) {
                    const newest = data[data.length - 1];
                    if (lastSeenNotificationId !== null && newest.id > lastSeenNotificationId) {
                        showWebPopupBanner(newest.message);
                    }
                    lastSeenNotificationId = newest.id;
                }

                const notifSignature = data.length > 0 ? `${data.length}-${data[data.length - 1].id}` : '0';
                if (!forceRender && notifSignature === lastNotifsHash) return;
                lastNotifsHash = notifSignature;

                const box = document.getElementById('notification-box');
                if (!box) return;
                box.innerHTML = '';
                data.slice().reverse().forEach(n => {
                    let thumb = n.image_thumb ? `<img src="${n.image_thumb}" class="w-10 h-8 object-cover rounded inline-block ml-1.5 border border-slate-700 shrink-0">` : '';
                    box.innerHTML += `<div class="flex items-center justify-between border-b border-slate-800/60 pb-1.5 gap-1.5"><div class="leading-relaxed"><span class="text-amber-400 font-bold">[${new Date(n.created_at).toLocaleTimeString()}]</span> ${n.message}</div>${thumb}</div>`;
                });
            }

            async function assignUnit(id) {
                const res = await fetch('/blockades/' + id + '/assign', { method: 'POST', headers: { 'Authorization': 'Bearer ' + authToken } });
                if (!res.ok) {
                    const err = await res.json();
                    alert(err.detail || 'Action restricted.');
                }
                loadBlockades(true); loadNotifications(true);
            }

            async function markArrived(id) {
                const res = await fetch('/blockades/' + id + '/arrived', { method: 'POST', headers: { 'Authorization': 'Bearer ' + authToken } });
                if (!res.ok) {
                    const err = await res.json();
                    alert(err.detail || 'Action restricted.');
                }
                loadBlockades(true); loadNotifications(true);
            }

            function openPhotoModal(id) {
                activeResolvingId = id;
                document.getElementById('clearance-file').value = '';
                document.getElementById('photo-modal').classList.remove('hidden');
            }

            function closePhotoModal() {
                document.getElementById('photo-modal').classList.add('hidden');
                activeResolvingId = null;
            }

            async function submitClearancePhoto() {
                if (!activeResolvingId) return;
                const fileInput = document.getElementById('clearance-file');
                if (!fileInput.files[0]) {
                    alert('Please capture a live photo to verify clearance.');
                    return;
                }

                const formData = new FormData();
                formData.append('file', fileInput.files[0]);

                try {
                    const res = await fetch('/blockades/' + activeResolvingId + '/resolve-photo', {
                        method: 'POST',
                        headers: { 'Authorization': 'Bearer ' + authToken },
                        body: formData
                    });

                    if (!res.ok) {
                        const err = await res.json();
                        throw new Error(err.detail || 'Failed to upload clearance photo');
                    }

                    closePhotoModal();
                    loadBlockades(true);
                    loadNotifications(true);
                    if (authToken.toUpperCase() === 'TN-ADMIN-01') loadAdminPanelData(true);
                } catch (err) {
                    alert('Error: ' + err.message);
                }
            }

            async function clearResolved() {
                await fetch('/blockades/clear-resolved', { method: 'DELETE', headers: { 'Authorization': 'Bearer ' + authToken } });
                loadBlockades(true); loadNotifications(true);
                if (authToken.toUpperCase() === 'TN-ADMIN-01') loadAdminPanelData(true);
            }

            function logout() { localStorage.removeItem('token_8002'); location.reload(); }
        </script>
    </body>
    </html>
    """

@app.post("/auth/register", tags=["Authentication"])
def register_officer(reg: RegisterRequest, db: Session = Depends(get_db)):
    existing = db.query(User).filter(
        (User.badge_number == reg.badge_number) | (User.username == reg.badge_number)
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Officer already registered.")
    db.add(User(
        username=reg.badge_number,
        password=reg.password,
        name=reg.name,
        designation=reg.designation or "Sub-Inspector (SI)",
        email=reg.email,
        mobile=reg.mobile,
        badge_number=reg.badge_number,
        status="PENDING APPROVAL"
    ))
    db.commit()
    return {"message": "Success"}

@app.post("/auth/request-otp", tags=["Authentication"])
def request_otp(data: dict):
    return {"message": "OTP dispatched"}

@app.post("/auth/login", tags=["Authentication"])
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(
        (User.username == form_data.username) | (User.badge_number == form_data.username)
    ).first()
    if not user or user.password != form_data.password:
        raise HTTPException(status_code=401, detail="Incorrect badge ID or password")
    return {"access_token": user.username, "token_type": "bearer"}

@app.get("/admin/officers", tags=["Control Room Management"])
def get_admin_officers(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    if token.upper() != "TN-ADMIN-01":
        raise HTTPException(status_code=403, detail="Unauthorized")
    return db.query(User).all()

@app.post("/admin/officers/{badge_number}/approve", tags=["Control Room Management"])
def approve_officer(badge_number: str, token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    if token.upper() != "TN-ADMIN-01":
        raise HTTPException(status_code=403, detail="Unauthorized")
    officer = db.query(User).filter(User.badge_number == badge_number).first()
    if not officer:
        raise HTTPException(status_code=404, detail="Officer not found")
    officer.status = "ACTIVE"
    db.add(Notification(message=f"[CONTROL ROOM] {officer.designation} {officer.name} ({badge_number}) approved for active duty."))
    db.commit()
    return {"message": f"Officer {badge_number} approved"}

@app.put("/admin/officers/{badge_number}", tags=["Control Room Management"])
def admin_edit_officer(badge_number: str, payload: AdminEditOfficerRequest, token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    if token.upper() != "TN-ADMIN-01":
        raise HTTPException(status_code=403, detail="Only Control Room can edit officer accounts.")
    officer = db.query(User).filter(User.badge_number == badge_number).first()
    if not officer:
        raise HTTPException(status_code=404, detail="Officer not found")
    officer.name = payload.name
    if payload.designation:
        officer.designation = payload.designation
    officer.email = payload.email
    officer.mobile = payload.mobile
    officer.status = payload.status
    if payload.password and payload.password.strip() != "":
        officer.password = payload.password.strip()
    db.add(Notification(message=f"[CONTROL ROOM EDIT] Updated profile/rank for {officer.designation} {badge_number} ({officer.status})."))
    db.commit()
    return {"message": "Officer profile updated by Control Room", "status": officer.status}

@app.delete("/admin/officers/{badge_number}", tags=["Control Room Management"])
def admin_delete_officer(badge_number: str, token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    if token.upper() != "TN-ADMIN-01":
        raise HTTPException(status_code=403, detail="Only Control Room can delete officer accounts.")
    if badge_number.upper() == "TN-ADMIN-01":
        raise HTTPException(status_code=400, detail="Cannot delete primary Control Room account.")
    officer = db.query(User).filter(User.badge_number == badge_number).first()
    if not officer:
        raise HTTPException(status_code=404, detail="Officer not found")
    officer_name = officer.name
    db.delete(officer)
    db.add(Notification(message=f"[CONTROL ROOM DELETE] Removed Officer {badge_number} ({officer_name}) from tactical grid."))
    db.commit()
    return {"message": f"Officer {badge_number} deleted"}

@app.get("/api/profile", tags=["Officer Profile"])
def get_profile(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    user = db.query(User).filter(
        (User.username == token) | (User.badge_number == token)
    ).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {
        "name": user.name,
        "designation": user.designation or "Sub-Inspector (SI)",
        "email": user.email,
        "mobile": user.mobile,
        "badge_number": user.badge_number,
        "profile_photo": user.profile_photo,
        "status": user.status
    }

@app.put("/api/profile", tags=["Officer Profile"])
async def update_profile(
    name: str = Form(...),
    designation: Optional[str] = Form("Sub-Inspector (SI)"),
    email: str = Form(...),
    mobile: str = Form(...),
    password: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(
        (User.username == token) | (User.badge_number == token)
    ).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    user.name = name
    if designation:
        user.designation = designation
    user.email = email
    user.mobile = mobile
    if password:
        user.password = password
    if file:
        file_bytes = await file.read()
        base64_encoded = base64.b64encode(file_bytes).decode("utf-8")
        user.profile_photo = f"data:{file.content_type or 'image/jpeg'};base64,{base64_encoded}"
    
    if user.username.upper() != "TN-ADMIN-01":
        user.status = "PENDING APPROVAL"
        db.add(Notification(message=f"[PROFILE EDIT] {user.designation} {user.badge_number} updated profile details (Pending Control Room Approval)"))

    db.commit()
    return {"message": "Profile updated successfully", "status": user.status}

@app.get("/api/my-clearances", tags=["Officer Profile"])
def get_my_clearances(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    if token.upper() == "TN-ADMIN-01":
        return []
    user = db.query(User).filter(
        (User.username == token) | (User.badge_number == token)
    ).first()
    badge = user.badge_number if user else token
    uname = user.username if user else token
    name_str = user.name if user else token
    clearances = db.query(Blockade).filter(
        Blockade.status == "RESOLVED",
        (Blockade.resolved_by == token) |
        (Blockade.resolved_by == badge) |
        (Blockade.resolved_by == uname) |
        (Blockade.resolved_by == name_str)
    ).order_by(Blockade.id.desc()).limit(10).all()
    return clearances

@app.head("/blockades/", tags=["Tactical Blockades"])
@app.get("/blockades/", tags=["Tactical Blockades"])
def get_blockades(db: Session = Depends(get_db)):
    return db.query(Blockade).all()

@app.post("/blockades/reset-all", tags=["Tactical Blockades"])
def reset_all_blockades(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    if token.upper() != "TN-ADMIN-01":
        raise HTTPException(status_code=403, detail="Only Control Room can reset and spawn blockades.")
    db.query(Blockade).delete()
    db.add(Blockade(
        location_name="Kumbakonam Bypass Traffic Signal - Sector 2",
        latitude=10.9601,
        longitude=79.3845,
        severity="CRITICAL",
        status="ACTIVE",
        notes="Multi-vehicle collision blocking north signal lane",
        image_url="https://images.unsplash.com/photo-1542282088-72c9c27ed0cd?w=400&q=80",
        green_corridor=False,
        signal_color="R",
        blue_mode="A",
        created_at=datetime.utcnow()
    ))
    db.add(Notification(message="[CONTROL ROOM RESET] சிக்னல் தரவு மீட்டமைக்கப்பட்டது | Fresh incident respawned at Kumbakonam Bypass Traffic Signal."))
    db.commit()
    return {"message": "Database reset successfully. All incidents set to active."}

@app.post("/api/edge-trigger", tags=["Live Project Model Integration"])
@app.post("/api-edge-trigger", tags=["Live Project Model Integration"])
def trigger_from_project_model(payload: EdgeModelTrigger, db: Session = Depends(get_db)):
    if payload.api_key != EDGE_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid Edge API Key")
    
    img_data = payload.image_base64
    if img_data and not img_data.startswith("data:image"):
        img_data = f"data:image/jpeg;base64,{img_data}"

    new_b = Blockade(
        location_name=payload.location_name,
        latitude=payload.latitude,
        longitude=payload.longitude,
        severity=payload.severity,
        status="ACTIVE",
        notes=payload.notes,
        image_url=img_data,
        green_corridor=False,
        signal_color="R",
        blue_mode="A",
        created_at=datetime.utcnow()
    )
    db.add(new_b)
    db.add(Notification(
        message=f"[LIVE YOLO MODEL ALERT] 🚨 போக்குவரத்து தடை! Blockade @ {payload.location_name}",
        image_thumb=img_data
    ))
    db.commit()
    db.refresh(new_b)
    return {"status": "success", "incident_id": new_b.id}

@app.post("/blockades/simulate-ai", tags=["Edge-AI Simulation"])
def simulate_ai_trigger(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    if token.upper() != "TN-ADMIN-01":
        raise HTTPException(status_code=403, detail="Only Control Room can simulate AI hazards.")
    samples = [
        ("Mahamaham Tank West Traffic Signal", 10.9576, 79.3789, "CRITICAL", "Crowd surge & road obstruction", "https://images.unsplash.com/photo-1542282088-72c9c27ed0cd?w=400&q=80", "R", "A"),
        ("Mayiladuthurai Highway Signal Pole 02", 11.1018, 79.6524, "HIGH", "Emergency vehicle bottleneck", "https://images.unsplash.com/photo-1506521781263-d8422e82f27a?w=400&q=80", "Y", "S"),
        ("Trichy-Chennai NH-45 Signal Sector 9", 10.8254, 78.6921, "MEDIUM", "Sudden traffic halt detected", "https://images.unsplash.com/photo-1519003722824-194d4455a60c?w=400&q=80", "R", "B")
    ]
    loc, lat, lng, sev, note, img, sig_col, b_mode = random.choice(samples)
    new_b = Blockade(
        location_name=loc, latitude=lat, longitude=lng, severity=sev, status="ACTIVE",
        notes=note, image_url=img, green_corridor=False, signal_color=sig_col, blue_mode=b_mode,
        created_at=datetime.utcnow()
    )
    db.add(new_b)
    db.add(Notification(message=f"[EDGE-AI YOLO] 🚨 போக்குவரத்து தடை! {note} @ {loc}", image_thumb=img))
    db.commit()
    return new_b

def verify_active_field_officer(token: str, db: Session):
    if token.upper() == "TN-ADMIN-01":
        raise HTTPException(status_code=403, detail="Control Room Supervisor does not perform field dispatch or clearance actions.")
    user = db.query(User).filter(
        (User.username == token) | (User.badge_number == token)
    ).first()
    if not user:
        raise HTTPException(status_code=404, detail="Officer account not found.")
    if user.status != "ACTIVE":
        raise HTTPException(status_code=403, detail="Your account is PENDING APPROVAL by the Control Room. Field actions are locked.")
    return user

@app.post("/blockades/{blockade_id}/assign", tags=["Tactical Blockades"])
def assign_blockade(blockade_id: int, payload: Optional[dict] = None, token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    verify_active_field_officer(token, db)
    b = db.query(Blockade).filter(Blockade.id == blockade_id).first()
    if not b:
        raise HTTPException(status_code=404, detail="Blockade not found")
    b.status = "ASSIGNED"
    if payload and "latitude" in payload and "longitude" in payload:
        b.officer_lat = payload["latitude"]
        b.officer_lng = payload["longitude"]
    else:
        b.officer_lat = b.latitude + 0.008
        b.officer_lng = b.longitude + 0.008
    db.add(Notification(message=f"[DISPATCH] 🚓 காவலர் {token} விரைகிறார் | Unit {token} -> {b.location_name}", image_thumb=b.image_url))
    db.commit()
    return {"status": b.status, "officer_lat": b.officer_lat, "officer_lng": b.officer_lng}

@app.post("/blockades/{blockade_id}/arrived", tags=["Tactical Blockades"])
def mark_arrived(blockade_id: int, token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    verify_active_field_officer(token, db)
    b = db.query(Blockade).filter(Blockade.id == blockade_id).first()
    if not b:
        raise HTTPException(status_code=404, detail="Blockade not found")
    b.status = "ARRIVED"
    b.officer_lat = b.latitude
    b.officer_lng = b.longitude
    db.add(Notification(message=f"[ON SCENE] 📍 காவலர் {token} சிக்னலை அடைந்தார் | Arrived @ {b.location_name}", image_thumb=b.image_url))
    db.commit()
    return {"status": b.status}

@app.post("/blockades/{blockade_id}/telemetry", tags=["Officer Tracking"])
def update_officer_telemetry(blockade_id: int, data: TelemetryUpdate, token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    verify_active_field_officer(token, db)
    b = db.query(Blockade).filter(Blockade.id == blockade_id).first()
    if not b:
        raise HTTPException(status_code=404, detail="Blockade not found")
    b.officer_lat = data.latitude
    b.officer_lng = data.longitude
    db.commit()
    return {"status": "telemetry updated"}

@app.post("/blockades/{blockade_id}/resolve-photo", tags=["Tactical Blockades"])
async def resolve_with_photo(blockade_id: int, file: UploadFile = File(...), token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    user = verify_active_field_officer(token, db)
    b = db.query(Blockade).filter(Blockade.id == blockade_id).first()
    if not b:
        raise HTTPException(status_code=404, detail="Blockade not found")
    
    file_bytes = await file.read()
    base64_encoded = base64.b64encode(file_bytes).decode("utf-8")
    mime_type = file.content_type or "image/jpeg"
    data_uri = f"data:{mime_type};base64,{base64_encoded}"

    b.status = "RESOLVED"
    b.green_corridor = False
    b.signal_color = "G"
    b.blue_mode = "0"
    b.clearance_photo = data_uri
    b.resolved_by = user.badge_number or token
    db.add(Notification(message=f"[RESOLVED] ✅ தடை அகற்றப்பட்டது | Cleared @ {b.location_name} by {b.resolved_by}", image_thumb=data_uri))
    db.commit()
    return {"message": "Resolved with photo"}

@app.post("/blockades/{blockade_id}/resolve-photo-base64", tags=["Tactical Blockades"])
def resolve_with_photo_base64(blockade_id: int, payload: dict, token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    user = verify_active_field_officer(token, db)
    b = db.query(Blockade).filter(Blockade.id == blockade_id).first()
    if not b:
        raise HTTPException(status_code=404, detail="Blockade not found")
    
    img_data = payload.get("image_data") or payload.get("file")
    if img_data and not img_data.startswith("data:image"):
        img_data = f"data:image/jpeg;base64,{img_data}"

    b.status = "RESOLVED"
    b.green_corridor = False
    b.signal_color = "G"
    b.blue_mode = "0"
    b.clearance_photo = img_data
    b.resolved_by = user.badge_number or token
    db.add(Notification(message=f"[RESOLVED] ✅ தடை அகற்றப்பட்டது | Cleared @ {b.location_name} by {b.resolved_by}", image_thumb=b.clearance_photo))
    db.commit()
    return {"message": "Resolved via base64 photo"}

@app.delete("/blockades/clear-resolved", tags=["Tactical Blockades"])
def clear_resolved(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    if token.upper() != "TN-ADMIN-01":
        raise HTTPException(status_code=403, detail="Only Control Room can clear resolved records.")
    deleted = db.query(Blockade).filter(Blockade.status == "RESOLVED").delete()
    db.commit()
    return {"deleted": deleted}

@app.get("/notifications/", tags=["Notifications"])
def get_notifications(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    all_notifs = db.query(Notification).all()
    if token.upper() == "TN-ADMIN-01":
        return all_notifs
    officer_alerts = [
        n for n in all_notifs
        if ("[LIVE YOLO MODEL ALERT]" in (n.message or ""))
        or ("[EDGE-AI YOLO]" in (n.message or ""))
        or ("[SIMULATED AI]" in (n.message or ""))
        or ("[YOLO AI]" in (n.message or ""))
        or ("[BACKUP SOS]" in (n.message or ""))
        or ("[GREEN CORRIDOR]" in (n.message or ""))
        or ("[PTT VOICE]" in (n.message or ""))
    ]
    return officer_alerts