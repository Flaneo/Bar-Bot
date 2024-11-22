# Bar-Bot
Automatic Cocktail Maker (Work in Progress)

Project startet on 17th November 2024

This is my take on the Automatic Bartender Robot (original: https://github.com/sidlauskaslukas/barbot/tree/master?tab=readme-ov-file)

# Things I want to change:
- Not use a 100€ Servo Motor,
- ESP32 only receives commands from a Raspberry Pi and executes them,
- All drinks are stored on the Raspberry Pi as command lists (pour <ml>, move to <mm>, calibrate,...),
- Drinks can be selected, added, removed, configured via a webserver. (Thus no App needed on a phone and user interface is not suffering from running a Webserver via the ESP)


# Already done:
- All parts are assembled (except liquor holding and pouring construction)
- Project almost compleately digitalized for easyer testing, troubleshooting ect. (3D files, ESP32 emulators...)
- Raspberry Pi Server programmed and functional
- ESP32 Code functional and taking commands from the Raspberry Pi
- Basic Web-Interface for testing purposes.
- Software for the Raspberry Pi and ESP32
- Hardware testing
- Parameter tuning
- User Interface
- Fully functional Web interface to configure, edit, add, remove recipes and drinks with ther corresponding position
- (Done at 22th November 2024)

# Currently working on:
- Waiting to buy liquor dispensers

# Total Hardware cost (not including 3D printing material): ~165€

# Here are a few images
![As of 22th November 2024](https://github.com/leofleischmann/Bar-Bot/blob/aef47b5e8c036a115e24fcea56c180e6691d0192/Progress_report.jpeg?raw=true)
![As of 22th November 2024](https://github.com/leofleischmann/Bar-Bot/blob/aef47b5e8c036a115e24fcea56c180e6691d0192/AutoBarTender_constructed_v1_2024-Nov-18_06-47-27PM-000.png?raw=true)

# About the Website:
![index.html](https://github.com/leofleischmann/Bar-Bot/blob/3d107a8f69a7a1337c4d5f3ebdf53a4c28e42e59/Images/index.png?raw=true)
![config.html](https://github.com/leofleischmann/Bar-Bot/blob/3d107a8f69a7a1337c4d5f3ebdf53a4c28e42e59/Images/config.png?raw=true)
![rezepte.html](https://github.com/leofleischmann/Bar-Bot/blob/3d107a8f69a7a1337c4d5f3ebdf53a4c28e42e59/Images/rezepte.png?raw=true)
