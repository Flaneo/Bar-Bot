import os
import json
import time
import serial
from flask import Flask, jsonify, render_template, request, redirect, url_for
from threading import Thread, Lock
import serial.tools.list_ports
import subprocess

app = Flask(__name__)

RECIPE_FOLDER = "Rezepte"
CONFIG_FILE = "config.json"

# SERIAL_PORT wird nicht mehr fest vorgegeben, sondern automatisch ermittelt
BAUDRATE = 115200

ser = None
esp_connected = False
serial_lock = Lock()

# **Globale Variablen Definieren**
active_recipe = None
is_running = False
current_progress = 0

def find_esp_port():
    ports = serial.tools.list_ports.comports()
    for port in ports:
        manufacturer = port.manufacturer or "Unbekannt"
        product = port.product or "Unbekannt"
        print(f"Prüfe Port: {port.device} - Hersteller: {manufacturer} - Produkt: {product}")
        if port.device.startswith("/dev/ttyUSB"):
            print(f"ESP (vermutet) an Port {port.device}")
            return port.device
    return None

def init_serial():
    global ser, esp_connected
    with serial_lock:
        if ser is not None and ser.is_open:
            return  # Bereits verbunden

        # Nach dem ESP-Port suchen
        esp_port = find_esp_port()
        if esp_port is None:
            print("Kein ESP gefunden. Bitte überprüfen Sie die Verbindung.")
            esp_connected = False
            ser = None
            return

        try:
            ser = serial.Serial(esp_port, BAUDRATE, timeout=2)
            esp_connected = True
            print(f"ESP verbunden an {esp_port}")
        except serial.SerialException as e:
            esp_connected = False
            ser = None
            print(f"ESP nicht verbunden: {e}")

def send_command_to_esp(command_dict):
    global ser, esp_connected
    with serial_lock:
        if not esp_connected or ser is None or not ser.is_open:
            return {"status": "error", "message": "ESP nicht verbunden"}

        try:
            cmd_str = json.dumps(command_dict) + "\n"
            ser.write(cmd_str.encode('utf-8'))

            start_time = time.time()
            while True:
                line = ser.readline().decode('utf-8', errors='replace').strip()
                if not line:
                    if time.time() - start_time > 5:
                        return {"status": "error", "message": "Keine Antwort vom ESP"}
                    continue

                # Debug-Zeilen ignorieren
                if line.startswith("DEBUG:"):
                    continue

                # Nur JSON-Linien verarbeiten
                if line.startswith("{"):
                    try:
                        resp = json.loads(line)
                        return resp
                    except json.JSONDecodeError as e:
                        print(f"JSON-Fehler beim Parsen der ESP-Antwort: {e}, empfangene Daten: {line}")
                        return {"status": "error", "message": "Ungültige Antwort vom ESP"}

        except Exception as e:
            print(f"Fehler bei der ESP-Kommunikation: {e}")
            esp_connected = False
            return {"status": "error", "message": "Kommunikationsfehler mit ESP"}

def load_config():
    try:
        with open(CONFIG_FILE, "r") as file:
            return json.load(file)
    except FileNotFoundError:
        print(f"Konfigurationsdatei '{CONFIG_FILE}' nicht gefunden! Erstelle eine neue.")
        return {}
    except json.JSONDecodeError as e:
        print(f"Fehler beim Lesen der Konfigurationsdatei: {e}")
        return {}

def save_config(new_config):
    try:
        # Alte Konfiguration laden
        existing_config = load_config()

        # Geschützte Schlüssel bewahren
        protected_keys = ["wlan_ssid", "wlan_password"]
        for key in protected_keys:
            if key in existing_config and key not in new_config:
                new_config[key] = existing_config[key]

        # Neue Konfiguration speichern
        with open(CONFIG_FILE, "w") as file:
            json.dump(new_config, file, indent=4)
        print("Konfiguration erfolgreich gespeichert.")
    except Exception as e:
        print(f"Fehler beim Speichern der Konfigurationsdatei: {e}")

def check_esp_connection():
    global esp_connected
    if not esp_connected or ser is None or not ser.is_open:
        return False
    with serial_lock:
        try:
            ser.write(b'{"command":"status"}\n')
            line = ser.readline().decode('utf-8').strip()
            if not line:
                return False

            if line.startswith("DEBUG:"):
                start = time.time()
                while line.startswith("DEBUG:"):
                    if time.time() - start > 2:
                        return False
                    line = ser.readline().decode('utf-8').strip()
                    if not line:
                        return False

            if line.startswith("{"):
                try:
                    resp_json = json.loads(line)
                    return resp_json.get("status") == "online"
                except json.JSONDecodeError as e:
                    print(f"JSON-Fehler beim Überprüfen des ESP-Status: {e}, Daten: {line}")
                    return False
            else:
                return False
        except Exception as e:
            print(f"Fehler bei der ESP-Kommunikation: {e}")
            esp_connected = False
            return False

def is_wifi_connected():
    try:
        result = subprocess.run(['iwgetid'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return result.returncode == 0
    except Exception as e:
        print(f"Fehler beim Überprüfen der WLAN-Verbindung: {e}")
        return False

def start_hotspot():
    try:
        subprocess.run(["sudo", "systemctl", "start", "hostapd"], check=True)
        subprocess.run(["sudo", "systemctl", "restart", "dnsmasq"], check=True)
        print("Hotspot gestartet.")
    except subprocess.CalledProcessError as e:
        print(f"Fehler beim Starten des Hotspots: {e}")

def stop_hotspot():
    try:
        subprocess.run(["sudo", "systemctl", "stop", "hostapd"], check=True)
        subprocess.run(["sudo", "systemctl", "restart", "dnsmasq"], check=True)
        print("Hotspot gestoppt.")
    except subprocess.CalledProcessError as e:
        print(f"Fehler beim Stoppen des Hotspots: {e}")

def initialize_network():
    if is_wifi_connected():
        print("WLAN ist verbunden.")
        stop_hotspot()
    else:
        print("WLAN ist nicht verbunden. Starte Hotspot.")
        start_hotspot()

# **Flask-Routen und Funktionen**

@app.route("/wifi", methods=["GET", "POST"])
def wifi_config():
    config = load_config()

    if request.method == "GET":
        return render_template("wifi.html", wlan_ssid=config.get("wlan_ssid", ""), wlan_password=config.get("wlan_password", ""))
    
    elif request.method == "POST":
        wlan_ssid = request.form.get("wlan_ssid")
        wlan_password = request.form.get("wlan_password")
        
        if not wlan_ssid or not wlan_password:
            return render_template("wifi.html", error="SSID und Passwort sind erforderlich.", wlan_ssid=wlan_ssid, wlan_password=wlan_password)
        
        config["wlan_ssid"] = wlan_ssid
        config["wlan_password"] = wlan_password
        save_config(config)
        
        # Konfigurieren von wpa_supplicant
        try:
            wpa_conf = f"""
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1
country=DE

network={{
    ssid="{wlan_ssid}"
    psk="{wlan_password}"
}}
"""
            with open("/etc/wpa_supplicant/wpa_supplicant.conf", "a") as f:
                f.write(wpa_conf)
            
            # Neuladen von wpa_supplicant
            subprocess.run(["sudo", "wpa_cli", "-i", "wlan0", "reconfigure"], check=True)
            
            # Versuch, sich mit dem neuen WLAN zu verbinden
            time.sleep(5)  # Kurze Wartezeit, um die Verbindung aufzubauen

            if is_wifi_connected():
                print("Verbindung zum WLAN erfolgreich hergestellt.")
                stop_hotspot()
                return redirect(url_for('index'))
            else:
                print("Verbindung zum WLAN fehlgeschlagen.")
                return render_template("wifi.html", error="Verbindung zum WLAN fehlgeschlagen. Bitte überprüfen Sie SSID und Passwort.", wlan_ssid=wlan_ssid, wlan_password=wlan_password)
        
        except Exception as e:
            print(f"Fehler beim Konfigurieren von WLAN: {e}")
            return render_template("wifi.html", error="Fehler beim Konfigurieren des WLAN.", wlan_ssid=wlan_ssid, wlan_password=wlan_password)

@app.route("/")
def index():
    if not is_wifi_connected():
        return redirect(url_for('wifi_config'))
    
    recipes = []
    config = load_config()

    for i in range(1, 5):
        pump_drink = config.get(f"pump{i}")
        if pump_drink:
            config[pump_drink] = config.get("pumpen", 250)

    for filename in os.listdir(RECIPE_FOLDER):
        if filename.endswith(".txt"):
            recipe_path = os.path.join(RECIPE_FOLDER, filename)
            is_valid = True
            invalid_reasons = []
            try:
                with open(recipe_path, "r") as file:
                    for line in file:
                        command = line.strip()
                        if not command:
                            continue
                        if command.startswith("move"):
                            args = command.split()
                            if len(args) != 2:
                                is_valid = False
                                invalid_reasons.append(f"Ungültiger move-Befehl: {command}")
                                continue
                            target = args[1]
                            if not target.isdigit() and target not in config:
                                is_valid = False
                                invalid_reasons.append(f"Kein Eintrag für '{target}' in der Konfiguration")
                        elif command.startswith("servo"):
                            args = command.split()
                            if len(args) >= 3:
                                mode = args[1]
                                value = args[2]
                                if mode == "ms":
                                    if not value.isdigit():
                                        is_valid = False
                                        invalid_reasons.append(f"Ungültiger servo ms-Wert: {command}")
                                elif mode == "cl":
                                    try:
                                        float(value)
                                        if "pour_time" not in config:
                                            is_valid = False
                                            invalid_reasons.append("Kein 'pour_time' in der Konfiguration für 'servo cl'")
                                    except ValueError:
                                        is_valid = False
                                        invalid_reasons.append(f"Ungültiger servo cl-Wert: {command}")
                                else:
                                    is_valid = False
                                    invalid_reasons.append(f"Unbekannter servo Modus: {mode}")
                            else:
                                is_valid = False
                                invalid_reasons.append(f"Ungültiger servo-Befehl: {command}")
            except Exception as e:
                is_valid = False
                invalid_reasons.append(f"Fehler beim Lesen des Rezepts: {e}")

            recipes.append({"name": filename, "valid": is_valid, "reasons": invalid_reasons})

    esp_connected_local = check_esp_connection()
    return render_template("index.html", recipes=recipes, esp_connected=esp_connected_local, active_recipe=active_recipe, is_running=is_running)

@app.route("/esp_status")
def esp_status():
    global esp_connected
    esp_connected = check_esp_connection()
    status_message = "ESP verbunden" if esp_connected else "ESP nicht verbunden"
    return jsonify({"connected": esp_connected, "status": status_message})

@app.route("/generate_and_run_temp_recipe", methods=["POST"])
def generate_and_run_temp_recipe():
    try:
        data = request.json
        recipe_name = data.get("name", "").strip()
        alcohol_data = data.get("alcoholData", [])

        if not recipe_name:
            return jsonify({"status": "error", "message": "Rezeptname fehlt."}), 400
        if not alcohol_data or not isinstance(alcohol_data, list):
            return jsonify({"status": "error", "message": "Ungültige Zutatenliste."}), 400

        generate_response = generate_recipe(data)
        if generate_response.status_code != 200:
            return generate_response

        recipe_path = os.path.join(RECIPE_FOLDER, f"{recipe_name}.txt")
        try:
            thread = Thread(target=execute_recipe, args=(f"{recipe_name}.txt",))
            thread.start()
            thread.join()
        finally:
            if os.path.exists(recipe_path):
                os.remove(recipe_path)

        return jsonify({"status": "success", "message": f"Temporäres Rezept '{recipe_name}' wurde ausgeführt und gelöscht."})
    except Exception as e:
        print(f"Fehler bei generate_and_run_temp_recipe: {e}")
        return jsonify({"status": "error", "message": "Fehler bei der Ausführung des temporären Rezepts."}), 500

@app.route("/config", methods=["GET", "POST"])
def manage_config():
    if request.method == "GET":
        config = load_config()
        return render_template("config.html", config=config)
    elif request.method == "POST":
        new_config = request.json.get("config")
        if not isinstance(new_config, dict):
            return jsonify({"status": "error", "message": "Ungültige Konfigurationsdaten"}), 400
        save_config(new_config)
        return jsonify({"status": "success", "message": "Konfiguration erfolgreich gespeichert"})

@app.route("/rezepte", methods=["GET", "POST", "DELETE"])
def manage_recipes():
    if request.method == "GET":
        recipes = {}
        for filename in os.listdir(RECIPE_FOLDER):
            if filename.endswith(".txt"):
                with open(os.path.join(RECIPE_FOLDER, filename), "r") as file:
                    recipes[filename] = file.read()

        config = load_config()
        drinks = [
            key for key in config.keys()
            if not key.startswith("pump") and key not in ["pour_time", "pump_time", "pumpen", "move_wait", "drip_wait", "refill_wait"]
        ]

        for i in range(1, 5):
            pump_drink = config.get(f"pump{i}")
            if pump_drink and pump_drink not in drinks:
                drinks.append(pump_drink)

        return render_template("rezepte.html", recipes=recipes, configured_alcohols=drinks)

    elif request.method == "POST":
        data = request.json
        name = data.get("name")
        content = data.get("content")
        if not name or not content:
            return jsonify({"status": "error", "message": "Name oder Inhalt fehlt"}), 400

        if not name.endswith(".txt"):
            name += ".txt"

        try:
            with open(os.path.join(RECIPE_FOLDER, name), "w") as file:
                file.write(content)
            return jsonify({"status": "success", "message": f"Rezept '{name}' gespeichert."})
        except Exception as e:
            return jsonify({"status": "error", "message": f"Fehler beim Speichern des Rezepts: {e}"}), 500

    elif request.method == "DELETE":
        data = request.json
        name = data.get("name")
        if not name or not name.endswith(".txt"):
            return jsonify({"status": "error", "message": "Ungültiger Rezeptname"}), 400

        filepath = os.path.join(RECIPE_FOLDER, name)
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
                return jsonify({"status": "success", "message": f"Rezept '{name}' gelöscht."})
            except Exception as e:
                return jsonify({"status": "error", "message": f"Fehler beim Löschen des Rezepts: {e}"}), 500
        else:
            return jsonify({"status": "error", "message": f"Rezept '{name}' nicht gefunden."}), 404

@app.route("/run_recipe", methods=["POST"])
def run_recipe():
    global is_running
    if is_running:
        return jsonify({"status": "error", "message": "Ein Rezept wird bereits ausgeführt."}), 400

    if not check_esp_connection():
        return jsonify({"status": "error", "message": "ESP ist nicht verbunden."}), 400

    recipe_file = request.json.get("recipe")
    if not recipe_file or not os.path.exists(os.path.join(RECIPE_FOLDER, recipe_file)):
        return jsonify({"status": "error", "message": "Ungültiges Rezept."}), 400

    thread = Thread(target=execute_recipe, args=(recipe_file,))
    thread.start()
    return jsonify({"status": "success", "message": f"Rezept '{recipe_file}' gestartet."})

def calculate_pump_duration(cl, pump_time):
    return int(cl * pump_time)

@app.route("/get_recipe_content", methods=["GET"])
def get_recipe_content():
    recipe_name = request.args.get("name")
    if not recipe_name:
        return "Rezeptname fehlt.", 400

    recipe_path = os.path.join(RECIPE_FOLDER, recipe_name)
    if not os.path.exists(recipe_path):
        return "Rezeptdatei nicht gefunden.", 404

    try:
        with open(recipe_path, "r") as file:
            content = file.read()
        if not content.strip():
            return "Rezeptdatei ist leer.", 400
        return content
    except Exception as e:
        return f"Fehler beim Lesen der Datei: {str(e)}", 500

@app.route("/send_command", methods=["POST"])
def send_command():
    global esp_connected
    if not esp_connected:
        return jsonify({"status": "error", "message": "ESP nicht verbunden."}), 400

    try:
        data = request.json
        if not data:
            return jsonify({"status": "error", "message": "Keine Daten gesendet."}), 400

        command_type = data.get("type")
        value = data.get("value")
        pump = data.get("pump")

        if not command_type or not isinstance(value, int):
            return jsonify({"status": "error", "message": "Ungültiger Befehlstyp oder Wert."}), 400

        if command_type == "move":
            print(f"[DEBUG] Manueller 'move': {value} mm")
            resp = send_command_to_esp({"command":"move","position":value})
            if resp.get("status") == "success":
                return jsonify({"status": "success", "message": f"Plattform zu {value} mm bewegt."})
            else:
                return jsonify({"status": "error", "message": "ESP hat nicht auf 'move' reagiert."}), 500

        elif command_type == "servo":
            print(f"[DEBUG] Manueller 'servo': {value} ms")
            resp = send_command_to_esp({"command":"servo","delay":value})
            if resp.get("status") == "success":
                return jsonify({"status": "success", "message": f"Servo mit {value} ms Verzögerung bewegt."})
            else:
                return jsonify({"status": "error", "message": "ESP hat nicht auf 'servo' reagiert."}), 500

        elif command_type == "pump":
            if not pump or not isinstance(pump, int):
                return jsonify({"status": "error", "message": "Pumpennummer fehlt oder ist ungültig."}), 400
            print(f"[DEBUG] Manueller 'pump': Pumpe {pump}, Dauer {value} ms")
            resp = send_command_to_esp({"command":"pump","pump":pump,"duration":value})
            if resp.get("status") == "success":
                # Warte die komplette Pumpenlaufzeit ab, da die Pumpe sofort erfolgreich gemeldet wird
                time.sleep(value / 1000.0)
                return jsonify({"status": "success", "message": f"Pumpe {pump} für {value} ms aktiviert."})
            else:
                return jsonify({"status": "error", "message": "ESP hat nicht auf 'pump' reagiert."}), 500

        else:
            return jsonify({"status": "error", "message": f"Unbekannter Befehlstyp: {command_type}."}), 400

    except Exception as e:
        print(f"Error in send_command: {e}")
        return jsonify({"status": "error", "message": "Serverfehler beim Verarbeiten des Befehls."}), 500

@app.route("/generate_recipe", methods=["POST"])
def generate_recipe(data=None):
    try:
        # Wenn data None ist, von request.json laden
        if data is None:
            data = request.json

        recipe_name = data.get("name", "").strip()
        alcohol_data = data.get("alcoholData", [])

        if not recipe_name:
            return jsonify({"status": "error", "message": "Rezeptname fehlt."}), 400
        if not alcohol_data or not isinstance(alcohol_data, list):
            return jsonify({"status": "error", "message": "Ungültige Zutatenliste."}), 400

        if not recipe_name.endswith(".txt"):
            recipe_name += ".txt"
        recipe_path = os.path.join(RECIPE_FOLDER, recipe_name)

        config = load_config()
        move_wait = config.get("move_wait", 500)
        refill_wait = config.get("refill_wait", 5000)
        drip_wait = config.get("drip_wait", 1000)
        pour_time = config.get("pour_time", 2000)

        commands = ["start"]

        for item in alcohol_data:
            alcohol = item.get("alcohol")
            amount_cl = float(item.get("amount", 0))
            if not alcohol:
                return jsonify({"status": "error", "message": "Getränkename fehlt."}), 400
            if amount_cl <= 0:
                return jsonify({"status": "error", "message": "Menge muss größer als 0 sein."}), 400

            move_command = f"move {alcohol}"
            is_valid, error_msg = validate_recipe_command(move_command, config)
            if not is_valid:
                return jsonify({"status": "error", "message": error_msg}), 400
            commands.append(move_command)
            commands.append("wait move_wait")

            remaining_cl = amount_cl
            while remaining_cl > 2:
                servo_command = "servo cl 2"
                is_valid, error_msg = validate_recipe_command(servo_command, config)
                if not is_valid:
                    return jsonify({"status": "error", "message": error_msg}), 400
                commands.append(servo_command)
                commands.append("wait refill_wait")
                remaining_cl -= 2

            if remaining_cl > 0:
                servo_command = f"servo cl {remaining_cl}"
                is_valid, error_msg = validate_recipe_command(servo_command, config)
                if not is_valid:
                    return jsonify({"status": "error", "message": error_msg}), 400
                commands.append(servo_command)
                commands.append("wait drip_wait")

        commands.append("move 10")
        commands.append("done")

        try:
            with open(recipe_path, "w") as file:
                file.write("\n".join(commands))
            return jsonify({"status": "success", "message": f"Rezept '{recipe_name}' wurde erfolgreich generiert."})
        except Exception as e:
            print(f"Fehler beim Generieren des Rezepts: {e}")
            return jsonify({"status": "error", "message": "Fehler beim Generieren des Rezepts."}), 500
    except Exception as e:
        print(f"Fehler beim Generieren des Rezepts: {e}")
        return jsonify({"status": "error", "message": "Fehler beim Generieren des Rezepts."}), 500

@app.route("/recipe_progress", methods=["GET"])
def recipe_progress():
    global current_progress
    return jsonify({"progress": current_progress})

def execute_recipe(recipe_file):
    global active_recipe, is_running, current_progress
    active_recipe = recipe_file
    is_running = True
    current_progress = 0

    config = load_config()
    pour_time = config.get("pour_time", 2000)
    pump_position = config.get("pumpen", 250)

    move_wait = config.get("move_wait", 500)
    drip_wait = config.get("drip_wait", 1000)
    refill_wait = config.get("refill_wait", 5000)

    pump_in_progress = False
    aggregated_pump_duration = 0
    abtropfzeit = 0
    current_target = None

    def trigger_pump_aggregation(pump_number, duration, abtropf):
        # Pumpe auslösen und auf Pumpenlauf warten
        resp = send_command_to_esp({"command":"pump","pump":pump_number,"duration":duration})
        # Pumpe meldet sofort Erfolg, wir warten die Laufzeit ab
        time.sleep(duration / 1000.0)
        # Danach Abtropfzeit abwarten
        time.sleep(abtropf / 1000.0)

    try:
        with open(os.path.join(RECIPE_FOLDER, recipe_file), "r") as file:
            commands = file.readlines()
            total_commands = len(commands)

            for idx, command in enumerate(commands):
                command = command.strip()
                if not command:
                    continue
                current_progress = int((idx + 1) / total_commands * 100)
                print(f"[DEBUG] Verarbeite Befehl: {command}, progress: {current_progress}%")

                if not esp_connected or ser is None or not ser.is_open:
                    print("[DEBUG] ESP nicht verbunden. Breche Rezept ausführung ab.")
                    break

                if command.startswith("start"):
                    print(f"Rezept '{recipe_file}' gestartet.")
                    continue

                elif command.startswith("move"):
                    target = command.split()[1]

                    if pump_in_progress:
                        pump_number = next((i for i in range(1, 5) if config.get(f"pump{i}") == current_target), None)
                        if pump_number:
                            print(f"[DEBUG] Aggregation endet. Aktiviere Pumpe {pump_number} für {aggregated_pump_duration} ms.")
                            trigger_pump_aggregation(pump_number, aggregated_pump_duration, abtropfzeit)
                        pump_in_progress = False
                        aggregated_pump_duration = 0
                        abtropfzeit = 0

                    if target.isdigit():
                        position = int(target)
                        current_target = None
                    elif target in config:
                        position = config[target]
                        current_target = target
                    else:
                        pump_number = next((i for i in range(1, 5) if config.get(f"pump{i}") == target), None)
                        if pump_number is None:
                            print(f"[DEBUG] Fehler: Ziel '{target}' ist nicht in der Konfiguration vorhanden.")
                            continue
                        position = config.get(f"pump{pump_number}_position", 250)
                        current_target = target

                    print(f"[DEBUG] Bewege Plattform zu {position} mm für '{target}'...")
                    send_command_to_esp({"command":"move","position":position})

                elif command.startswith("servo"):
                    if not current_target:
                        print("[DEBUG] Fehler: Kein gültiges Ziel für 'servo' vorhanden.")
                        continue

                    parts = command.split()
                    mode, value = parts[1], parts[2]
                    if mode == "cl":
                        cl = float(value)
                        pump_number = next((i for i in range(1, 5) if config.get(f"pump{i}") == current_target), None)
                        if pump_number:
                            pump_time_specific = config.get(f"pump{pump_number}_time", 1000)
                            aggregated_pump_duration += int(cl * pump_time_specific)
                            pump_in_progress = True
                            print(f"[DEBUG] Aggregiere Pumpe: Ziel {current_target}, Pumpe {pump_number}, {cl} cl => {aggregated_pump_duration} ms total.")
                        else:
                            delay = int((cl / 2) * pour_time)
                            print(f"[DEBUG] Bewege Servo für {cl} cl mit Verzögerung {delay} ms (kein Pumpenziel).")
                            send_command_to_esp({"command":"servo","delay":delay})

                    elif mode == "ms":
                        delay = int(value)
                        print(f"[DEBUG] Servo ms: {delay} ms Verzögerung.")
                        send_command_to_esp({"command":"servo","delay":delay})

                elif command.startswith("wait"):
                    parts = command.split()
                    if len(parts) != 2:
                        print(f"[DEBUG] Ungültiger wait-Befehl: {command}")
                        continue
                    wait_value = parts[1]

                    if wait_value.isdigit():
                        duration = int(wait_value)
                    else:
                        if wait_value == "move_wait":
                            duration = move_wait
                        elif wait_value == "drip_wait":
                            duration = drip_wait
                        elif wait_value == "refill_wait":
                            duration = refill_wait
                        else:
                            print(f"[DEBUG] Unbekannter wait-Platzhalter: {wait_value}, Standard 500ms.")
                            duration = 500

                    if pump_in_progress:
                        abtropfzeit = duration
                        print(f"[DEBUG] Setze Abtropfzeit auf {abtropfzeit} ms (Platzhalter: {wait_value}).")
                    else:
                        print(f"[DEBUG] Warte {duration} ms (Platzhalter: {wait_value}).")
                        time.sleep(duration / 1000.0)

                elif command.startswith("done"):
                    if pump_in_progress:
                        pump_number = next((i for i in range(1, 5) if config.get(f"pump{i}") == current_target), None)
                        if pump_number:
                            pump_time_specific = config.get(f"pump{pump_number}_time", 1000)
                            print(f"[DEBUG] Rezeptende: Aktiviere Pumpe {pump_number} für {aggregated_pump_duration} ms.")
                            trigger_pump_aggregation(pump_number, aggregated_pump_duration, abtropfzeit)
                        pump_in_progress = False
                        aggregated_pump_duration = 0
                        abtropfzeit = 0

                    print(f"Rezept '{recipe_file}' abgeschlossen.")
                    break
    except Exception as e:
        print(f"[DEBUG] Fehler beim Ausführen des Rezepts: {e}")

    current_progress = 100
    is_running = False
    active_recipe = None

def execute_custom_recipe(commands, recipe_name):
    global active_recipe, is_running, current_progress
    active_recipe = recipe_name
    is_running = True
    current_progress = 0

    config = load_config()
    pour_time = config.get("pour_time", 2000)
    refill_wait = config.get("refill_wait", 5000)
    drip_wait = config.get("drip_wait", 1000)

    pump_in_progress = False
    aggregated_pump_duration = 0
    abtropfzeit = 0
    current_target = None

    def trigger_pump_aggregation(pump_number, duration, abtropf):
        resp = send_command_to_esp({"command":"pump","pump":pump_number,"duration":duration})
        time.sleep(duration / 1000.0)
        time.sleep(abtropf / 1000.0)

    total_commands = len(commands)
    try:
        for idx, command in enumerate(commands):
            command = command.strip()
            if not command:
                continue
            current_progress = int((idx + 1) / total_commands * 100)
            print(f"[DEBUG] (Custom) Verarbeite Befehl: {command}, progress: {current_progress}%")

            if command.startswith("start"):
                print(f"Custom Rezept '{recipe_name}' gestartet.")
                continue

            elif command.startswith("move"):
                parts = command.split()
                if len(parts) == 2:
                    target = parts[1]

                    if pump_in_progress:
                        pump_number = next((i for i in range(1, 5) if config.get(f"pump{i}") == current_target), None)
                        if pump_number and aggregated_pump_duration > 0:
                            print(f"[DEBUG] (Custom) Aggregation endet bei move. Aktiviere Pumpe {pump_number} für {aggregated_pump_duration} ms.")
                            trigger_pump_aggregation(pump_number, aggregated_pump_duration, abtropfzeit)
                        pump_in_progress = False
                        aggregated_pump_duration = 0
                        abtropfzeit = 0

                    if target.isdigit():
                        position = int(target)
                        current_target = None
                    elif target in config:
                        position = config[target]
                        current_target = target
                    else:
                        pump_number = next((i for i in range(1, 5) if config.get(f"pump{i}") == target), None)
                        if pump_number:
                            position = config.get(f"pump{pump_number}_position", 250)
                            current_target = target
                        else:
                            print(f"[DEBUG] (Custom) Fehler: Ziel '{target}' nicht in der Konfiguration.")
                            continue

                    print(f"[DEBUG] (Custom) Bewege Plattform zu {position} mm für '{target}'...")
                    send_command_to_esp({"command":"move","position":position})
                else:
                    print(f"[DEBUG] (Custom) Ungültiger move-Befehl: {command}")

            elif command.startswith("servo"):
                parts = command.split()
                if len(parts) >= 3:
                    mode = parts[1]
                    value = parts[2]
                    if mode == "cl":
                        cl = float(value)
                        pump_number = next((i for i in range(1, 5) if config.get(f"pump{i}") == current_target), None)
                        if pump_number:
                            pump_time_specific = config.get(f"pump{pump_number}_time", 1000)
                            aggregated_pump_duration += int(cl * pump_time_specific)
                            pump_in_progress = True
                            print(f"[DEBUG] (Custom) Aggregiere Pumpe: {cl} cl => {aggregated_pump_duration} ms total für Ziel {current_target}, Pumpe {pump_number}")
                        else:
                            delay = int((cl / 2) * pour_time)
                            print(f"[DEBUG] (Custom) Servo für {cl} cl mit Verzögerung {delay} ms (kein Pumpenziel).")
                            send_command_to_esp({"command":"servo","delay":delay})
                    elif mode == "ms":
                        delay = int(value)
                        print(f"[DEBUG] (Custom) Servo ms: {delay} ms Verzögerung.")
                        send_command_to_esp({"command":"servo","delay":delay})
                    else:
                        print(f"[DEBUG] (Custom) Unbekannter servo Modus: {mode}")
                else:
                    print(f"[DEBUG] (Custom) Ungültiger servo-Befehl: {command}")

            elif command.startswith("wait"):
                parts = command.split()
                if len(parts) == 2:
                    wait_value = parts[1]
                    move_wait = config.get("move_wait", 500)
                    drip_wait = config.get("drip_wait", 1000)
                    refill_wait = config.get("refill_wait", 5000)

                    if wait_value.isdigit():
                        duration = int(wait_value)
                        print(f"[DEBUG] (Custom) Warte {duration} ms (Zahl).")
                    else:
                        if wait_value == "move_wait":
                            duration = move_wait
                            print(f"[DEBUG] (Custom) Warte {duration} ms (Platzhalter: move_wait).")
                        elif wait_value == "drip_wait":
                            duration = drip_wait
                            print(f"[DEBUG] (Custom) Warte {duration} ms (Platzhalter: drip_wait).")
                        elif wait_value == "refill_wait":
                            duration = refill_wait
                            print(f"[DEBUG] (Custom) Warte {duration} ms (Platzhalter: refill_wait).")
                        else:
                            duration = 500
                            print(f"[DEBUG] (Custom) Unbekannter wait-Platzhalter: {wait_value}, verwende 500 ms.")

                    if pump_in_progress:
                        abtropfzeit = duration
                        print(f"[DEBUG] (Custom) Setze Abtropfzeit auf {abtropfzeit} ms.")
                    else:
                        print(f"[DEBUG] (Custom) Warte {duration} ms (Platzhalter: {wait_value}).")
                        time.sleep(duration / 1000.0)
                else:
                    print(f"[DEBUG] (Custom) Ungültiger wait-Befehl: {command}")

            elif command.startswith("done"):
                if pump_in_progress:
                    pump_number = next((i for i in range(1, 5) if config.get(f"pump{i}") == current_target), None)
                    if pump_number and aggregated_pump_duration > 0:
                        pump_time_specific = config.get(f"pump{pump_number}_time", 1000)
                        print(f"[DEBUG] (Custom) Rezeptende: Aktiviere Pumpe {pump_number} für {aggregated_pump_duration} ms.")
                        trigger_pump_aggregation(pump_number, aggregated_pump_duration, abtropfzeit)
                    pump_in_progress = False
                    aggregated_pump_duration = 0
                    abtropfzeit = 0

                print(f"Custom Rezept '{recipe_name}' abgeschlossen.")
                break

    except Exception as e:
        print(f"[DEBUG] Fehler beim Ausführen des Custom Rezepts: {e}")

    current_progress = 100
    is_running = False
    active_recipe = None

@app.route("/get_recipe_ingredients")
def get_recipe_ingredients():
    recipe_name = request.args.get("recipe")
    if not recipe_name:
        return jsonify({"status": "error", "message": "Kein Rezept angegeben"}), 400
    recipe_path = os.path.join(RECIPE_FOLDER, recipe_name)
    if not os.path.exists(recipe_path):
        return jsonify({"status": "error", "message": "Rezept nicht gefunden"}), 404

    try:
        with open(recipe_path, "r") as f:
            lines = f.readlines()

        config = load_config()
        ingredientAmounts = {}
        currentIngredient = None
        for line in lines:
            line = line.strip()
            if line.startswith("move"):
                args = line.split()
                if len(args) == 2:
                    currentIngredient = args[1]
            elif line.startswith("servo cl") and currentIngredient:
                val = float(line.split()[2])
                if currentIngredient not in ingredientAmounts:
                    ingredientAmounts[currentIngredient] = 0.0
                ingredientAmounts[currentIngredient] += val

        ing_list = []
        for ing, amt in ingredientAmounts.items():
            ing_list.append({"name": ing, "amount": amt})

        return jsonify({"status": "success", "ingredients": ing_list})
    except Exception as e:
        print(e)
        return jsonify({"status": "error", "message": "Fehler beim Lesen des Rezepts"}), 500

@app.route("/run_custom_recipe", methods=["POST"])
def run_custom_recipe():
    global is_running
    if is_running:
        return jsonify({"status": "error", "message": "Ein Rezept wird bereits ausgeführt."}), 400
    if not check_esp_connection():
        return jsonify({"status": "error", "message": "ESP ist nicht verbunden."}), 400

    data = request.json
    recipe_name = data.get("recipe", "")
    ingredients = data.get("ingredients", [])
    if not recipe_name or not ingredients:
        return jsonify({"status": "error", "message": "Rezeptname oder Zutaten fehlen"}), 400

    recipe_path = os.path.join(RECIPE_FOLDER, recipe_name)
    if not os.path.exists(recipe_path):
        return jsonify({"status": "error", "message": "Rezept nicht gefunden"}), 404

    try:
        with open(recipe_path, "r") as f:
            original_lines = f.readlines()

        ing_map = {ing["name"]: ing["amount"] for ing in ingredients}
        config = load_config()

        currentIngredient = None
        new_commands = []
        for line in original_lines:
            line = line.strip()
            if line.startswith("move"):
                args = line.split()
                if len(args) == 2:
                    currentIngredient = args[1]
                new_commands.append(line)
            elif line.startswith("servo cl") and currentIngredient:
                parts = line.split()
                original_val = float(parts[2])
                new_val = ing_map.get(currentIngredient, original_val)
                parts[2] = str(new_val)
                new_commands.append(" ".join(parts))
            else:
                new_commands.append(line)

        thread = Thread(target=execute_custom_recipe, args=(new_commands, recipe_name,))
        thread.start()
        return jsonify({"status": "success", "message": "Angepasstes Rezept gestartet."})
    except Exception as e:
        print(e)
        return jsonify({"status": "error", "message": "Fehler beim Anpassen des Rezepts."}), 500

@app.route("/calibrate", methods=["GET", "POST"])
def calibrate():
    config = load_config()
    if request.method == "GET":
        item = request.args.get("item", "")
        if not item:
            return "Kein Item angegeben.", 400

        is_pump = False
        pump_number = None
        if item.startswith("pump") and item[-1].isdigit():
            is_pump = True
            pump_number = int(item[-1])

        drink_position = config.get(item) if (item in config and not item.startswith("pump")) else None
        pour_time = config.get("pour_time", 2000)

        pump_drink = None
        pump_time_val = None
        pump_pos_val = None
        if is_pump and pump_number:
            pump_drink = config.get(f"pump{pump_number}", "")
            pump_time_val = config.get(f"pump{pump_number}_time", 1000)
            pump_pos_val = config.get(f"pump{pump_number}_position", 250)

        return render_template("calibrate.html",
                               item=item,
                               is_pump=is_pump,
                               pump_number=pump_number,
                               pump_drink=pump_drink,
                               pump_time_val=pump_time_val,
                               pump_pos_val=pump_pos_val,
                               drink_position=drink_position,
                               pour_time=pour_time)

    elif request.method == "POST":
        data = request.json
        if not data:
            return jsonify({"status": "error", "message": "Keine Daten gesendet."}), 400

        item = data.get("item")
        if not item:
            return jsonify({"status": "error", "message": "Kein Item angegeben"}), 400

        config = load_config()

        if item.startswith("pump") and item[-1].isdigit():
            pump_number = int(item[-1])
            pump_drink_new = data.get("pump_drink", "").strip()
            pump_time_new = int(data.get("pump_time", 1000))
            pump_pos_new = int(data.get("pump_position", 250))

            if pump_drink_new:
                config[f"pump{pump_number}"] = pump_drink_new
            config[f"pump{pump_number}_time"] = pump_time_new
            config[f"pump{pump_number}_position"] = pump_pos_new

        else:
            if "pour_time" in data:
                config["pour_time"] = int(data["pour_time"])
            if "drink_position" in data and item in config:
                config[item] = int(data["drink_position"])

        save_config(config)
        return jsonify({"status": "success", "message": "Kalibrierte Werte erfolgreich gespeichert."})

def validate_recipe_command(command, config):
    command = command.strip()
    if not command:
        return False, "Leerer Befehl."

    parts = command.split()
    if parts[0] == "move":
        if len(parts) != 2:
            return False, f"Ungültiger move-Befehl: {command}"
        target = parts[1]
        if not target.isdigit() and target not in config:
            is_pump = any(config.get(f"pump{i}") == target for i in range(1, 5))
            if not is_pump:
                return False, f"'{target}' ist nicht in der Konfiguration vorhanden."
    elif parts[0] == "servo":
        if len(parts) < 3:
            return False, f"Ungültiger servo-Befehl: {command}"
    elif parts[0] == "wait":
        if len(parts) != 2:
            return False, f"Ungültiger wait-Befehl: {command}"
    elif parts[0] == "done":
        if len(parts) != 1:
            return False, f"Ungültiger done-Befehl: {command}"
    elif parts[0] == "start":
        if len(parts) != 1:
            return False, f"Ungültiger start-Befehl: {command}"
    else:
        return False, f"Unbekannter Befehl: {command}"

    return True, None

if __name__ == "__main__":
    init_serial()
    initialize_network()
    app.run(host="0.0.0.0", port=5001, debug=True)
