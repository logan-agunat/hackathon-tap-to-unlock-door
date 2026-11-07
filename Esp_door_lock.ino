// ESP32 door lock.
// Workato -> (HTTP POST) -> [ntfy relay OR tunnel to this board] -> ESP32 -> servo
//
// Every message goes through handleCommand(). Expected JSON:
//   {"action":"unlock","secret":"...","request_id":"r_1","decided_by":"Alex","duration_ms":5000}
//   {"action":"lock","secret":"..."}
//
// Libraries (Library Manager): ESP32Servo, ArduinoJson (version 7.x)
// Board: ESP32 Dev Module

#include <WiFi.h>
#include <ESP32Servo.h>
#include <ArduinoJson.h>
#include "config.h"

#if USE_NTFY
  #include <WiFiClientSecure.h>
  WiFiClientSecure client;
  String lastNtfyId = "";
  unsigned long lastAttempt = 0;
  unsigned long lastDataAt = 0;
#else
  #include <WebServer.h>
  WebServer server(80);
#endif

// ---------- state ----------
Servo lockServo;
bool isUnlocked = false;
unsigned long unlockedAt = 0;
unsigned long unlockForMs = DEFAULT_UNLOCK_MS;
String lastRequestId = "";
unsigned long lastWifiTry = 0;

enum Result { RES_OK, RES_BAD_FORMAT, RES_UNAUTHORIZED, RES_DUPLICATE, RES_UNKNOWN_ACTION };

const char *resultText(Result r) {
  switch (r) {
    case RES_OK:             return "ok";
    case RES_BAD_FORMAT:     return "bad format";
    case RES_UNAUTHORIZED:   return "unauthorized";
    case RES_DUPLICATE:      return "duplicate";
    case RES_UNKNOWN_ACTION: return "unknown action";
  }
  return "error";
}

int httpCodeFor(Result r) {
  switch (r) {
    case RES_OK:           return 200;
    case RES_DUPLICATE:    return 200;
    case RES_UNAUTHORIZED: return 401;
    default:               return 400;
  }
}

// ---------- servo ----------
void moveServo(bool locked) {
  lockServo.write(locked ? LOCKED_ANGLE : UNLOCKED_ANGLE);
  isUnlocked = !locked;
}

// ---------- the one place all commands go through ----------
Result handleCommand(const String &payload) {
  JsonDocument doc;
  DeserializationError err = deserializeJson(doc, payload);
  if (err) {
    Serial.print("Rejected: bad JSON (");
    Serial.print(err.c_str());
    Serial.println(")");
    return RES_BAD_FORMAT;
  }

  const char *secret = doc["secret"] | "";
  if (String(secret) != SHARED_SECRET) {
    Serial.println("Rejected: wrong secret");
    return RES_UNAUTHORIZED;
  }

  const char *reqId = doc["request_id"] | "";
  if (strlen(reqId) > 0) {
    if (String(reqId) == lastRequestId) {
      Serial.println("Ignored: duplicate request_id");
      return RES_DUPLICATE;
    }
    lastRequestId = reqId;
  }

  String action = doc["action"] | "";
  const char *by = doc["decided_by"] | "unknown";

  if (action == "unlock") {
    unsigned long duration = doc["duration_ms"] | (unsigned long)DEFAULT_UNLOCK_MS;
    duration = constrain(duration, (unsigned long)MIN_UNLOCK_MS, (unsigned long)MAX_UNLOCK_MS);
    moveServo(false);
    unlockedAt = millis();   // a second unlock just restarts the timer
    unlockForMs = duration;
    Serial.print("UNLOCKED for ");
    Serial.print(duration);
    Serial.print(" ms, approved by ");
    Serial.println(by);
    return RES_OK;
  }

  if (action == "lock") {
    moveServo(true);
    Serial.println("LOCKED by command");
    return RES_OK;
  }

  Serial.println("Rejected: unknown action");
  return RES_UNKNOWN_ACTION;
}

// ---------- transport A: ntfy relay ----------
#if USE_NTFY
bool connectStream() {
  client.stop();
  client.setInsecure();  // fine for a hackathon; skips certificate checking
  Serial.println("Connecting to ntfy.sh...");
  if (!client.connect("ntfy.sh", 443)) {
    Serial.println("Connect failed, will retry");
    return false;
  }
  client.print(String("GET /") + NTFY_TOPIC + "/json HTTP/1.0\r\nHost: ntfy.sh\r\n\r\n");
  lastDataAt = millis();
  Serial.println("Subscribed. Waiting for messages.");
  return true;
}

void handleNtfyLine(String line) {
  lastDataAt = millis();  // any data, including keepalives, means the stream is alive
  line.trim();
  if (line.length() == 0 || line[0] != '{') return;  // skip HTTP headers

  JsonDocument doc;
  if (deserializeJson(doc, line)) return;

  const char *event = doc["event"] | "";
  if (String(event) != "message") return;

  String id = doc["id"] | "";
  if (id == lastNtfyId) return;  // duplicate after a reconnect
  lastNtfyId = id;

  String message = doc["message"] | "";  // the JSON Workato sent
  handleCommand(message);
}

void startTransport() {
  connectStream();
}

void serviceTransport() {
  bool stale = millis() - lastDataAt > 90000;  // ntfy sends keepalives
  if ((!client.connected() || stale) && millis() - lastAttempt > 3000) {
    lastAttempt = millis();
    connectStream();
  }
  while (client.available()) {
    handleNtfyLine(client.readStringUntil('\n'));
  }
}

// ---------- transport B: web server ----------
#else
void onCommandRoute() {
  if (server.method() != HTTP_POST) {
    server.send(405, "application/json", "{\"result\":\"use POST\"}");
    return;
  }
  Result r = handleCommand(server.arg("plain"));  // raw body (send as application/json)
  server.send(httpCodeFor(r), "application/json",
              String("{\"result\":\"") + resultText(r) + "\"}");
}

void onHealthRoute() {
  server.send(200, "application/json",
              isUnlocked ? "{\"locked\":false}" : "{\"locked\":true}");
}

void startTransport() {
  server.on("/command", onCommandRoute);
  server.on("/health", HTTP_GET, onHealthRoute);
  server.begin();
  Serial.println("Web server started: POST /command, GET /health");
}

void serviceTransport() {
  server.handleClient();
}
#endif

// ---------- test without any network: paste JSON into the Serial Monitor ----------
void checkSerialInput() {
  if (Serial.available()) {
    String line = Serial.readStringUntil('\n');
    line.trim();
    if (line.length() > 0) {
      Result r = handleCommand(line);
      Serial.print("Result: ");
      Serial.println(resultText(r));
    }
  }
}

// ---------- setup / loop ----------
void setup() {
  Serial.begin(115200);

  lockServo.setPeriodHertz(50);
  lockServo.attach(SERVO_PIN, 500, 2400);
  moveServo(true);  // always boot locked

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.print("Connecting to WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.print("\nConnected. IP address: ");
  Serial.println(WiFi.localIP());

  startTransport();
}

void loop() {
  // 1. relock timer first, so it works even if the network is flaky
  if (isUnlocked && millis() - unlockedAt >= unlockForMs) {
    moveServo(true);
    Serial.println("Relocked");
  }

  // 2. keep WiFi alive without blocking
  if (WiFi.status() != WL_CONNECTED) {
    if (millis() - lastWifiTry > 5000) {
      lastWifiTry = millis();
      WiFi.reconnect();
    }
    checkSerialInput();
    return;
  }

  // 3. listen for commands
  checkSerialInput();
  serviceTransport();
}
