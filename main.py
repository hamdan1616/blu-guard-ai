from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from datetime import datetime
from typing import Optional
import os
import random
import base64

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

class Notification(Base):
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True, index=True)
    message = Column(String)
    image_thumb = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="நான்காம் காவல் நண்பன் | Naangham Kaaval Nanban - TN Police", 
    version="49.0"
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

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class RegisterRequest(BaseModel):
    name: str
    email: str
    mobile: str
    badge_number: str
    password: str

class AdminEditOfficerRequest(BaseModel):
    name: str
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

@app.on_event("startup")
def seed_initial_data():
    db = SessionLocal()
    if not db.query(User).filter(User.username == "TN-ADMIN-01").first():
        db.add(User(
            username="TN-ADMIN-01",
            password="Admin@123",
            name="Central Command Admin",
            email="admin@tnpolice.gov.in",
            mobile="9999999999",
            badge_number="TN-ADMIN-01",
            status="ACTIVE"
        ))
    if not db.query(User).filter(User.username == "test1").first():
        db.add(User(
            username="test1",
            password="password",
            name="Inspector Test Officer",
            email="tnpolice007@tn.gov.in",
            mobile="9876543210",
            badge_number="TN-POLICE-007",
            status="ACTIVE"
        ))
    
    if db.query(Blockade).filter(Blockade.status != "RESOLVED").count() == 0:
        db.add(Blockade(
            location_name="Kumbakonam Bypass Junction - Sector 2",
            latitude=10.9601,
            longitude=79.3845,
            severity="CRITICAL",
            status="ACTIVE",
            notes="Multi-vehicle collision blocking north lane",
            image_url="https://images.unsplash.com/photo-1542282088-72c9c27ed0cd?w=400&q=80"
        ))
    db.commit()
    db.close()

@app.get("/logo.png", include_in_schema=False)
def get_logo():
    if os.path.exists("logo.png"):
        return FileResponse("logo.png")
    raise HTTPException(status_code=404, detail="Logo not found")

@app.get("/", response_class=HTMLResponse, tags=["Frontend UI"])
def serve_frontend():
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>நான்காம் காவல் நண்பன் | Naangham Kaaval Nanban - Tamil Nadu Police</title>
        <script src="https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4"></script>
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
        <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
        <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
        <style>
            .leaflet-layer, .leaflet-control-zoom-in, .leaflet-control-zoom-out, .leaflet-control-attribution {
                filter: invert(100%) hue-rotate(190deg) brightness(95%) contrast(92%);
            }
            .leaflet-container { background: #070d19; }
            .tn-police-stripe {
                background: linear-gradient(90deg, #b91c1c 0%, #b91c1c 50%, #1e3a8a 50%, #1e3a8a 100%);
            }
            .gold-glow { box-shadow: 0 0 35px rgba(217, 119, 6, 0.35); }
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
    <body class="bg-[#081021] text-slate-100 min-h-screen font-sans overflow-y-auto">

        <div class="h-1.5 w-full tn-police-stripe"></div>

        <!-- LOGIN / REGISTER MODAL -->
        <div id="login-modal" class="fixed inset-0 bg-[#050b16]/92 backdrop-blur-md z-50 flex items-center justify-center p-4">
            <div class="bg-[#0d182e] border-2 border-amber-500/40 rounded-2xl w-full max-w-md p-7 gold-glow relative overflow-hidden">
                <div class="absolute top-0 left-0 right-0 h-1.5 tn-police-stripe"></div>

                <div class="text-center mb-5">
                    <div class="inline-flex items-center justify-center w-28 h-28 mb-2 rounded-full bg-[#070e1c] border-2 border-amber-400 p-1 shadow-2xl relative overflow-hidden">
                        <img src="/logo.png" alt="TN Police Logo" class="w-full h-full object-contain rounded-full">
                    </div>
                    <div class="text-[11px] font-bold uppercase tracking-widest text-amber-400">தமிழ்நாடு காவல்துறை • Tamil Nadu Police</div>
                    <h1 class="text-xl font-extrabold tracking-tight text-white mt-0.5">நான்காம் காவல் நண்பன்</h1>
                    <p class="text-xs font-semibold text-amber-300/90">NAANGHAM KAAVAL NANBAN</p>
                </div>

                <div class="grid grid-cols-2 gap-1 bg-[#070e1c] p-1 rounded-xl mb-5 border border-amber-500/20">
                    <button onclick="switchTab('login')" id="tab-login" class="py-2 text-xs font-bold rounded-lg bg-amber-500 text-slate-950 transition cursor-pointer">Officer Login</button>
                    <button onclick="switchTab('register')" id="tab-register" class="py-2 text-xs font-bold rounded-lg text-slate-300 hover:text-white transition cursor-pointer">New Registration</button>
                </div>

                <!-- LOGIN FORM -->
                <form id="form-login" onsubmit="handleLogin(event)" class="space-y-3.5">
                    <div>
                        <label class="block text-xs font-semibold text-amber-400/90 uppercase mb-1">Badge ID / Username</label>
                        <input type="text" id="login-username" required placeholder="Enter Badge ID (e.g. TN-ADMIN-01)" class="w-full bg-[#070e1c] border border-amber-500/30 rounded-lg px-3.5 py-2 text-sm text-white focus:outline-none focus:border-amber-400">
                    </div>
                    <div>
                        <label class="block text-xs font-semibold text-amber-400/90 uppercase mb-1">Password</label>
                        <div class="relative">
                            <input type="password" id="login-password" required placeholder="Enter Password" class="w-full bg-[#070e1c] border border-amber-500/30 rounded-lg px-3.5 py-2 pr-10 text-sm text-white focus:outline-none focus:border-amber-400">
                            <button type="button" onclick="togglePasswordVisibility('login-password', 'login-eye')" class="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-amber-400 cursor-pointer">
                                <i id="login-eye" class="fa-solid fa-eye"></i>
                            </button>
                        </div>
                    </div>
                    <button type="submit" class="w-full bg-gradient-to-r from-red-700 to-blue-800 hover:from-red-600 hover:to-blue-700 border border-amber-400/50 text-white font-bold py-2.5 rounded-lg transition text-sm cursor-pointer shadow-md">
                        <i class="fa-solid fa-shield-halved mr-1 text-amber-300"></i> Secure Login
                    </button>
                    <div id="login-error" class="text-center text-xs text-red-400 hidden"></div>
                </form>

                <!-- REGISTRATION FORM -->
                <div id="form-register" class="hidden space-y-3">
                    <div id="reg-step-1" class="space-y-3">
                        <div>
                            <label class="block text-[11px] font-semibold text-amber-400 uppercase mb-0.5">Officer Full Name</label>
                            <input type="text" id="reg-name" placeholder="e.g. Inspector K. Murugan" class="w-full bg-[#070e1c] border border-amber-500/30 rounded-lg px-3 py-1.5 text-xs text-white">
                        </div>
                        <div class="grid grid-cols-2 gap-2">
                            <div>
                                <label class="block text-[11px] font-semibold text-amber-400 uppercase mb-0.5">Badge ID</label>
                                <input type="text" id="reg-badge" placeholder="TN-POLICE-99" class="w-full bg-[#070e1c] border border-amber-500/30 rounded-lg px-3 py-1.5 text-xs text-white">
                            </div>
                            <div>
                                <label class="block text-[11px] font-semibold text-amber-400 uppercase mb-0.5">Mobile Number</label>
                                <input type="tel" id="reg-mobile" placeholder="9876543210" class="w-full bg-[#070e1c] border border-amber-500/30 rounded-lg px-3 py-1.5 text-xs text-white">
                            </div>
                        </div>
                        <div>
                            <label class="block text-[11px] font-semibold text-amber-400 uppercase mb-0.5">Official Email</label>
                            <input type="email" id="reg-email" placeholder="officer@tn.gov.in" class="w-full bg-[#070e1c] border border-amber-500/30 rounded-lg px-3 py-1.5 text-xs text-white">
                        </div>
                        <div>
                            <label class="block text-[11px] font-semibold text-amber-400 uppercase mb-0.5">Set Password</label>
                            <div class="relative">
                                <input type="password" id="reg-password" placeholder="••••••••" class="w-full bg-[#070e1c] border border-amber-500/30 rounded-lg px-3 py-1.5 pr-9 text-xs text-white">
                                <button type="button" onclick="togglePasswordVisibility('reg-password', 'reg-eye')" class="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-amber-400 cursor-pointer text-xs">
                                    <i id="reg-eye" class="fa-solid fa-eye"></i>
                                </button>
                            </div>
                        </div>
                        <button onclick="requestOTP()" class="w-full bg-amber-600 hover:bg-amber-500 text-slate-950 font-bold py-2 rounded-lg transition text-xs cursor-pointer shadow">
                            <i class="fa-solid fa-paper-plane mr-1"></i> Send Verification OTP (Mail/SMS)
                        </button>
                    </div>

                    <div id="reg-step-2" class="hidden space-y-3">
                        <div class="bg-blue-950/40 border border-blue-500/30 p-2.5 rounded-lg text-center">
                            <p class="text-xs text-blue-300">OTP dispatched to registered mobile & email.</p>
                            <p id="otp-hint" class="text-[11px] text-amber-400 font-mono mt-1 font-bold"></p>
                        </div>
                        <div>
                            <label class="block text-xs font-semibold text-amber-400 uppercase mb-1 text-center">Enter 6-Digit OTP Code</label>
                            <input type="text" id="reg-otp" maxlength="6" placeholder="123456" class="w-full text-center tracking-widest font-mono bg-[#070e1c] border border-amber-500/50 rounded-lg px-3 py-2 text-base text-amber-300">
                        </div>
                        <button onclick="verifyAndRegister()" class="w-full bg-emerald-600 hover:bg-emerald-500 text-white font-bold py-2.5 rounded-lg transition text-xs cursor-pointer shadow">
                            <i class="fa-solid fa-check-circle mr-1"></i> Verify OTP & Create Account
                        </button>
                        <div class="flex justify-between items-center pt-1">
                            <button type="button" onclick="resendOTP()" class="text-[11px] text-amber-400 hover:underline font-bold cursor-pointer">
                                <i class="fa-solid fa-rotate-right mr-1"></i> Resend OTP
                            </button>
                            <button type="button" onclick="backToRegStep1()" class="text-[11px] text-slate-400 hover:text-white cursor-pointer">
                                ← Edit Details
                            </button>
                        </div>
                    </div>
                    <div id="reg-error" class="text-center text-xs text-red-400 hidden"></div>
                </div>

                <div class="mt-5 pt-3 border-t border-slate-800 text-center">
                    <p class="text-[10px] text-slate-500 italic">Designed & Developed by Mohamed Hamdan</p>
                </div>
            </div>
        </div>

        <!-- MAIN TACTICAL DASHBOARD -->
        <div id="dashboard" class="hidden flex flex-col min-h-screen">
            <header class="bg-[#0d182e] border-b-2 border-amber-500/40 px-6 py-2.5 flex flex-wrap justify-between items-center gap-3 shadow-md">
                <div class="flex items-center space-x-3.5">
                    <img src="/logo.png" class="w-10 h-10 object-contain rounded-full border border-amber-500/40 bg-slate-900" alt="Emblem">
                    <div>
                        <div class="flex items-center space-x-2">
                            <h2 class="font-extrabold text-base tracking-wide text-white">நான்காம் காவல் நண்பன்</h2>
                            <span class="text-xs font-bold text-amber-300 bg-amber-500/15 border border-amber-400/30 px-2 py-0.5 rounded">NAANGHAM KAAVAL NANBAN</span>
                            <span id="grid-status-badge" class="text-[11px] font-semibold px-2 py-0.5 rounded flex items-center gap-1 transition-all">
                                <span id="grid-dot" class="w-2 h-2 rounded-full"></span> <span id="grid-text">CONNECTING...</span>
                            </span>
                        </div>
                        <p class="text-[11px] text-slate-400">Tamil Nadu Police Integrated Tactical Command • सत्यमेव जयते</p>
                    </div>
                </div>

                <div class="flex items-center space-x-2.5">
                    <!-- ADMIN-ONLY ACTION BUTTONS -->
                    <div id="admin-action-btns" class="hidden flex items-center space-x-2">
                        <button onclick="resetDatabase()" class="bg-blue-700/30 hover:bg-blue-700/50 border border-blue-400/40 text-blue-300 px-3 py-1.5 rounded-lg text-xs font-bold transition cursor-pointer flex items-center gap-1.5">
                            <i class="fa-solid fa-rotate-right"></i> Reset & Spawn Active
                        </button>
                        <button onclick="simulateAITrigger()" class="bg-red-700/30 hover:bg-red-700/50 border border-amber-400/40 text-amber-300 px-3 py-1.5 rounded-lg text-xs font-bold transition cursor-pointer flex items-center gap-1.5">
                            <i class="fa-solid fa-satellite-dish text-red-400"></i> Simulate AI Hazard
                        </button>
                    </div>
                    <a href="/docs" target="_blank" class="text-xs text-amber-400 hover:underline px-2 font-medium">API /docs ↗</a>
                    
                    <div class="relative">
                        <button onclick="toggleProfileMenu()" class="bg-slate-800 hover:bg-slate-700 border border-amber-500/40 text-amber-300 px-3 py-1.5 rounded-lg text-xs font-semibold transition cursor-pointer flex items-center gap-2">
                            <i class="fa-solid fa-user-shield"></i> <span id="user-badge">Officer</span> <i class="fa-solid fa-caret-down text-[10px]"></i>
                        </button>
                        <div id="profile-dropdown" class="hidden absolute right-0 mt-2 w-52 bg-[#0d182e] border border-amber-500/40 rounded-xl shadow-2xl z-50 overflow-hidden py-1">
                            <button onclick="openProfileModal()" class="w-full text-left px-4 py-2.5 text-xs text-slate-200 hover:bg-amber-500/20 hover:text-amber-300 transition flex items-center gap-2 cursor-pointer">
                                <i class="fa-solid fa-id-card text-amber-400"></i> View & Edit Profile
                            </button>
                            <button id="menu-my-clearances" onclick="openClearancesModal()" class="w-full text-left px-4 py-2.5 text-xs text-slate-200 hover:bg-amber-500/20 hover:text-amber-300 transition flex items-center gap-2 cursor-pointer">
                                <i class="fa-solid fa-clipboard-check text-emerald-400"></i> My Last 10 Clearances
                            </button>
                            <div class="border-t border-slate-700 my-1"></div>
                            <button onclick="logout()" class="w-full text-left px-4 py-2.5 text-xs text-red-400 hover:bg-red-950/40 transition flex items-center gap-2 cursor-pointer">
                                <i class="fa-solid fa-right-from-bracket"></i> Logout
                            </button>
                        </div>
                    </div>
                </div>
            </header>

            <!-- PENDING APPROVAL WARNING BANNER -->
            <div id="pending-banner" class="hidden bg-amber-600/20 border-b border-amber-500/50 py-2 px-6 text-center text-xs font-bold text-amber-300">
                ⏳ YOUR ACCOUNT STATUS IS "PENDING APPROVAL" BY CENTRAL COMMAND ADMIN. FIELD ACTIONS ARE RESTRICTED.
            </div>

            <!-- ADMIN SUPERVISOR PANEL -->
            <div id="admin-panel" class="hidden bg-[#0d182e] border-b-2 border-amber-500/30 p-4 px-6">
                <div class="flex justify-between items-center mb-3">
                    <h3 class="font-bold text-xs uppercase tracking-wider text-amber-400 flex items-center gap-2">
                        <i class="fa-solid fa-shield-cat text-amber-300"></i> Central Command Supervisor: Officer Approvals, Profile Editor & Department Oversight
                    </h3>
                    <span class="text-[11px] bg-amber-500/20 text-amber-300 px-2 py-0.5 rounded font-bold">ADMIN SUPERVISOR ACCESS</span>
                </div>
                <div class="grid grid-cols-1 md:grid-cols-2 gap-4 max-h-64 overflow-y-auto">
                    <div class="bg-[#070e1c] border border-amber-500/20 rounded-lg p-3">
                        <h4 class="text-xs font-bold text-slate-300 mb-2">Registered Officer Accounts (Approve or Edit Any Profile)</h4>
                        <div id="admin-officers-list" class="space-y-2 text-xs text-slate-300"></div>
                    </div>
                    <div class="bg-[#070e1c] border border-emerald-500/20 rounded-lg p-3">
                        <h4 class="text-xs font-bold text-emerald-400 mb-2">All Department Verified Clearances & Proof Photos</h4>
                        <div id="admin-clearances-list" class="space-y-2 text-xs text-slate-300"></div>
                    </div>
                </div>
            </div>

            <div class="flex-1 grid grid-cols-1 lg:grid-cols-12 gap-5 p-5">
                <div class="lg:col-span-4 bg-[#0d182e] border border-amber-500/30 rounded-xl p-4 flex flex-col space-y-4 shadow-lg">
                    <div class="flex items-center justify-between border-b border-slate-800 pb-1.5">
                        <h3 class="font-bold text-xs uppercase tracking-wider text-amber-400">Active Field Incidents & Blockades</h3>
                        <div class="flex items-center space-x-2">
                            <button id="btn-clear-resolved" onclick="clearResolved()" class="hidden text-[11px] text-slate-400 hover:text-red-400 cursor-pointer">Clear Resolved</button>
                            <button onclick="loadBlockades()" class="text-amber-400 hover:text-amber-300 text-xs cursor-pointer"><i class="fa-solid fa-rotate"></i></button>
                        </div>
                    </div>
                    <div id="blockade-list" class="space-y-2.5 pr-1 max-h-[650px] overflow-y-auto"></div>
                </div>

                <div class="lg:col-span-8 flex flex-col gap-5">
                    <div class="bg-[#0d182e] border border-amber-500/30 rounded-xl p-3 flex flex-col relative min-h-[420px] shadow-lg">
                        <div class="flex flex-wrap justify-between items-center mb-2 px-1 gap-2">
                            <span class="text-xs font-bold uppercase tracking-wider text-amber-400">
                                <i class="fa-solid fa-map-location-dot text-red-500 mr-1.5"></i>TN Police Geo-Radar Grid (Live Officer & Hazard Tracking)
                            </span>
                            <div class="flex items-center gap-3 text-[11px]">
                                <span class="flex items-center gap-1"><span class="w-2.5 h-2.5 rounded-full bg-red-500 inline-block"></span> Critical</span>
                                <span class="flex items-center gap-1"><span class="w-2.5 h-2.5 rounded-full bg-amber-500 inline-block"></span> High</span>
                                <span class="flex items-center gap-1"><i class="fa-solid fa-shield-halved text-blue-400"></i> Dispatched Officer</span>
                                <span class="flex items-center gap-1"><span class="w-2.5 h-2.5 rounded-full bg-emerald-500 inline-block"></span> Cleared</span>
                            </div>
                        </div>
                        <div id="map" class="w-full h-[400px] rounded-lg border border-amber-500/20 z-10"></div>
                    </div>

                    <div class="bg-[#0d182e] border border-amber-500/30 rounded-xl p-4 flex flex-col shadow-lg">
                        <div class="flex justify-between items-center mb-2">
                            <h3 id="wireless-log-heading" class="font-bold text-xs uppercase tracking-wider text-amber-400">
                                <i class="fa-solid fa-walkie-talkie text-red-400 mr-1.5"></i>TN Police Wireless & Blockade Alert Feed
                            </h3>
                            <span class="text-[11px] text-amber-300 bg-amber-500/10 border border-amber-400/30 px-2 py-0.5 rounded">Live Edge-AI Receiver Ready</span>
                        </div>
                        <div id="notification-box" class="h-48 bg-[#070e1c] border border-slate-800 rounded-lg p-3 overflow-y-auto space-y-2 font-mono text-xs text-slate-200"></div>
                    </div>
                </div>
            </div>

            <footer class="bg-[#0d182e] border-t border-amber-500/20 py-2.5 text-center text-xs text-slate-400">
                நான்காம் காவல் நண்பன் • <span class="text-amber-400 font-semibold">Designed & Developed by Mohamed Hamdan</span>
            </footer>
        </div>

        <!-- OFFICER SELF PROFILE EDIT MODAL -->
        <div id="profile-modal" class="fixed inset-0 bg-black/85 backdrop-blur-sm z-50 flex items-center justify-center p-4 hidden">
            <div class="bg-[#0d182e] border-2 border-amber-500/50 rounded-2xl max-w-md w-full p-6 space-y-4 shadow-2xl relative">
                <div class="flex justify-between items-center border-b border-slate-800 pb-3">
                    <h3 class="font-bold text-sm text-amber-400 uppercase"><i class="fa-solid fa-id-card mr-2"></i>Officer Profile & Settings</h3>
                    <button onclick="closeProfileModal()" class="text-slate-400 hover:text-white text-xs cursor-pointer"><i class="fa-solid fa-xmark text-base"></i></button>
                </div>
                <form id="profile-form" onsubmit="updateProfile(event)" class="space-y-3">
                    <div class="flex flex-col items-center justify-center space-y-2">
                        <div class="w-20 h-20 rounded-full bg-[#070e1c] border-2 border-amber-400 overflow-hidden flex items-center justify-center">
                            <img id="profile-avatar-preview" src="/logo.png" class="w-full h-full object-cover">
                        </div>
                        <label class="text-[11px] text-amber-300 cursor-pointer hover:underline">
                            Change Profile Photo <input type="file" id="profile-photo-input" accept="image/*" class="hidden" onchange="previewAvatar(event)">
                        </label>
                    </div>
                    <div>
                        <label class="block text-[11px] font-semibold text-amber-400 uppercase mb-1">Full Name</label>
                        <input type="text" id="profile-name" required class="w-full bg-[#070e1c] border border-amber-500/30 rounded-lg px-3 py-1.5 text-xs text-white">
                    </div>
                    <div class="grid grid-cols-2 gap-2">
                        <div>
                            <label class="block text-[11px] font-semibold text-amber-400 uppercase mb-1">Badge ID</label>
                            <input type="text" id="profile-badge" disabled class="w-full bg-[#070e1c]/50 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-slate-400 cursor-not-allowed">
                        </div>
                        <div>
                            <label class="block text-[11px] font-semibold text-amber-400 uppercase mb-1">Mobile Number</label>
                            <input type="tel" id="profile-mobile" required class="w-full bg-[#070e1c] border border-amber-500/30 rounded-lg px-3 py-1.5 text-xs text-white">
                        </div>
                    </div>
                    <div>
                        <label class="block text-[11px] font-semibold text-amber-400 uppercase mb-1">Official Email</label>
                        <input type="email" id="profile-email" required class="w-full bg-[#070e1c] border border-amber-500/30 rounded-lg px-3 py-1.5 text-xs text-white">
                    </div>
                    <div>
                        <label class="block text-[11px] font-semibold text-amber-400 uppercase mb-1">New Password (Optional)</label>
                        <div class="relative">
                            <input type="password" id="profile-password" placeholder="Leave blank to keep current" class="w-full bg-[#070e1c] border border-amber-500/30 rounded-lg px-3 py-1.5 pr-9 text-xs text-white">
                            <button type="button" onclick="togglePasswordVisibility('profile-password', 'profile-eye')" class="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-amber-400 cursor-pointer text-xs">
                                <i id="profile-eye" class="fa-solid fa-eye"></i>
                            </button>
                        </div>
                    </div>
                    <div class="flex space-x-2 pt-2">
                        <button type="submit" class="flex-1 bg-amber-600 hover:bg-amber-500 text-slate-950 font-bold py-2 rounded-lg text-xs cursor-pointer shadow">Save Changes</button>
                        <button type="button" onclick="closeProfileModal()" class="bg-slate-700 hover:bg-slate-600 text-white px-4 py-2 rounded-lg text-xs cursor-pointer">Cancel</button>
                    </div>
                    <div id="profile-msg" class="text-center text-xs text-emerald-400 hidden"></div>
                </form>
            </div>
        </div>

        <!-- ADMIN EDIT ANY OFFICER PROFILE MODAL -->
        <div id="admin-edit-modal" class="fixed inset-0 bg-black/85 backdrop-blur-sm z-50 flex items-center justify-center p-4 hidden">
            <div class="bg-[#0d182e] border-2 border-blue-500/50 rounded-2xl max-w-md w-full p-6 space-y-4 shadow-2xl relative">
                <div class="flex justify-between items-center border-b border-slate-800 pb-3">
                    <h3 class="font-bold text-sm text-blue-400 uppercase"><i class="fa-solid fa-user-pen mr-2"></i>Admin Supervisor: Edit Officer Profile</h3>
                    <button onclick="closeAdminEditModal()" class="text-slate-400 hover:text-white text-xs cursor-pointer"><i class="fa-solid fa-xmark text-base"></i></button>
                </div>
                <form onsubmit="submitAdminOfficerEdit(event)" class="space-y-3">
                    <div>
                        <label class="block text-[11px] font-semibold text-amber-400 uppercase mb-1">Target Badge ID</label>
                        <input type="text" id="admin-edit-badge" disabled class="w-full bg-[#070e1c]/60 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-slate-400">
                    </div>
                    <div>
                        <label class="block text-[11px] font-semibold text-amber-400 uppercase mb-1">Officer Full Name</label>
                        <input type="text" id="admin-edit-name" required class="w-full bg-[#070e1c] border border-amber-500/30 rounded-lg px-3 py-1.5 text-xs text-white">
                    </div>
                    <div class="grid grid-cols-2 gap-2">
                        <div>
                            <label class="block text-[11px] font-semibold text-amber-400 uppercase mb-1">Mobile Number</label>
                            <input type="text" id="admin-edit-mobile" required class="w-full bg-[#070e1c] border border-amber-500/30 rounded-lg px-3 py-1.5 text-xs text-white">
                        </div>
                        <div>
                            <label class="block text-[11px] font-semibold text-amber-400 uppercase mb-1">Account Status</label>
                            <select id="admin-edit-status" class="w-full bg-[#070e1c] border border-amber-500/30 rounded-lg px-2 py-1.5 text-xs text-white">
                                <option value="ACTIVE">ACTIVE</option>
                                <option value="PENDING APPROVAL">PENDING APPROVAL</option>
                            </select>
                        </div>
                    </div>
                    <div>
                        <label class="block text-[11px] font-semibold text-amber-400 uppercase mb-1">Official Email</label>
                        <input type="email" id="admin-edit-email" required class="w-full bg-[#070e1c] border border-amber-500/30 rounded-lg px-3 py-1.5 text-xs text-white">
                    </div>
                    <div>
                        <label class="block text-[11px] font-semibold text-amber-400 uppercase mb-1">Reset Password (Optional)</label>
                        <div class="relative">
                            <input type="password" id="admin-edit-password" placeholder="Leave blank to keep existing" class="w-full bg-[#070e1c] border border-amber-500/30 rounded-lg px-3 py-1.5 pr-9 text-xs text-white">
                            <button type="button" onclick="togglePasswordVisibility('admin-edit-password', 'admin-edit-eye')" class="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-amber-400 cursor-pointer text-xs">
                                <i id="admin-edit-eye" class="fa-solid fa-eye"></i>
                            </button>
                        </div>
                    </div>
                    <div class="flex space-x-2 pt-2">
                        <button type="submit" class="flex-1 bg-blue-600 hover:bg-blue-500 text-white font-bold py-2 rounded-lg text-xs cursor-pointer shadow">Update Officer Account</button>
                        <button type="button" onclick="closeAdminEditModal()" class="bg-slate-700 hover:bg-slate-600 text-white px-4 py-2 rounded-lg text-xs cursor-pointer">Cancel</button>
                    </div>
                </form>
            </div>
        </div>

        <!-- CLEARANCES MODAL (OFFICERS ONLY) -->
        <div id="clearances-modal" class="fixed inset-0 bg-black/85 backdrop-blur-sm z-50 flex items-center justify-center p-4 hidden">
            <div class="bg-[#0d182e] border-2 border-emerald-500/50 rounded-2xl max-w-2xl w-full p-6 space-y-4 shadow-2xl flex flex-col max-h-[85vh]">
                <div class="flex justify-between items-center border-b border-slate-800 pb-3">
                    <h3 class="font-bold text-sm text-emerald-400 uppercase"><i class="fa-solid fa-clipboard-check mr-2"></i>My Last 10 Blockade Clearances</h3>
                    <button onclick="closeClearancesModal()" class="text-slate-400 hover:text-white text-xs cursor-pointer"><i class="fa-solid fa-xmark text-base"></i></button>
                </div>
                <div id="clearances-list" class="flex-1 overflow-y-auto space-y-3 pr-1"></div>
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
                    <button onclick="submitClearancePhoto()" class="flex-1 bg-emerald-600 hover:bg-emerald-500 text-white font-bold py-2.5 rounded text-xs cursor-pointer shadow">Submit Live Proof</button>
                    <button onclick="closePhotoModal()" class="bg-slate-700 hover:bg-slate-600 text-white px-3 py-2.5 rounded text-xs cursor-pointer">Cancel</button>
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

            function playTacticalSirenAndVoice(message) {
                try {
                    const sirenAudio = new Audio('https://assets.mixkit.co/active_storage/sfx/2869/2869-preview.mp3');
                    sirenAudio.volume = 0.85;
                    sirenAudio.play().catch(err => {});
                } catch (e) {}

                try {
                    if ('speechSynthesis' in window) {
                        window.speechSynthesis.cancel();
                        const cleanText = message.replace(/\\[.*?\\]/g, '').replace(/@/g, 'at');
                        const isAdmin = authToken.toUpperCase() === 'TN-ADMIN-01';
                        const spokenPrompt = isAdmin 
                            ? `Attention Control Room! Police Emergency Alert! ${cleanText}`
                            : `Attention Field Officer! Traffic Blockade and Congestion Alert! ${cleanText}. Proceed for immediate clearance.`;
                        const utter = new SpeechSynthesisUtterance(spokenPrompt);
                        utter.lang = 'en-IN';
                        utter.rate = 1.0;
                        window.speechSynthesis.speak(utter);
                    }
                } catch (e) {}
            }

            function showWebPopupBanner(message) {
                const isAdmin = authToken.toUpperCase() === 'TN-ADMIN-01';
                const headerTitle = isAdmin ? '🚨 Control Room Tactical Alert' : '🚨 Officer Blockade & Congestion Alert';
                const toast = document.createElement('div');
                toast.className = 'fixed top-16 right-6 z-50 bg-red-900/95 border-2 border-amber-400 text-white px-4 py-3 rounded-xl shadow-2xl max-w-sm animate-bounce';
                toast.innerHTML = `<div class="text-xs font-extrabold text-amber-300 uppercase">${headerTitle}</div><div class="text-xs mt-1">${message}</div>`;
                document.body.appendChild(toast);
                playTacticalSirenAndVoice(message);
                setTimeout(() => toast.remove(), 7500);
            }

            setInterval(async () => {
                const badge = document.getElementById('grid-status-badge');
                const dot = document.getElementById('grid-dot');
                const text = document.getElementById('grid-text');
                try {
                    const res = await fetch('/blockades/', { method: 'HEAD' });
                    if (res.ok) {
                        badge.className = 'text-[11px] font-semibold px-2 py-0.5 rounded flex items-center gap-1 bg-emerald-500/10 border border-emerald-500/30 text-emerald-400';
                        dot.className = 'w-2 h-2 rounded-full bg-emerald-400 animate-ping';
                        text.innerText = 'SECURE GRID LIVE';
                        if (authToken && !document.getElementById('dashboard').classList.contains('hidden')) {
                            checkMyProfileStatus();
                            loadBlockades();
                            loadNotifications();
                            if (authToken.toUpperCase() === 'TN-ADMIN-01') loadAdminPanelData();
                        }
                    } else { throw new Error(); }
                } catch (e) {
                    badge.className = 'text-[11px] font-semibold px-2 py-0.5 rounded flex items-center gap-1 bg-red-500/20 border border-red-500/40 text-red-400';
                    dot.className = 'w-2 h-2 rounded-full bg-red-500';
                    text.innerText = 'SECURE GRID OFFLINE';
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
                    loadBlockades();
                    loadNotifications();
                    alert('Database reset! All resolved alerts cleared and a fresh ACTIVE incident has been spawned.');
                } else {
                    alert('Unauthorized: Only Central Command Admin can reset the database.');
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
                        msg.innerText = authToken.toUpperCase() === 'TN-ADMIN-01' ? 'Supervisor profile updated!' : 'Profile updated! Status set to PENDING APPROVAL.';
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
                    loadAdminPanelData();
                    alert(`Officer ${badge} profile updated by Admin.`);
                } else {
                    alert('Failed to update officer profile.');
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
                                <div class="bg-[#070e1c] border border-emerald-500/30 p-3 rounded-xl flex items-center justify-between gap-4">
                                    <div class="space-y-1">
                                        <div class="flex items-center gap-2">
                                            <span class="text-xs font-bold text-amber-400">#${idx + 1} - ${b.location_name}</span>
                                            <span class="text-[10px] bg-emerald-500/20 text-emerald-300 px-2 py-0.5 rounded font-bold">RESOLVED BY YOU</span>
                                        </div>
                                        <p class="text-[11px] text-slate-300">${b.notes || 'No notes'}</p>
                                    </div>
                                    ${b.clearance_photo ? `<img src="${b.clearance_photo}" class="w-16 h-16 object-cover rounded-lg border border-emerald-500/40 shrink-0">` : ''}
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
                    loginTab.className = 'py-2 text-xs font-bold rounded-lg bg-amber-500 text-slate-950 transition cursor-pointer';
                    regTab.className = 'py-2 text-xs font-bold rounded-lg text-slate-300 hover:text-white transition cursor-pointer';
                    loginForm.classList.remove('hidden');
                    regForm.classList.add('hidden');
                } else {
                    regTab.className = 'py-2 text-xs font-bold rounded-lg bg-amber-500 text-slate-950 transition cursor-pointer';
                    loginTab.className = 'py-2 text-xs font-bold rounded-lg text-slate-300 hover:text-white transition cursor-pointer';
                    regForm.classList.remove('hidden');
                    loginForm.classList.add('hidden');
                }
            }

            async function requestOTP() {
                const name = document.getElementById('reg-name').value;
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

                tempRegData = { name, badge_number: badge, mobile, email, password };
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

                alert('Officer account registered successfully! Awaiting Admin approval.');
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
                document.getElementById('user-badge').innerText = authToken;

                const isAdmin = authToken.toUpperCase() === 'TN-ADMIN-01';
                const logHeading = document.getElementById('wireless-log-heading');
                if (isAdmin) {
                    document.getElementById('admin-panel').classList.remove('hidden');
                    document.getElementById('admin-action-btns').classList.remove('hidden');
                    document.getElementById('btn-clear-resolved').classList.remove('hidden');
                    document.getElementById('menu-my-clearances').classList.add('hidden');
                    logHeading.innerHTML = `<i class="fa-solid fa-walkie-talkie text-red-400 mr-1.5"></i>Control Room Master Wireless & Telemetry Log`;
                    loadAdminPanelData();
                } else {
                    document.getElementById('admin-panel').classList.add('hidden');
                    document.getElementById('admin-action-btns').classList.add('hidden');
                    document.getElementById('btn-clear-resolved').classList.add('hidden');
                    document.getElementById('menu-my-clearances').classList.remove('hidden');
                    logHeading.innerHTML = `<i class="fa-solid fa-triangle-exclamation text-amber-400 mr-1.5"></i>Officer Blockade & Congestion Alert Feed`;
                }

                setTimeout(() => {
                    initMap();
                    checkMyProfileStatus();
                    loadBlockades();
                    loadNotifications();
                }, 100);
            }

            async function loadAdminPanelData() {
                try {
                    const offRes = await fetch('/admin/officers', { headers: { 'Authorization': 'Bearer ' + authToken } });
                    if (offRes.ok) {
                        cachedOfficers = await offRes.json();
                        const offContainer = document.getElementById('admin-officers-list');
                        offContainer.innerHTML = '';
                        cachedOfficers.forEach(o => {
                            let badgeStyle = o.status === 'ACTIVE' ? 'bg-emerald-500/20 text-emerald-400' : 'bg-amber-500/20 text-amber-400';
                            offContainer.innerHTML += `
                                <div class="flex items-center justify-between border-b border-slate-800 pb-1.5">
                                    <div><strong>${o.name}</strong> (${o.badge_number})<br><span class="text-[10px] text-slate-400">${o.email} • ${o.mobile}</span></div>
                                    <div class="flex items-center gap-1.5">
                                        <span class="text-[10px] px-2 py-0.5 rounded font-bold ${badgeStyle}">${o.status}</span>
                                        ${o.status === 'PENDING APPROVAL' ? `<button onclick="approveOfficer('${o.badge_number}')" class="bg-emerald-600 hover:bg-emerald-500 text-white text-[10px] px-2 py-1 rounded cursor-pointer">Approve</button>` : ''}
                                        <button onclick="openAdminEditModal('${o.badge_number}')" class="bg-blue-600/40 hover:bg-blue-600 border border-blue-400/40 text-blue-200 text-[10px] px-2 py-1 rounded cursor-pointer"><i class="fa-solid fa-pen"></i> Edit</button>
                                    </div>
                                </div>
                            `;
                        });
                    }

                    const res = await fetch('/blockades/');
                    const data = await res.json();
                    const container = document.getElementById('admin-clearances-list');
                    if (container) {
                        container.innerHTML = '';
                        const resolved = data.filter(b => b.status === 'RESOLVED');
                        if (resolved.length === 0) {
                            container.innerHTML = '<p class="text-xs text-slate-500">No clearances logged yet.</p>';
                        } else {
                            resolved.forEach((b) => {
                                container.innerHTML += `
                                    <div class="flex items-center justify-between border-b border-slate-800 pb-1.5 gap-2">
                                        <div>📍 <strong class="text-white">${b.location_name}</strong><br><span class="text-[10px] text-amber-300">Resolved by: ${b.resolved_by || 'Officer'}</span></div>
                                        ${b.clearance_photo ? `<a href="${b.clearance_photo}" target="_blank"><img src="${b.clearance_photo}" class="w-12 h-12 object-cover rounded border border-emerald-500/40 shrink-0"></a>` : '<span class="text-[10px] text-slate-500">No Photo</span>'}
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
                loadAdminPanelData();
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
                    errDiv.innerText = 'Incorrect badge ID or password.';
                    errDiv.classList.remove('hidden');
                }
            }

            async function simulateAITrigger() {
                const res = await fetch('/blockades/simulate-ai', {
                    method: 'POST',
                    headers: { 'Authorization': 'Bearer ' + authToken }
                });
                if (res.ok) {
                    loadBlockades();
                    loadNotifications();
                } else {
                    alert('Unauthorized: Only Central Command Admin can simulate AI hazards.');
                }
            }

            async function loadBlockades() {
                const res = await fetch('/blockades/');
                const data = await res.json();
                const container = document.getElementById('blockade-list');
                if (!container) return;
                container.innerHTML = '';

                if (markersLayer) markersLayer.clearLayers();
                const isAdmin = authToken.toUpperCase() === 'TN-ADMIN-01';

                data.slice().reverse().forEach(b => {
                    const isResolved = b.status === 'RESOLVED';
                    const isAssignedOrArrived = b.status === 'ASSIGNED' || b.status === 'ARRIVED';
                    const badgeColor = b.severity === 'CRITICAL' ? 'bg-red-600/25 text-red-300 border-red-500/40' :
                                       b.severity === 'HIGH' ? 'bg-amber-500/20 text-amber-300 border-amber-500/40' :
                                       'bg-blue-600/25 text-blue-300 border-blue-500/40';

                    let imgHtml = b.image_url ? `<img src="${b.image_url}" class="w-full h-28 object-cover rounded border border-slate-700 mt-1 mb-1">` : '';
                    let clearanceHtml = b.clearance_photo ? `
                        <div class="mt-1 p-1.5 bg-emerald-950/40 border border-emerald-500/30 rounded">
                            <div class="text-[10px] text-emerald-400 font-bold mb-1"><i class="fa-solid fa-camera"></i> Live Clearance Verified (By: ${b.resolved_by || 'Officer'}):</div>
                            <img src="${b.clearance_photo}" class="w-full h-20 object-cover rounded">
                        </div>` : '';

                    let actionBtnsHtml = '';
                    if (!isAdmin) {
                        if (currentUserStatus !== 'ACTIVE') {
                            actionBtnsHtml = `<span class="text-[10px] text-amber-400 font-semibold">⏳ Pending Admin Approval</span>`;
                        } else {
                            if (b.status === 'ACTIVE') actionBtnsHtml = `<button onclick="assignUnit(${b.id})" class="bg-blue-700/40 hover:bg-blue-700/60 border border-blue-400/30 text-blue-200 text-[11px] px-2.5 py-0.5 rounded transition cursor-pointer">Dispatch</button>`;
                            if (b.status === 'ASSIGNED') actionBtnsHtml = `<button onclick="markArrived(${b.id})" class="bg-amber-700/40 hover:bg-amber-700/60 border border-amber-400/30 text-amber-200 text-[11px] px-2.5 py-0.5 rounded transition cursor-pointer">Arrived</button>`;
                            if (b.status === 'ARRIVED') actionBtnsHtml = `<button onclick="openPhotoModal(${b.id})" class="bg-emerald-700/40 hover:bg-emerald-700/60 border border-emerald-400/30 text-emerald-200 text-[11px] px-2.5 py-0.5 rounded transition cursor-pointer">Live Camera Clear</button>`;
                        }
                    } else {
                        actionBtnsHtml = `<span class="text-[10px] text-slate-500 italic">Supervisor View</span>`;
                    }

                    container.innerHTML += `
                        <div class="bg-[#070e1c] border ${isResolved ? 'border-emerald-500/40' : 'border-amber-500/25'} p-3 rounded-lg space-y-2">
                            <div class="flex justify-between items-start">
                                <div onclick="focusMap(${b.latitude}, ${b.longitude})" class="cursor-pointer">
                                    <h4 class="font-bold text-xs text-white hover:text-amber-400">${b.location_name}</h4>
                                    <p class="text-[11px] text-slate-400">${b.notes || ''}</p>
                                </div>
                                <span class="text-[10px] font-bold px-2 py-0.5 border rounded ${badgeColor}">${b.severity}</span>
                            </div>
                            ${imgHtml}
                            ${clearanceHtml}
                            <div class="flex justify-between items-center pt-1 border-t border-slate-800/80">
                                <span class="text-[11px] text-slate-400">Status: <strong class="${isResolved ? 'text-emerald-400' : 'text-amber-300'}">${b.status}</strong></span>
                                <div class="space-x-1.5 flex items-center">${actionBtnsHtml}</div>
                            </div>
                        </div>`;

                    if (markersLayer && b.latitude && b.longitude) {
                        const markerColor = isResolved ? '#10b981' : (b.severity === 'CRITICAL' ? '#ef4444' : '#f59e0b');
                        const circle = L.circleMarker([b.latitude, b.longitude], {
                            radius: 9, fillColor: markerColor, color: '#fbbf24', weight: 2, opacity: 1, fillOpacity: 0.9
                        }).bindPopup(`<b>Hazard: ${b.location_name}</b><br>Severity: ${b.severity}<br>Status: ${b.status}`);
                        markersLayer.addLayer(circle);

                        if (isAssignedOrArrived && b.officer_lat && b.officer_lng) {
                            const officerIcon = L.divIcon({
                                className: 'custom-officer-marker',
                                html: `<div class="officer-pulse" style="position:relative; background: linear-gradient(135deg, #1e3a8a, #b91c1c); border: 2px solid #fbbf24; border-radius: 50%; width: 34px; height: 34px; display: flex; align-items: center; justify-content: center; box-shadow: 0 0 15px rgba(251,191,36,0.9);">
                                          <i class="fa-solid fa-user-shield text-amber-300 text-sm"></i>
                                       </div>`,
                                iconSize: [34, 34],
                                iconAnchor: [17, 17]
                            });
                            const officerMarker = L.marker([b.officer_lat, b.officer_lng], { icon: officerIcon })
                                .bindPopup(`<b>🚓 TN Police Dispatched Unit</b><br>Target: ${b.location_name}<br>Status: ${b.status}`);
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

            async function loadNotifications() {
                const res = await fetch('/notifications/', { headers: { 'Authorization': 'Bearer ' + authToken } });
                if (!res.ok) return;
                const data = await res.json();
                const box = document.getElementById('notification-box');
                if (!box) return;

                if (data.length > 0) {
                    const newest = data[data.length - 1];
                    if (lastSeenNotificationId !== null && newest.id > lastSeenNotificationId) {
                        showWebPopupBanner(newest.message);
                    }
                    lastSeenNotificationId = newest.id;
                }

                box.innerHTML = '';
                data.slice().reverse().forEach(n => {
                    let thumb = n.image_thumb ? `<img src="${n.image_thumb}" class="w-12 h-10 object-cover rounded inline-block ml-2 border border-slate-700">` : '';
                    box.innerHTML += `<div class="flex items-center justify-between border-b border-slate-800/50 pb-1"><div><span class="text-amber-400/80">[${new Date(n.created_at).toLocaleTimeString()}]</span> ${n.message}</div>${thumb}</div>`;
                });
            }

            async function assignUnit(id) {
                const res = await fetch('/blockades/' + id + '/assign', { method: 'POST', headers: { 'Authorization': 'Bearer ' + authToken } });
                if (!res.ok) {
                    const err = await res.json();
                    alert(err.detail || 'Action restricted.');
                }
                loadBlockades(); loadNotifications();
            }

            async function markArrived(id) {
                const res = await fetch('/blockades/' + id + '/arrived', { method: 'POST', headers: { 'Authorization': 'Bearer ' + authToken } });
                if (!res.ok) {
                    const err = await res.json();
                    alert(err.detail || 'Action restricted.');
                }
                loadBlockades(); loadNotifications();
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
                    loadBlockades();
                    loadNotifications();
                } catch (err) {
                    alert('Error: ' + err.message);
                }
            }

            async function clearResolved() {
                await fetch('/blockades/clear-resolved', { method: 'DELETE', headers: { 'Authorization': 'Bearer ' + authToken } });
                loadBlockades(); loadNotifications();
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
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or user.password != form_data.password:
        raise HTTPException(status_code=401, detail="Incorrect badge ID or password")
    return {"access_token": user.username, "token_type": "bearer"}

@app.get("/admin/officers", tags=["Admin Control"])
def get_admin_officers(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    if token.upper() != "TN-ADMIN-01":
        raise HTTPException(status_code=403, detail="Unauthorized")
    return db.query(User).all()

@app.post("/admin/officers/{badge_number}/approve", tags=["Admin Control"])
def approve_officer(badge_number: str, token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    if token.upper() != "TN-ADMIN-01":
        raise HTTPException(status_code=403, detail="Unauthorized")
    officer = db.query(User).filter(User.badge_number == badge_number).first()
    if not officer:
        raise HTTPException(status_code=404, detail="Officer not found")
    officer.status = "ACTIVE"
    db.add(Notification(message=f"[ADMIN SUPERVISOR] Officer {badge_number} ({officer.name}) approved for active duty."))
    db.commit()
    return {"message": f"Officer {badge_number} approved"}

@app.put("/admin/officers/{badge_number}", tags=["Admin Control"])
def admin_edit_officer(badge_number: str, payload: AdminEditOfficerRequest, token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    if token.upper() != "TN-ADMIN-01":
        raise HTTPException(status_code=403, detail="Only Central Command Admin can edit officer accounts.")
    officer = db.query(User).filter(User.badge_number == badge_number).first()
    if not officer:
        raise HTTPException(status_code=404, detail="Officer not found")
    officer.name = payload.name
    officer.email = payload.email
    officer.mobile = payload.mobile
    officer.status = payload.status
    if payload.password and payload.password.strip() != "":
        officer.password = payload.password.strip()
    db.add(Notification(message=f"[ADMIN PROFILE EDIT] Supervisor updated profile/status for Officer {badge_number} ({officer.status})."))
    db.commit()
    return {"message": "Officer profile updated by Admin", "status": officer.status}

@app.get("/api/profile", tags=["Officer Profile"])
def get_profile(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == token).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {
        "name": user.name,
        "email": user.email,
        "mobile": user.mobile,
        "badge_number": user.badge_number,
        "profile_photo": user.profile_photo,
        "status": user.status
    }

@app.put("/api/profile", tags=["Officer Profile"])
async def update_profile(
    name: str = Form(...),
    email: str = Form(...),
    mobile: str = Form(...),
    password: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.username == token).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    user.name = name
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
        db.add(Notification(message=f"[PROFILE EDIT] Officer {user.badge_number} updated profile details (Pending Admin Approval)"))

    db.commit()
    return {"message": "Profile updated successfully", "status": user.status}

@app.get("/api/my-clearances", tags=["Officer Profile"])
def get_my_clearances(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    if token.upper() == "TN-ADMIN-01":
        return []
    clearances = db.query(Blockade).filter(
        Blockade.status == "RESOLVED",
        Blockade.resolved_by == token
    ).order_by(Blockade.id.desc()).limit(10).all()
    return clearances

@app.head("/blockades/", tags=["Tactical Blockades"])
@app.get("/blockades/", tags=["Tactical Blockades"])
def get_blockades(db: Session = Depends(get_db)):
    return db.query(Blockade).all()

@app.post("/blockades/reset-all", tags=["Tactical Blockades"])
def reset_all_blockades(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    if token.upper() != "TN-ADMIN-01":
        raise HTTPException(status_code=403, detail="Only Central Command Admin can reset and spawn blockades.")
    db.query(Blockade).delete()
    db.add(Blockade(
        location_name="Kumbakonam Bypass Junction - Sector 2",
        latitude=10.9601,
        longitude=79.3845,
        severity="CRITICAL",
        status="ACTIVE",
        notes="Multi-vehicle collision blocking north lane",
        image_url="https://images.unsplash.com/photo-1542282088-72c9c27ed0cd?w=400&q=80"
    ))
    db.add(Notification(message="[SYSTEM RESET] Admin wiped old incidents. Fresh ACTIVE incident spawned."))
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
        image_url=img_data
    )
    db.add(new_b)
    db.add(Notification(
        message=f"[LIVE YOLO MODEL ALERT] {payload.notes} @ {payload.location_name}",
        image_thumb=img_data
    ))
    db.commit()
    db.refresh(new_b)
    return {"status": "success", "incident_id": new_b.id}

@app.post("/blockades/simulate-ai", tags=["Edge-AI Simulation"])
def simulate_ai_trigger(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    if token.upper() != "TN-ADMIN-01":
        raise HTTPException(status_code=403, detail="Only Central Command Admin can simulate AI hazards.")
    samples = [
        ("Mahamaham Tank West Gate", 10.9576, 79.3789, "CRITICAL", "YOLO-v8 Edge Cam: Crowd surge & road obstruction detected", "https://images.unsplash.com/photo-1542282088-72c9c27ed0cd?w=400&q=80"),
        ("Mayiladuthurai State Highway", 11.1018, 79.6524, "HIGH", "AI Acoustic Sensor: Emergency vehicle bottleneck", "https://images.unsplash.com/photo-1506521781263-d8422e82f27a?w=400&q=80"),
        ("Trichy-Chennai NH-45 Sector 9", 10.8254, 78.6921, "MEDIUM", "Speed Radar: Sudden traffic halt detected", "https://images.unsplash.com/photo-1519003722824-194d4455a60c?w=400&q=80")
    ]
    loc, lat, lng, sev, note, img = random.choice(samples)
    new_b = Blockade(location_name=loc, latitude=lat, longitude=lng, severity=sev, status="ACTIVE", notes=note, image_url=img)
    db.add(new_b)
    db.add(Notification(message=f"[EDGE-AI YOLO] {note} @ {loc}", image_thumb=img))
    db.commit()
    return new_b

def verify_active_field_officer(token: str, db: Session):
    if token.upper() == "TN-ADMIN-01":
        raise HTTPException(status_code=403, detail="Admin Supervisor does not perform field dispatch or clearance actions.")
    user = db.query(User).filter(User.username == token).first()
    if not user:
        raise HTTPException(status_code=404, detail="Officer account not found.")
    if user.status != "ACTIVE":
        raise HTTPException(status_code=403, detail="Your account is PENDING APPROVAL by Central Command Admin. Field actions are locked.")
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
    db.add(Notification(message=f"[DISPATCH] Unit {token} dispatched to {b.location_name}", image_thumb=b.image_url))
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
    db.add(Notification(message=f"[ON SCENE] Officer {token} arrived at {b.location_name}", image_thumb=b.image_url))
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
    verify_active_field_officer(token, db)
    b = db.query(Blockade).filter(Blockade.id == blockade_id).first()
    if not b:
        raise HTTPException(status_code=404, detail="Blockade not found")
    
    file_bytes = await file.read()
    base64_encoded = base64.b64encode(file_bytes).decode("utf-8")
    mime_type = file.content_type or "image/jpeg"
    data_uri = f"data:{mime_type};base64,{base64_encoded}"

    b.status = "RESOLVED"
    b.clearance_photo = data_uri
    b.resolved_by = token
    db.add(Notification(message=f"[RESOLVED & VERIFIED] Live camera proof submitted for {b.location_name} by officer {token}", image_thumb=data_uri))
    db.commit()
    return {"message": "Resolved with photo"}

@app.post("/blockades/{blockade_id}/resolve-photo-base64", tags=["Tactical Blockades"])
def resolve_with_photo_base64(blockade_id: int, payload: dict, token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    verify_active_field_officer(token, db)
    b = db.query(Blockade).filter(Blockade.id == blockade_id).first()
    if not b:
        raise HTTPException(status_code=404, detail="Blockade not found")
    
    img_data = payload.get("image_data") or payload.get("file")
    if img_data and not img_data.startswith("data:image"):
        img_data = f"data:image/jpeg;base64,{img_data}"

    b.status = "RESOLVED"
    b.clearance_photo = img_data
    b.resolved_by = token
    db.add(Notification(message=f"[RESOLVED & VERIFIED] Live camera proof submitted for {b.location_name} by officer {token}", image_thumb=b.clearance_photo))
    db.commit()
    return {"message": "Resolved via base64 photo"}

@app.delete("/blockades/clear-resolved", tags=["Tactical Blockades"])
def clear_resolved(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    if token.upper() != "TN-ADMIN-01":
        raise HTTPException(status_code=403, detail="Only Admin can clear resolved records.")
    deleted = db.query(Blockade).filter(Blockade.status == "RESOLVED").delete()
    db.commit()
    return {"deleted": deleted}

@app.get("/notifications/", tags=["Notifications"])
def get_notifications(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    all_notifs = db.query(Notification).all()
    # Control Room Admin receives ALL system notifications
    if token.upper() == "TN-ADMIN-01":
        return all_notifs
    # Field Officers ONLY receive active Blockade & Congestion hazard alerts
    officer_alerts = [
        n for n in all_notifs
        if ("[LIVE YOLO MODEL ALERT]" in (n.message or ""))
        or ("[EDGE-AI YOLO]" in (n.message or ""))
        or ("[SIMULATED AI]" in (n.message or ""))
        or ("[YOLO AI]" in (n.message or ""))
    ]
    return officer_alerts