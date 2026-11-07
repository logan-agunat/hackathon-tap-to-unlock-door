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

const char *WIFI_SSID     = "your-wifi";
const char *WIFI_PASS     = "your-password";
const char *POLL_URL      = "https://example.com/door/pending";
const char *SHARED_SECRET = "change-me";
const unsigned long POLL_INTERVAL_MS = 2000;

unsigned long lastPoll = 0;
String lastRequestId = "";

void handleCommand(const String &payload) {
  JsonDocument doc;
  if (deserializeJson(doc, payload)) {
    Serial.println("Bad JSON");
    return;
  }
  if (String((const char *)(doc["secret"] | "")) != SHARED_SECRET) {
    Serial.println("Wrong secret");
    return;
  }
  String reqId = doc["request_id"] | "";
  if (reqId.length() && reqId == lastRequestId) {
    Serial.println("Duplicate, ignored");
    return;
  }
  lastRequestId = reqId;

  String action = doc["action"] | "";
  if (action == "unlock")      Serial.println("UNLOCK");   // move servo here
  else if (action == "lock")   Serial.println("LOCK");
  else                         Serial.println("Unknown action");
}

void pollOnce() {
  WiFiClientSecure client;
  client.setInsecure();            // no cert check; pin a CA for production

  HTTPClient http;
  if (!http.begin(client, POLL_URL)) return;
  http.setTimeout(4000);

  int code = http.GET();
  if (code == 200) {
    String body = http.getString();
    body.trim();
    if (body.length()) handleCommand(body);
  } else if (code != 204) {        // 204 = nothing pending
    Serial.printf("Poll failed: HTTP %d\n", code);
  }
  http.end();
}

void setup() {
  Serial.begin(115200);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nConnected: " + WiFi.localIP().toString());
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    WiFi.reconnect();
    delay(5000);
    return;
  }
  
