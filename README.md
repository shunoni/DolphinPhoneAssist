# 🎮 DolphinPhoneAssist

**Turn your iPhone into a Wiimote controller for the Dolphin Emulator!**

A PWA (Progressive Web App) that runs on your iPhone — just open the website, add it to your Home Screen, and use your phone as a full Wiimote with gyro motion controls for Dolphin on your Raspberry Pi / Linux PC.

<p align="center">
  <img src="assets/screenshot.png" alt="Wiimote Controller Screenshot" width="300" />
</p>

## ✨ Features

- 🎯 **Full Wiimote Layout** — D-Pad, A, B (Trigger), −, Home, +, 1, 2 buttons
- 📱 **iPhone Gyroscope & Accelerometer** — Real motion controls for Wiimote pointing & tilting
- 🔗 **Zero-Config Pairing** — Phone and host auto-discover each other on the same WiFi (via MQTT signaling)
- 🐬 **Native Dolphin Support** — Cemuhook/DSU protocol server feeds motion data directly to Dolphin's Wiimote
- ⌨️ **Keyboard & Mouse Fallback** — Also emulates keyboard/mouse via Linux `uinput` for instant compatibility
- 🏠 **PWA Home Screen App** — Full-screen, no browser chrome, feels like a native app
- 🎮 **Haptic Feedback** — Vibration on button presses
- ⚡ **60Hz Motion Streaming** — Low-latency sensor data

## 🏗️ Architecture

```
┌──────────────┐    WiFi (MQTT/WS)     ┌──────────────────────┐
│   iPhone     │ ──────────────────►  │   PiOS / Linux Host  │
│  PWA (Safari)│   Buttons + Gyro     │                      │
│              │   60Hz JSON stream   │  host.py             │
│  Wiimote UI  │                      │   ├─ DSU Server      │──► Dolphin Emulator
│  + Sensors   │                      │   │  (UDP:26760)     │    (Cemuhook Client)
│              │                      │   └─ Input Emitter   │──► Virtual KB/Mouse
└──────────────┘                      └──────────────────────┘
```

## 📋 Quick Start

### 1. Set Up the Host (Raspberry Pi / Linux)

```bash
# Clone the repo
git clone https://github.com/shunoni/DolphinPhoneAssist.git
cd DolphinPhoneAssist/host

# Run the installer (installs dependencies, sets up uinput, installs Dolphin profile)
chmod +x install.sh
./install.sh

# Start the host companion
source .venv/bin/activate
python3 host.py
```

### 2. Connect Your iPhone

1. Make sure your iPhone is on the **same WiFi network** as your host device
2. Open Safari and go to: **https://shunoni.github.io/DolphinPhoneAssist/**
3. Tap the **Share** button → **Add to Home Screen**
4. Launch the app from your Home Screen
5. Tap **Enable & Connect** to grant motion sensor permissions
6. The phone will automatically find and pair with the host! 🎉

### 3. Configure Dolphin Emulator

#### Option A: DSU/Cemuhook (Recommended — Full Motion Wiimote)

1. In Dolphin, go to **Controllers** → **Alternate Input Sources**
2. Check **Enable DSU Client** → Add Server: `127.0.0.1:26760`
3. For Wii Remote 1, select **Emulated Wii Remote** → **Configure**
4. In the **Profile** dropdown, select **DolphinPhoneAssist** and click **Load**

#### Option B: Keyboard & Mouse Mode (Simpler)

1. In Dolphin, select **Emulated Wii Remote** with the default keyboard/mouse profile
2. The host app will simulate keypresses and mouse movement automatically

## ⚙️ Host Options

```bash
# Use a specific 4-digit PIN for pairing (instead of auto-detect)
python3 host.py --pin 1234

# DSU only (Cemuhook protocol, no virtual keyboard/mouse)
python3 host.py --mode dsu

# Keyboard/Mouse only (no DSU server)
python3 host.py --mode input

# Both DSU + keyboard/mouse (default)
python3 host.py --mode both

# Custom DSU port
python3 host.py --port 26761
```

## 🗂️ Project Structure

```
DolphinPhoneAssist/
├── index.html          # PWA controller page (GitHub Pages)
├── style.css           # Wiimote visual styling
├── app.js              # Phone-side logic (sensors, networking, buttons)
├── manifest.json       # PWA manifest
├── icons/              # App icons for PWA & Home Screen
├── assets/             # SVG assets (target, dolphin, home icons)
└── host/               # Linux host companion app
    ├── host.py         # Main entry point
    ├── dsu_server.py   # Cemuhook/DSU UDP server
    ├── input_emitter.py # Virtual keyboard/mouse via uinput
    ├── install.sh      # Quick installer for PiOS/Debian
    ├── requirements.txt
    └── profiles/
        └── DolphinPhoneAssist.ini  # Dolphin Wiimote mapping profile
```

## 🔧 Requirements

**Host (PiOS / Linux):**
- Python 3.7+
- `paho-mqtt` (auto-installed)
- `evdev` (auto-installed, Linux only)
- Dolphin Emulator

**Phone (iPhone):**
- iOS 13+ with Safari
- Same WiFi network as host

## 📡 How Pairing Works

1. Both devices query their public IP via `api.ipify.org`
2. A hash of the public IP creates a unique "room" on a free MQTT broker (`broker.emqx.io`)
3. Devices on the same WiFi/NAT get the same hash → auto-discover each other
4. Optionally, use a 4-digit PIN for explicit pairing

## 📄 License

MIT — do whatever you want with it! 🚀
