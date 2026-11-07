# hackathon-tap-to-unlock-door
How it Works
1) tap card to card scanner (card reader connected to rasberry pi)
2) Rasberry sends data to python server (or workato)
    - Sends trusted notification to phone ( push notifications)
          - If yes (via push notifications), communicate to esp32 (which controls the servo lock) and unlock deadbolt, process Done
          - If no (via push notifications), do nothing/disallow entry, process Done
      
      

      
      

