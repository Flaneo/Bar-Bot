#include <WiFi.h>
#include <WebServer.h>
#include <HTTPClient.h>
#include <ArduinoOTA.h>
#include <AccelStepper.h>
#include <ESP32Servo.h>
#include <ArduinoJson.h> // ArduinoJson-Bibliothek

// Pin Definitions
#define DIR_PIN 15
#define STEP_PIN 2
#define LIMIT_SWITCH1_PIN 27
#define LIMIT_SWITCH2_PIN 26
#define SLEEP_PIN 4
#define SERVO_PIN 25 // Servo-Pin

// Servo Steps definition (all active for 1/16)
#define MS1 13
#define MS2 12
#define MS3 14

#define PUMP1_PIN 21
#define PUMP2_PIN 19
#define PUMP3_PIN 18
#define PUMP4_PIN 5

// Struct für Pumpen
struct Pump {
    uint8_t pin;
    bool active;
    unsigned long start;
    unsigned long duration;
};

// Pumpen-Array initialisieren
Pump pumps[4] = {
    {PUMP1_PIN, false, 0, 0},
    {PUMP2_PIN, false, 0, 0},
    {PUMP3_PIN, false, 0, 0},
    {PUMP4_PIN, false, 0, 0}
};

// Stepper Motor
AccelStepper stepper(AccelStepper::DRIVER, STEP_PIN, DIR_PIN);

// Servo
Servo myServo;
int servoDelay = 1000; // Standardwartezeit in Millisekunden

// WLAN-Einstellungen
const char* ssid = "ssid";
const char* password = "password";

// Statische IP-Konfiguration
IPAddress local_IP(192, 168, 2, 236);   // Feste IP-Adresse des ESP32
IPAddress gateway(192, 168, 2, 1);      // Gateway (Router-Adresse)
IPAddress subnet(255, 255, 255, 0);     // Subnetzmaske
IPAddress dns(192, 168, 2, 40);         // DNS-Server

// Raspberry Pi Server
const char* raspi_ip = "192.168.2.40"; // IP-Adresse des Raspberry Pi
const int raspi_port = 5001;           // Port des Flask-Servers

// Webserver auf dem ESP
WebServer server(80);

// Bewegungseinstellungen
const int moveMaxSpeed = 6000;        // Schritte pro Sekunde
const int moveAcceleration = 1200;    // Schritte pro Sekunde^2
const int calibMaxSpeed = 2600;      // Geschwindigkeit während der Kalibrierung
const int maxMillimeters = 1200;     // Maximale Strecke in Millimetern (Zwischen Endschaltern)

// Zustandsvariablen
long maxSteps = 0;         // Maximale Schritte zwischen Endschaltern
long currentPosition = 0;  // Aktuelle Position des Motors in Schritten

void setup() {
    Serial.begin(115200);

    Serial.println("\n===== ESP32 Initialisierung =====");

    // Pin-Konfiguration
    Serial.println("Pins konfigurieren...");
    pinMode(LIMIT_SWITCH1_PIN, INPUT);
    pinMode(LIMIT_SWITCH2_PIN, INPUT);
    pinMode(SLEEP_PIN, OUTPUT);
    digitalWrite(SLEEP_PIN, LOW);  // Treiber deaktivieren
    
    //Stepper Steps configuration
    pinMode(MS1, OUTPUT);
    pinMode(MS2, OUTPUT);
    pinMode(MS3, OUTPUT);
    digitalWrite(MS1, HIGH);
    digitalWrite(MS2, HIGH);
    digitalWrite(MS3, HIGH);

    // Pumpen-Pins initialisieren
    for (int i = 0; i < 4; i++) {
        pinMode(pumps[i].pin, OUTPUT);
        digitalWrite(pumps[i].pin, HIGH);  // Pumpen deaktivieren (HIGH ist der inaktive Zustand bei aktiven LOW-Relais)
        pumps[i].active = false;         // Pumpenstatus zurücksetzen
    }

    Serial.println("Pins konfiguriert.");

    // Stepper initialisieren
    Serial.println("Stepper-Motor initialisieren...");
    stepper.setMaxSpeed(moveMaxSpeed);
    stepper.setAcceleration(moveAcceleration);
    Serial.println("Stepper-Motor initialisiert.");

    // Servo initialisieren
    Serial.println("Servo initialisieren...");
    myServo.attach(SERVO_PIN);
    myServo.write(90);  // Neutralposition
    Serial.println("Servo auf 90 Grad gesetzt.");

    // WLAN verbinden
    connectToWiFi();

    // OTA einrichten
    setupOTA();

    // Webserver-Routen definieren
    Serial.println("Webserver-Routen definieren...");
    server.on("/move", HTTP_POST, handleMove);
    server.on("/servo", HTTP_POST, handleServo);
    server.on("/status", HTTP_GET, handleStatus);
    server.on("/pump", HTTP_POST, handlePump);
    server.begin();
    Serial.println("Webserver gestartet.");

    // Kalibrierung starten
    Serial.println("Starte Kalibrierung der Plattform...");
    calibratePlatform();

    // Bewege zur Mitte (600 mm)
    Serial.println("Bewege Plattform zur Mitte (600 mm)...");
    moveToMM(maxMillimeters / 2);
    Serial.println("Setup abgeschlossen.");
}


void loop() {
    server.handleClient();
    ArduinoOTA.handle();

    // Überprüfe den Status aller aktiven Pumpen
    unsigned long currentMillis = millis();
    for (int i = 0; i < 4; i++) {
        if (pumps[i].active && (currentMillis - pumps[i].start >= pumps[i].duration)) {
            pumps[i].active = false;
            digitalWrite(pumps[i].pin, HIGH);  // Schalte die Pumpe aus
            Serial.printf("Pumpe %d deaktiviert.\n", i + 1);
        }
    }
}


// WLAN-Verbindung herstellen
void connectToWiFi() {
  Serial.println("Statische IP konfigurieren...");
  if (!WiFi.config(local_IP, gateway, subnet, dns)) {
    Serial.println("Fehler: Statische IP konnte nicht konfiguriert werden!");
  } else {
    Serial.println("Statische IP erfolgreich konfiguriert.");
  }

  Serial.printf("Verbinde mit WLAN '%s'...\n", ssid);
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.printf("\nWLAN verbunden! IP-Adresse: %s\n", WiFi.localIP().toString().c_str());
}

// OTA einrichten
void setupOTA() {
  ArduinoOTA.setHostname("ESP32-Stepper");

  ArduinoOTA.onStart([]() {
    String type = (ArduinoOTA.getCommand() == U_FLASH) ? "Sketch" : "SPIFFS";
    Serial.printf("OTA-Update gestartet: %s\n", type.c_str());
  });
  ArduinoOTA.onEnd([]() {
    Serial.println("\nOTA-Update abgeschlossen.");
  });
  ArduinoOTA.onProgress([](unsigned int progress, unsigned int total) {
    Serial.printf("OTA-Fortschritt: %u%%\r", (progress / (total / 100)));
  });
  ArduinoOTA.onError([](ota_error_t error) {
    Serial.printf("OTA-Fehler [%u]: ", error);
    if (error == OTA_AUTH_ERROR) Serial.println("Authentifizierungsfehler");
    else if (error == OTA_BEGIN_ERROR) Serial.println("Beginn-Fehler");
    else if (error == OTA_CONNECT_ERROR) Serial.println("Verbindungsfehler");
    else if (error == OTA_RECEIVE_ERROR) Serial.println("Empfangsfehler");
    else if (error == OTA_END_ERROR) Serial.println("Ende-Fehler");
  });

  ArduinoOTA.begin();
  Serial.println("OTA eingerichtet.");
}

// Treibersteuerung
void enableDriver() {
  Serial.println("Treiber aktivieren...");
  digitalWrite(SLEEP_PIN, HIGH);
}

void disableDriver() {
  Serial.println("Treiber deaktivieren...");
  digitalWrite(SLEEP_PIN, LOW);
}

// Kalibrierung der Plattform
void calibratePlatform() {
  Serial.println("Kalibrierung: Bewege zu Endschalter 1...");
  enableDriver();

  stepper.setSpeed(-calibMaxSpeed);  // Nutzt die in calibMaxSpeed definierte Geschwindigkeit
  while (digitalRead(LIMIT_SWITCH1_PIN) == LOW) {
    stepper.runSpeed();
  }
  stepper.stop();
  stepper.setCurrentPosition(0);
  Serial.println("Kalibrierung: Endschalter 1 erreicht. Position auf 0 gesetzt.");

  Serial.println("Kalibrierung: Bewege zu Endschalter 2...");
  stepper.setSpeed(calibMaxSpeed);
  while (digitalRead(LIMIT_SWITCH2_PIN) == LOW) {
    stepper.runSpeed();
  }
  stepper.stop();
  maxSteps = stepper.currentPosition();
  Serial.printf("Kalibrierung abgeschlossen. Maximale Schritte: %ld\n", maxSteps);

  disableDriver();
}

// Bewege zur Zielposition in Millimetern
void moveToMM(int targetMM) {
  if (targetMM < 0 || targetMM > maxMillimeters) {
    Serial.printf("Ungültige Position: %d mm (Erlaubt: 0-%d mm)\n", targetMM, maxMillimeters);
    return;
  }

  long steps = map(targetMM, 0, maxMillimeters, 0, maxSteps);
  Serial.printf("Bewege Plattform zu %d mm (%ld Schritte)...\n", targetMM, steps);

  enableDriver();
  stepper.moveTo(steps);

  while (stepper.distanceToGo() != 0) {
    stepper.run();
  }

  currentPosition = stepper.currentPosition();
  Serial.printf("Position erreicht: %d mm (%ld Schritte).\n", targetMM, currentPosition);

  disableDriver();
}

// Webserver-Route: Bewegung ausführen
void handleMove() {
  if (!server.hasArg("plain")) {
    server.send(400, "application/json", "{\"status\":\"error\",\"message\":\"Keine Daten gesendet\"}");
    return;
  }

  StaticJsonDocument<200> doc;
  DeserializationError error = deserializeJson(doc, server.arg("plain"));
  if (error) {
    server.send(400, "application/json", "{\"status\":\"error\",\"message\":\"Ungültiges JSON\"}");
    return;
  }

  int targetMM = doc["position"];
  Serial.printf("Webserver: Bewegung zu %d mm angefordert.\n", targetMM);
  moveToMM(targetMM);

  server.send(200, "application/json", "{\"status\":\"success\",\"message\":\"Bewegung abgeschlossen\"}");
}

// Webserver-Route: Servo steuern
void handleServo() {
  if (!server.hasArg("plain")) {
    server.send(400, "application/json", "{\"status\":\"error\",\"message\":\"Keine Daten gesendet\"}");
    return;
  }

  StaticJsonDocument<200> doc;
  DeserializationError error = deserializeJson(doc, server.arg("plain"));
  if (error) {
    server.send(400, "application/json", "{\"status\":\"error\",\"message\":\"Ungültiges JSON\"}");
    return;
  }

  int delayTime = doc["delay"];
  if (delayTime < 0) {
    server.send(400, "application/json", "{\"status\":\"error\",\"message\":\"Ungültige Verzögerung\"}");
    return;
  }

  servoDelay = delayTime;
  Serial.printf("Webserver: Servo bewegen (140 Grad), warte %d ms, zurück zu 90 Grad.\n", servoDelay);

  myServo.write(140);
  delay(servoDelay);
  myServo.write(90);

  server.send(200, "application/json", "{\"status\":\"success\",\"message\":\"Servo-Bewegung abgeschlossen\"}");
}

void activatePump(int pumpNumber, int duration) {
    if (pumpNumber < 1 || pumpNumber > 4) {
        Serial.printf("Ungültige Pumpennummer: %d\n", pumpNumber);
        return;
    }

    Pump &pump = pumps[pumpNumber - 1];
    if (pump.active) {
        Serial.printf("Pumpe %d ist bereits aktiv. Ignoriere Aktivierung.\n", pumpNumber);
        return;
    }

    pump.active = true;
    pump.start = millis();
    pump.duration = duration;

    digitalWrite(pump.pin, LOW);  // Pumpe einschalten
    Serial.printf("Pumpe %d aktiviert für %d ms.\n", pumpNumber, duration);

    // Automatisches Ausschalten nach Ablauf der Zeit
    delay(duration);
    digitalWrite(pump.pin, HIGH);  // Pumpe ausschalten
    pump.active = false;
    Serial.printf("Pumpe %d wurde automatisch deaktiviert.\n", pumpNumber);
}

void handlePump() {
    if (!server.hasArg("plain")) {
        server.send(400, "application/json", "{\"status\":\"error\",\"message\":\"Keine Daten gesendet\"}");
        return;
    }

    StaticJsonDocument<200> doc;
    DeserializationError error = deserializeJson(doc, server.arg("plain"));
    if (error) {
        server.send(400, "application/json", "{\"status\":\"error\",\"message\":\"Ungültiges JSON\"}");
        return;
    }

    int pumpNumber = doc["pump"];
    int duration = doc["duration"];

    if (pumpNumber < 1 || pumpNumber > 4 || duration <= 0) {
        Serial.printf("Fehler: Ungültige Eingaben - Pumpennummer: %d, Dauer: %d\n", pumpNumber, duration);
        server.send(400, "application/json", "{\"status\":\"error\",\"message\":\"Ungültige Pumpennummer oder Dauer\"}");
        return;
    }

    activatePump(pumpNumber, duration);

    server.send(200, "application/json", "{\"status\":\"success\",\"message\":\"Pumpe aktiviert\"}");
}


void handleStatus() {
    StaticJsonDocument<256> doc;
    doc["status"] = "online";

    JsonArray pumpStatuses = doc.createNestedArray("pumps");
    for (int i = 0; i < 4; i++) {
        JsonObject pump = pumpStatuses.createNestedObject();
        pump["pumpNumber"] = i + 1;
        pump["active"] = pumps[i].active;
        pump["remainingTime"] = pumps[i].active ? (pumps[i].duration - (millis() - pumps[i].start)) : 0;
    }

    String response;
    serializeJson(doc, response);
    server.send(200, "application/json", response);
}
