#!/usr/bin/env python3
"""
DolphinPhoneAssist - Linux / PiOS Host Companion App
Pairs with iPhone PWA controller and emulates a Wiimote for the Dolphin Emulator.
"""

import sys
import os
import json
import time
import socket
import argparse
import threading
import urllib.request
import signal

from dsu_server import DSUServer
from input_emitter import InputEmitter

# Third-party MQTT client for zero-config pairing
try:
    import paho.mqtt.client as mqtt
    HAS_MQTT = True
except ImportError:
    HAS_MQTT = False

def get_local_ip():
    """Detect LAN IP address of this device."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def get_public_ip_hash():
    """Compute network room hash based on public IP so devices on same WiFi auto-pair."""
    try:
        req = urllib.request.Request("https://api.ipify.org?format=json", headers={"User-Agent": "DPA-Host"})
        with urllib.request.urlopen(req, timeout=3.0) as res:
            data = json.loads(res.read().decode())
            ip = data.get("ip", "local")
            # Same hashing algorithm as client app.js
            h = 0
            for char in ip:
                h = ((h << 5) - h) + ord(char)
                h &= 0xFFFFFFFF
            return f"dpa_{abs(h):x}"
    except Exception:
        return "dpa_local_default"

class DolphinHostApp:
    def __init__(self, pin=None, mode="both", port=26760):
        self.pin = pin
        self.mode = mode # 'dsu', 'input', or 'both'
        self.port = port
        self.running = False
        
        self.local_ip = get_local_ip()
        self.room_hash = get_public_ip_hash()
        self.room_id = f"pin_{self.pin}" if self.pin else self.room_hash
        self.topic_base = f"dolphinphone/room/{self.room_id}"
        
        # Subsystems
        self.dsu = DSUServer(host="0.0.0.0", port=self.port)
        self.emitter = InputEmitter(enabled=(mode in ("input", "both")))
        self.mqtt_client = None

        # Stats
        self.connected_client = None
        self.last_packet_time = 0
        self.packet_count = 0

    def start(self):
        self.running = True
        print("=" * 64)
        print("     🎮 DolphinPhoneAssist - Host Companion App (PiOS/Linux)")
        print("=" * 64)
        print(f"[*] Local Device IP:  {self.local_ip}")
        print(f"[*] Pairing Room:     {self.room_id}")
        if self.pin:
            print(f"[*] 4-Digit PIN:      {self.pin}")
        print(f"[*] Dolphin DSU UDP:  127.0.0.1:{self.port}")
        print(f"[*] Controller Mode:  {self.mode.upper()}")
        print("-" * 64)

        # 1. Start DSU Server for native Dolphin motion/buttons
        if self.mode in ("dsu", "both"):
            self.dsu.start()

        # 2. Connect to MQTT Signaling Broker
        if HAS_MQTT:
            self._connect_mqtt()
        else:
            print("[!] 'paho-mqtt' is not installed.")
            print("[!] Install it with: pip3 install paho-mqtt")
            print("[!] Waiting for direct connections...")

        # 3. Print instructions
        self._print_banner()

        # 4. Heartbeat announcer loop
        self.heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self.heartbeat_thread.start()

    def _connect_mqtt(self):
        broker = "broker.emqx.io"
        port = 1883
        client_id = f"dpahost_{os.uname().nodename}_{os.getpid()}"

        print(f"[*] Connecting to pairing broker ({broker})...")
        try:
            self.mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
        except Exception:
            self.mqtt_client = mqtt.Client(client_id=client_id)

        self.mqtt_client.on_connect = self._on_mqtt_connect
        self.mqtt_client.on_message = self._on_mqtt_message

        try:
            self.mqtt_client.connect_async(broker, port, keepalive=60)
            self.mqtt_client.loop_start()
        except Exception as e:
            print(f"[!] MQTT connection error: {e}")

    def _on_mqtt_connect(self, client, userdata, flags, rc, properties=None):
        print(f"[✓] Connected to pairing broker! Room: {self.room_id}")
        # Subscribe to client hello and input streams
        client.subscribe(f"{self.topic_base}/#")
        self._announce_presence()

    def _announce_presence(self):
        if not self.mqtt_client:
            return
        payload = {
            "event": "host_announce",
            "host_name": socket.gethostname(),
            "local_ip": self.local_ip,
            "pin": self.pin,
            "dsu_port": self.port,
            "timestamp": time.time()
        }
        self.mqtt_client.publish(f"{self.topic_base}/host", json.dumps(payload), qos=0)

    def _on_mqtt_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
            topic = msg.topic

            if "client" in topic:
                event = payload.get("event")
                if event == "client_hello":
                    self.connected_client = payload.get("device", "iPhone")
                    print(f"\n[★] PAIRED! Phone connected: {self.connected_client}")
                    # Send ack back
                    ack = {
                        "event": "host_ack",
                        "host_name": socket.gethostname(),
                        "time": time.time()
                    }
                    client.publish(f"{self.topic_base}/host", json.dumps(ack), qos=0)

            elif "input" in topic:
                self._process_input_packet(payload)

        except Exception as e:
            pass

    def _process_input_packet(self, data):
        self.last_packet_time = time.time()
        self.packet_count += 1

        pkg_type = data.get("type")

        if pkg_type == "button":
            key = data.get("key")
            st = data.get("state", 0)
            # Update DSU state
            if self.mode in ("dsu", "both"):
                self.dsu.update_input(buttons={key: st})
            # Update Virtual Keyboard & Mouse
            if self.mode in ("input", "both"):
                self.emitter.handle_button(key, st)
            print(f"\r[Input] Button: {key.upper()} = {'DOWN' if st else 'UP'}   ", end="", flush=True)

        elif pkg_type == "state":
            buttons = data.get("buttons", {})
            motion = data.get("motion", {})

            # Feed DSU Cemuhook
            if self.mode in ("dsu", "both"):
                self.dsu.update_input(buttons=buttons, motion=motion)

            # Feed Virtual Mouse
            if self.mode in ("input", "both"):
                px = motion.get("pointer_x", 0.0)
                py = motion.get("pointer_y", 0.0)
                self.emitter.handle_pointer(px, py)

        elif pkg_type == "event":
            if data.get("event") == "recenter":
                print("\n[★] Gyro Recentered by Phone!")

    def _heartbeat_loop(self):
        while self.running:
            time.sleep(3.0)
            if self.mqtt_client:
                self._announce_presence()

    def _print_banner(self):
        print("\n" + "=" * 64)
        print("                 HOW TO CONNECT YOUR IPHONE")
        print("=" * 64)
        print("1. Ensure your iPhone is connected to the SAME Wi-Fi network.")
        print("2. Open your GitHub Pages website on Safari:")
        print("   👉 https://shunoni.github.io/DolphinPhoneAssist/")
        print("3. Tap the Share button in Safari and tap 'Add to Home Screen'.")
        print("4. Launch the Wiimote app from your Home Screen.")
        print("5. Tap 'Enable & Connect' to grant Gyro permissions.")
        print("   The phone will automatically detect this host nearby!")
        print("-" * 64)
        print("                 DOLPHIN EMULATOR SETUP")
        print("-" * 64)
        print("Option A (Recommended - Full Motion Wiimote via DSU):")
        print("  1. In Dolphin, go to: Controllers -> Alternate Input Sources")
        print("  2. Check 'Enable DSU Client' -> Add Server: 127.0.0.1:26760")
        print("  3. For Wii Remote 1, select: 'Emulated Wii Remote' -> Configure")
        print("  4. Choose Device: 'DSUClient/0' (or load the DolphinPhoneAssist profile).")
        print("\nOption B (Keyboard & Mouse Mode):")
        print("  Select 'Emulated Wii Remote' with Dolphin's default profile.")
        print("=" * 64 + "\n")

    def stop(self):
        print("\n[*] Shutting down host companion...")
        self.running = False
        if self.mqtt_client:
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()
        self.dsu.stop()
        self.emitter.close()
        print("[✓] Clean exit. Goodbye!")

def main():
    parser = argparse.ArgumentParser(description="DolphinPhoneAssist Companion Host")
    parser.add_argument("--pin", type=str, default=None, help="Custom 4-digit pairing PIN (e.g. 1234)")
    parser.add_argument("--mode", type=str, choices=["dsu", "input", "both"], default="both",
                        help="Controller mode: 'dsu' (Cemuhook Wiimote), 'input' (Keyboard/Mouse), or 'both'")
    parser.add_argument("--port", type=int, default=26760, help="DSU UDP port (default: 26760)")
    args = parser.parse_args()

    app = DolphinHostApp(pin=args.pin, mode=args.mode, port=args.port)

    def handle_sigint(sig, frame):
        app.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_sigint)
    signal.signal(signal.SIGTERM, handle_sigint)

    app.start()

    while True:
        try:
            time.sleep(1)
        except KeyboardInterrupt:
            break

if __name__ == "__main__":
    main()
