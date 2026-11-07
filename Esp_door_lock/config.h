// Copy this file to config.h and fill in your values. Never commit config.h
#pragma once

#define WIFI_SSID      "your-wifi-or-hotspot"
#define WIFI_PASS      "your-password"

// Letters and digits only (no quotes or symbols). Workato sends "unlock:<this>".
#define SHARED_SECRET  "pick-a-long-random-string"

// The ntfy topic is effectively a password. Make it long and random,
// e.g. "tapunlock-7f3k9x2qm8w4". Anyone who knows it can send messages to it.
#define NTFY_TOPIC     "tapunlock-change-me-to-something-random"

#define SERVO_PIN      13
#define LOCKED_ANGLE   0      // tune on the real deadbolt
#define UNLOCKED_ANGLE 120
#define UNLOCK_MS      5000   // how long the door stays unlocked

