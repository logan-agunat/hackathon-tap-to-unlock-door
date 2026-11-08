import json
import time

import requests
from gpiozero import AngularServo, LED

REPLY_TOPIC =   "hackathon-door-replym4k9v8"
ACK_TOPIC = "hackathon-door-ack-p3w7z2"

NTFY_BASE = "https://ntfy.sh"

SERVO_PIN = 18            # GPIO (BCM) number, not the physical pin number
LED_PIN = 17
LOCKED_ANGLE = 0          # servo position when locked
UNLOCKED_ANGLE = 120      # servo position when unlocked

UNLOCK_SECONDS = 5        # door stays unlocked this long, then relocks
POLL_INTERVAL = 6         # seconds between polls (faster gets HTTP 429 from ntfy)
RATE_LIMIT_WAIT = 30      # seconds to wait after a 429

# =====================================================================
# SERVO SETUP
# The pulse widths match the ESP32 version (500 to 2400 microseconds).
# =====================================================================
servo = AngularServo(
    SERVO_PIN,
    min_angle=0,
    max_angle=180,
    min_pulse_width=0.0005,
    max_pulse_width=0.0024,
)

# LED SETUP
led = LED(LED_PIN)

# =====================================================================
# STATE: values the program remembers between loop passes
# =====================================================================
is_unlocked = False       # is the door currently unlocked?
unlocked_at = 0.0         # time.monotonic() when the last unlock happened
last_ntfy_id = ""         # id of the newest message seen, so each is read only once
baselined = False         # False until the first poll has skipped old messages

# LED FEEDBACK
def blink(times: int, on: float = 0.5, off: float = 0.5) -> None:
    led.blink(on_time=on, off_time=off, n=times, background=True)

# =====================================================================
# STEP 3: MOVE THE SERVO
# Every lock/unlock goes through here, so is_unlocked always matches reality.
# =====================================================================
def move_servo(locked: bool) -> None:
    global is_unlocked
    servo.angle = LOCKED_ANGLE if locked else UNLOCKED_ANGLE
    is_unlocked = not locked


# =====================================================================
# STATUS MESSAGE TO YOUR PHONE
# Lets you SEE that a trigger arrived, even when you aren't watching the Pi.
# =====================================================================
def send_ack(text: str) -> None:
    try:
        requests.post(f"{NTFY_BASE}/{ACK_TOPIC}", data=text.encode("utf-8"), timeout=5)
    except requests.RequestException as err:
        print(f"Ack failed: {err}")


# =====================================================================
# STEP 2: DECIDE WHAT A REPLY MEANS
# Called with the text of each new message found on the REPLY topic.
# =====================================================================
def do_command(cmd: str) -> None:
    global unlocked_at
 
    cmd = cmd.strip().lower()    # "Unlock" and "unlock" are treated the same
    print(f">>> TRIGGER RECEIVED: {cmd}")
 
    # Start the blink BEFORE the network ack, so you see it instantly
    # even if the ack POST is slow.
    if cmd == "unlock":
        blink(3)
    elif cmd == "deny":
        blink(1, on=1.0, off=0.2)
    elif cmd == "lock":
        blink(2)
    elif cmd == "triggered":
        blink(2, on=0.5, off=0.3)
    else:
        blink(5, on=0.05, off=0.05)
 
    send_ack(f"Board received: {cmd}")      # phone notification
 
    if cmd == "unlock":                     # you tapped [Yes]
        move_servo(False)                   # open the door
        unlocked_at = time.monotonic()      # start the relock countdown (a second unlock restarts it)
        print("UNLOCKED (approved)")
        send_ack("Door unlocked")
 
    elif cmd == "deny":                     # you tapped [No]
        print("DENIED, door stays locked")  # no servo movement at all
        send_ack("Request denied")
 
    elif cmd == "lock":                     # optional: lock immediately
        move_servo(True)
        print("LOCKED")
 
    elif cmd == "triggered":                # ntfy's default text for an empty message
        print("Trigger confirmed (no command in body)")
        send_ack("Triggered, but no unlock/deny command was sent")
 
    else:                                   # anything else is ignored for safety
        print(f"Ignored unknown reply: {cmd}")


# =====================================================================
# STEP 1a: BUILD THE POLL URL (the script assembles it itself)
#   https://ntfy.sh/<reply topic>/json?poll=1&since=<last id | all>
#   poll=1  -> answer right away with what's there, then close
#   since   -> only messages newer than the last one we saw
#              ("all" on the first poll, since we have no id yet)
# =====================================================================
def build_url() -> str:
    since = last_ntfy_id if last_ntfy_id else "all"
    return f"{NTFY_BASE}/{REPLY_TOPIC}/json?poll=1&since={since}"


# =====================================================================
# STEP 1b: ONE POLL (ask ntfy "anything new?" and act on the answer)
# Returns how many seconds to wait before the next poll.
# =====================================================================
def poll_once() -> float:
    global last_ntfy_id, baselined

    # --- send the GET and check the result ---
    try:
        response = requests.get(build_url(), timeout=10)
    except requests.RequestException as err:      # no internet, DNS failure, timeout...
        print(f"Poll failed: {err}")
        return POLL_INTERVAL

    if response.status_code != 200:               # 200 = success; anything else is a problem
        print(f"Poll failed: HTTP {response.status_code}")
        if response.status_code == 429:           # too many requests: wait longer
            return RATE_LIMIT_WAIT
        return POLL_INTERVAL

    # --- go through the reply one line at a time (one JSON object per line, oldest first) ---
    for line in response.text.splitlines():
        line = line.strip()
        if not line.startswith("{"):              # skip blank or non-JSON lines
            continue

        try:
            msg = json.loads(line)                # read the JSON
        except json.JSONDecodeError:
            continue                              # unreadable: skip

        if msg.get("event") != "message":         # skip keepalives and other events
            continue

        # --- remember this message so it's never processed twice ---
        if msg.get("id"):
            last_ntfy_id = msg["id"]

        # --- boot protection ---
        # On the very first poll, only record the newest id and don't act.
        # Otherwise an old "unlock" left in the topic would open the door at start-up.
        if not baselined:
            continue

        # --- a genuinely new reply: act on it ---
        reply = msg.get("message", "")            # the text your button sent
        do_command(reply)                         # go to STEP 2

    # --- end of the first poll: from now on, new messages count ---
    if not baselined:
        baselined = True
        print("Baseline set. Ready: listening for new replies.")

    return POLL_INTERVAL


# =====================================================================
# MAIN LOOP: safety first, then poll on a timer
# =====================================================================
def main() -> None:
    move_servo(True)                              # ALWAYS start locked
    print("Door lock started, locked.")

    next_poll = 0.0                               # poll immediately on start
    try:
        while True:
            now = time.monotonic()

            # 1. RELOCK TIMER (first, so it still works if the network is down)
            if is_unlocked and now - unlocked_at >= UNLOCK_SECONDS:
                move_servo(True)
                print("Relocked")

            # 2. POLL ON A TIMER
            if now >= next_poll:
                wait = poll_once()                # go to STEP 1b
                next_poll = time.monotonic() + wait

            time.sleep(0.2)                       # tiny pause so the loop doesn't hog the CPU

    except KeyboardInterrupt:                     # Ctrl+C: leave the door locked and exit
        print("\nStopping, locking door.")
        move_servo(True)
        led.off()
        time.sleep(0.5)
        servo.detach()


if __name__ == "__main__":
    main()