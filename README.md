# hackathon-tap-to-unlock-door
# Built with raspberry pi 4's and Arduino uno

**How it Works**
1) A card is tapped on the card scanner, which is connected to Rasberry Pi 1
2) Raspberry pi 1 sends a webhook to Workato
3) If the card belongs to a trusted user, the door unlocks and you get a notification that it opened.
4) If the card is not a trusted user, you get notification asking you to approve the request
    - YES: The door unlocks and the card is added as a trusted user
    - NO: Nothing happens, the door stays locked.
5) Workato posts an unlock message to a private ntfy topic
6) Raspberry pi 2 picks up that messsage, turns to servo its open position, and will relock after 5 seconds
    - Raspberry pi 2 runs all the control code, and generates the servo signal itself
    - The servos are plugged into an arduino uno connected to Raspberry pi 2. Arduino uno runs no code and only acts
    - as a power and wiring board for the servos
      
Note: A card will only becomes trusted after the person on the phone approves it. Scanning a card never trusts it by itself

**HARDWARE**
Raspberry pi 1: On the outside of the door. Reads the card scanner and sends 
                a webhook to Workato
Zag Card Scanner: Reads the card tap
Raspberry pi 2: Inside of the door. Runs doorlock.py, which polls ntfy for replies and 
                controls the servos.
Arduino Uno: Connected to Raspberry pi 2. The two servos are plugged into the arduino uno,
             which provides power and wiring. It runs no code.
Servo Motors: Plugged into the arduino uno. Controls the door lock.
Status LED: Blinks when a reply is received.
Phone Hotspot: Internet for both Raspberry pi's.

**HOW DOORLOCK.PY WORKS**
Note: the Raspberry pi can't be contacted directly, so it will poll every 6 seconds ("asks" ntfy if theres any new messages)
1) Startup: The servo is in locked position
   
2) Startup baseline:
   - On the first poll, the python script reads the messages that is already in the topic(name channel on nfty.sh) and will ignore them,
     and will then print a "Baseline set. Ready: listening for new replies."
     
3) Polling: Each poll ask for messages newer than the last one seen, so that no message is handled twice.
    If ntfy returns HTTP 429 (too many requests), the script waits 30 seconds before trying again. Network errors are printed and the poll is retried.
   
4) Command: when a new message arrives, its text is trimmed and lowercased and printed to the console. If it is unlock, the script:
    blinks the LED 6 times,
    sends "Board received: unlock" to the phone,
    moves the servos to the unlocked position and starts the relock timer,
    sends "Door unlocked" to the phone.
    Any other text is ignored.
    Auto-relock: 5 seconds after an unlock, the main loop moves the servos back to the locked position and prints Relocked. A second unlock restarts the countdown. This check will run before every poll, so the door still relocks if the network becomes unstable.


**Safety design**
- The door always starts locked.
- Old messages are ignored at startup, so a stale unlock can't open the door after a reboot.
  Anything other than unlock is ignored.
- The relock timer keeps running even if the network goes down.
- New cards need explicit approval before they are trusted.

**Limitations**
- Delay: because the Pi polls every 6 seconds, an approval can take up to 6 seconds to reach the servos.
- Internet required: both Pis need internet access (a phone hotspot in our demo).
- No stop handler: if the script is stopped while the door is unlocked, the servo stays in the unlocked position until the script is started again.






      

      
      

