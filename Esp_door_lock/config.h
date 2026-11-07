// config.h  (keep this file out of version control)

#define WIFI_SSID   "your-wifi"
#define WIFI_PASS   "your-password"
#define SHARED_SECRET "change-me-to-a-long-random-string"

// ---- servo ----
#define SERVO_PIN        18
#define LOCKED_ANGLE     0
#define UNLOCKED_ANGLE   90
#define DEFAULT_UNLOCK_MS 5000
#define MIN_UNLOCK_MS     1000
#define MAX_UNLOCK_MS     30000

// ---- polling ----
#define POLL_INTERVAL_MS 2000

// 1 = poll ntfy.sh (Workato POSTs to the topic, board polls it)
// 0 = poll your own HTTPS endpoint (POLL_URL)
#define USE_NTFY 1

#define NTFY_TOPIC "your-long-unguessable-topic"

// Only used when USE_NTFY is 0.
// GET must return 200 + the command JSON, or 204 / empty body when nothing is pending.
// The endpoint must remove the command once served, so it isn't returned twice.
#define POLL_URL "https://example.com/door/pending"
