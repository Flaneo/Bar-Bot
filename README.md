# Bar-Bot
Automatic Cocktail Maker (Work in Progress)

Project startet on 17th November 2024

This is my take on the Automatic Bartender Robot (original: https://github.com/sidlauskaslukas/barbot/tree/master?tab=readme-ov-file)

# Details
- You can freely decide which drink you want to put on which position. Then you can configure the drink and location in the webserver. (/config)
- You can easily create new recipes and manage your existing ones. (/rezepte)
- You can decide what drink is made with a click of a button. The available recipes are shown in green, while the other ones are red. You can see details on why a recipe is not available.
- Chancing location of drinks is as easy as it gets. Just set the name of your drink and the position.
- Adding new recipes is also very easy. Just select the drink and the quantity, and a file with the instructions for the esp is automatically created.
- When Bottles are reordered, it still works perfectly, as long as you define the new locations on the /config page

# Technical Details
The ESP has minimal code on it. It only takes 2 commands.
- move to position x and
- activate servo, hold for x ms, then go back
The Raspberry Pi takes the heavy lifting, by sending the right commands to the ESP

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

# Total Hardware cost (not including 3D printing material): ~315€

# Here are a few images
![As of 22th November 2024](https://github.com/leofleischmann/Bar-Bot/blob/aef47b5e8c036a115e24fcea56c180e6691d0192/Progress_report.jpeg?raw=true)
![As of 22th November 2024](https://github.com/leofleischmann/Bar-Bot/blob/aef47b5e8c036a115e24fcea56c180e6691d0192/AutoBarTender_constructed_v1_2024-Nov-18_06-47-27PM-000.png?raw=true)

# About the Website:
![index.html](https://github.com/leofleischmann/Bar-Bot/blob/3d107a8f69a7a1337c4d5f3ebdf53a4c28e42e59/Images/index.png?raw=true)
![config.html](https://github.com/leofleischmann/Bar-Bot/blob/ae1de67198a41afd0f7748fb647b31d3b8999d1d/Images/config_V2.png?raw=true)
![rezepte.html](https://github.com/leofleischmann/Bar-Bot/blob/3d107a8f69a7a1337c4d5f3ebdf53a4c28e42e59/Images/rezepte.png?raw=true)
