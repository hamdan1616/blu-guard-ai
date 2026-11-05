#include <SoftwareSerial.h>
#include <TinyGPS++.h>

// --- Pin Definitions (ESP8266 NodeMCU) ---
#define RED_PIN     D5  // GPIO 14 - Traffic Red
#define YELLOW_PIN  D2  // GPIO 4  - Traffic Yellow
#define GREEN_PIN   D7  // GPIO 13 - Traffic Green
#define BLUE_AI_PIN D3  // GPIO 0  - External Blue AI Strobe LED
#define GPS_RX_PIN  D6  // GPIO 12 - Connected to NEO-6M GPS TX

SoftwareSerial gpsSerial(GPS_RX_PIN, -1); // RX only on D6
TinyGPSPlus gps;

// --- Independent State Variables ---
// 1. Blue AI Strobe Modes (Pin D3):
//    '0' = Clear (OFF), 'B' = Slow Blink (0-15s), 'S' = Steady HIGH (15-45s), 'A' = Rapid Strobe (>45s)
char aiMode = '0';

// 2. Traffic Signal Control Room Modes (Pins D5, D2, D7):
//    'C' = Autonomous Cycle, 'R' = Force RED, 'Y' = Force YELLOW, 'G' = Force GREEN (108 Corridor)
char manualSignalMode = 'C';

unsigned long lastSignalChange = 0;
int trafficPhase = 0; // 0 = Green, 1 = Yellow, 2 = Red

unsigned long lastBlueToggle = 0;
bool blueState = false;
unsigned long lastGpsPrint = 0;

void applyTrafficLightPins() {
  if (manualSignalMode == 'R') {
    digitalWrite(RED_PIN, HIGH);
    digitalWrite(YELLOW_PIN, LOW);
    digitalWrite(GREEN_PIN, LOW);
  } 
  else if (manualSignalMode == 'Y') {
    digitalWrite(RED_PIN, LOW);
    digitalWrite(YELLOW_PIN, HIGH);
    digitalWrite(GREEN_PIN, LOW);
  } 
  else if (manualSignalMode == 'G') {
    digitalWrite(RED_PIN, LOW);
    digitalWrite(YELLOW_PIN, LOW);
    digitalWrite(GREEN_PIN, HIGH);
  }
}

void setup() {
  Serial.begin(115200);
  gpsSerial.begin(9600);

  pinMode(RED_PIN, OUTPUT);
  pinMode(YELLOW_PIN, OUTPUT);
  pinMode(GREEN_PIN, OUTPUT);
  pinMode(BLUE_AI_PIN, OUTPUT);

  // Start in Green phase with Blue AI LED off
  digitalWrite(RED_PIN, LOW);
  digitalWrite(YELLOW_PIN, LOW);
  digitalWrite(GREEN_PIN, HIGH);
  digitalWrite(BLUE_AI_PIN, LOW);
}

void loop() {
  unsigned long now = millis();

  // 1. Read Serial Commands from Python Control Room & Edge AI
  while (Serial.available() > 0) {
    char c = Serial.read();

    // Independent Blue AI LED states ('0', 'B', 'S', 'A')
    if (c == '0' || c == 'B' || c == 'S' || c == 'A') {
      aiMode = c;
      if (aiMode == '0') {
        digitalWrite(BLUE_AI_PIN, LOW);
        blueState = false;
      } else if (aiMode == 'S') {
        digitalWrite(BLUE_AI_PIN, HIGH);
        blueState = true;
      }
      Serial.print("ACK:BLUE=");
      Serial.println(aiMode);
    }
    // Control Room Traffic Signal Override states ('R', 'Y', 'G', 'C')
    else if (c == 'R' || c == 'Y' || c == 'G' || c == 'C') {
      manualSignalMode = c;
      lastSignalChange = now;
      if (c == 'C') {
        // Resume autonomous cycle starting from Green
        trafficPhase = 0;
        digitalWrite(GREEN_PIN, HIGH);
        digitalWrite(YELLOW_PIN, LOW);
        digitalWrite(RED_PIN, LOW);
      } else {
        // Apply Red, Yellow, or Green immediately
        applyTrafficLightPins();
      }
      Serial.print("ACK:SIGNAL=");
      Serial.println(manualSignalMode);
    }
  }

  // 2. Read NEO-6M GPS Data & Broadcast to Python Every 2 Seconds
  while (gpsSerial.available() > 0) {
    gps.encode(gpsSerial.read());
  }
  if (now - lastGpsPrint >= 2000) {
    lastGpsPrint = now;
    if (gps.location.isValid()) {
      Serial.print("GPS:");
      Serial.print(gps.location.lat(), 6);
      Serial.print(",");
      Serial.println(gps.location.lng(), 6);
    } else {
      Serial.println("GPS:SEARCHING");
    }
  }

  // 3. Traffic Light Matrix (Control Room Manual Override OR Autonomous Cycle)
  if (manualSignalMode == 'R' || manualSignalMode == 'Y' || manualSignalMode == 'G') {
    applyTrafficLightPins();
  } 
  else {
    // 'C' = Standard Autonomous Traffic Cycle Routine (8s Green -> 3s Yellow -> 8s Red)
    if (trafficPhase == 0 && (now - lastSignalChange >= 8000)) {
      trafficPhase = 1; // Switch to Yellow
      lastSignalChange = now;
      digitalWrite(GREEN_PIN, LOW);
      digitalWrite(YELLOW_PIN, HIGH);
      digitalWrite(RED_PIN, LOW);
    } else if (trafficPhase == 1 && (now - lastSignalChange >= 3000)) {
      trafficPhase = 2; // Switch to Red
      lastSignalChange = now;
      digitalWrite(GREEN_PIN, LOW);
      digitalWrite(YELLOW_PIN, LOW);
      digitalWrite(RED_PIN, HIGH);
    } else if (trafficPhase == 2 && (now - lastSignalChange >= 8000)) {
      trafficPhase = 0; // Switch to Green
      lastSignalChange = now;
      digitalWrite(GREEN_PIN, HIGH);
      digitalWrite(YELLOW_PIN, LOW);
      digitalWrite(RED_PIN, LOW);
    }
  }

  // 4. Independent 3-Stage External Blue AI Strobe Escalation (Pin D3)
  if (aiMode == '0') {
    digitalWrite(BLUE_AI_PIN, LOW);
    blueState = false;
  } else if (aiMode == 'B') {
    // Stage 1 (0-15s): Slow Warning Blink (300ms)
    if (now - lastBlueToggle >= 300) {
      lastBlueToggle = now;
      blueState = !blueState;
      digitalWrite(BLUE_AI_PIN, blueState ? HIGH : LOW);
    }
  } else if (aiMode == 'S') {
    // Stage 2 (15-45s): Steady Lock (HIGH)
    digitalWrite(BLUE_AI_PIN, HIGH);
  } else if (aiMode == 'A') {
    // Stage 3 (>45s): Rapid Emergency Police Strobe (70ms)
    if (now - lastBlueToggle >= 70) {
      lastBlueToggle = now;
      blueState = !blueState;
      digitalWrite(BLUE_AI_PIN, blueState ? HIGH : LOW);
    }
  }
}