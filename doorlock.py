import json
import time

import requests
from gpiozero import AngularServo, LED

REPLY_TOPIC =   "hackathon-door-replym4k9v8"        
ACK_TOPIC = "hackathon-door-ack-p3w7z2"

NTFY_BASE = "https://ntfy.sh"

# HARDWARE CONFIGURATION
SERVO_PIN = 18            # servo control signal pin
LED_PIN = 17              # GPIO (BCM) number (physical pin 11)

# SERVO POSITIONS
LOCKED_ANGLE = 0          # servo position when locked
UNLOCKED_ANGLE = 120      # servo position when unlocked

# TIMING SETTINGS
UNLOCK_SECONDS = 5        # keep door unlocked for 5 seconds, than automatically relock

# POLLING AND RATE-LIMIT SETTINGS
POLL_INTERVAL = 6         # time(seconds) between ntfy polling requests
RATE_LIMIT_WAIT = 30      # the wait time after receiving a HTTP 429 response before retrying

# =====================================================================
# SERVO SETUP

servo = AngularServo(
    SERVO_PIN,
    
    min_angle=0,
    max_angle=180,
    min_pulse_width=0.0005,
    max_pulse_width=0.0024,
)


led = LED(LED_PIN) 

# =====================================================================
# Runtime state:
# these variables keep track of what the door lock setup 
# while the program is runnin


door_unlocked = False   # Remains true while the door is unlocked
unlocked_time = 0.0     # Time stamp of when the door was last unlocked.
last_message_id = ""    # Most recent ntfy message ID that has been processed.
                        # Prevents the same command from being handled twice.

startup_done = False    # On startup, should ignore exisiting/old notifications and only
                        #  react to new ones that arrive afterward

# =====================================================================
# LED FEEDBACK


def blink(times: int, on: float = 0.06, off: float = 0.06) -> None:
    #  Flash the statu LED(on arduino) without interuptting main program.
    # this will run in the background, so we can still allow polling and relocking
    # timers to run uninterrupted.
    led.blink(on_time=on, off_time=off, n=times, background=True)


# =====================================================================
# STEP 3: SERVO MOVEMENT
# Moves the lock to either the locked or unlocked position snd updtes the 
# door's current state

def move_servo(locked: bool) -> None:
    global door_unlocked
    # Rotate the servo to the correct position
    servo.angle = LOCKED_ANGLE if locked else UNLOCKED_ANGLE
    # Keep track of the door's current status
    door_unlocked = not locked


# =====================================================================
# PHONE NOTIFICATION
# Sends a message to a phone through ntfy so that we know when the door
# lock has been triggered. even if we are away from door-lock system

def send_ack(text: str) -> None:
    try:
        requests.post(f"{NTFY_BASE}/{ACK_TOPIC}", data=text.encode("utf-8"), timeout=5)
    except requests.RequestException as err:
        print(f"Ack failed: {err}")


# =====================================================================
# STEP 2: DECIDE WHAT A REPLY MEANS
# Process the message received fro mthe reply topic and performs the
# requested door action
#
# LED feedback on arduino:
#   unlock    -> 6 fast blinks

def do_command(command: str) -> None:
    global unlocked_time

    command = command.strip().lower()    # "Unlock" and "unlock" are treated the same
    print(f">>> TRIGGER RECEIVED: {command}")

    # Start the blink BEFORE the network ack, so you see it instantly
    # even if the ack POST is slow.
    if command == "unlock":
        # Flash the LED 6 times to indicate that the command was recieved
        blink(6)
        # Send a confirmation that the board reeived the request
        send_ack("Board received: unlock")
        # Move the ser vo to the unlocked position
        move_servo(False)
        # Start the automatic relock timer
        unlocked_time = time.monotonic()

        print("Door unlocked")
        send_ack("Door unlocked")


# =====================================================================
# STEP 1a: BUILD THE POLLING URL
# Creates the ntfy request used the check for any new replies
#
# On startup, request only the newest messsage("all")
# so that old notifications are ignored. And after that, we ask
# for messages that arrived after the last one we processed.

def build_url() -> str:
    # if we've already seen a message, poll for anything newer.
    # Otherwise start from the latest available message.
    since = last_message_id if last_message_id else "all"
    return f"{NTFY_BASE}/{REPLY_TOPIC}/json?poll=1&since={since}"


# =====================================================================
# STEP 1b: ONE POLL / CHECK FOR ANY NEW REPLIES
# Polls ntdy for new messages and processes any unlock commands
# that arrive.

def poll_once() -> float:
    global last_message_id, startup_done

    # Send a request to ntfy and wait for a response
    try:
        response = requests.get(build_url(), timeout=10)
    except requests.RequestException as err:      
        print(f"Poll failed: {err}")
        return POLL_INTERVAL
    
    # Make sure the request is successful
    if response.status_code != 200:               # 200 = successful request, any other number no good
        print(f"Poll failed: HTTP {response.status_code}")

        # waits longer if the ntfy is rate-limiting any requests
        if response.status_code == 429:           # 429 means too many requests sent, than server can allow
            return RATE_LIMIT_WAIT
        return POLL_INTERVAL

    # read each message thats returned by ntfy
    for line in response.text.splitlines():
        line = line.strip()

        if not line.startswith("{"):              # skip empty or invalid lines
            continue

        try:
            message = json.loads(line)            
        except json.JSONDecodeError:
            continue                             

        # Proces only message events
        if message.get("event") != "message":       
            continue

        # Save the newest message ID we've seen
        if message.get("id"):
            last_message_id = message["id"]

        # Ignore old messages during startup
        if not startup_done:
            continue

        # Process the unlock command
        reply_cmd = message.get("message", "")            
        do_command(reply_cmd)                         

    # Startup done. only new messages are processed from now on
    if not startup_done:
        startup_done = True
        print("Baseline set. Ready: listening for new replies.")
        blink(3)                                  # 3 fast blinks = ready and listening

    return POLL_INTERVAL


# =====================================================================
# MAIN FUNCTION
# Runs the door controller, handles automatic relocking, checks
# for new unlock requests

def main() -> None:
    move_servo(True)                              # ALWAYS start locked
    print("Door lock started, locked.")

    next_poll_time = 0.0                               # poll immediately on start
  
    while True:
        now = time.monotonic()

        # 1. RELOCK TIMER (automatically relock door after the unlock period expires
        if door_unlocked and now - unlocked_time >= UNLOCK_SECONDS:
            move_servo(True)
            print("Relocked")

        # 2. POLL ON A TIMER
        # Check for any new unlock requests
        if now >= next_poll_time:
            poll_delay = poll_once()               
            next_poll_time = time.monotonic() + poll_delay

        time.sleep(0.2)                 # put a tiny pause here so that we can check the relock timer and
                                        # whether its time to poll ntfy, using it for the polling



if __name__ == "__main__":
    main()
