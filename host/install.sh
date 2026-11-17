#!/bin/bash
# DolphinPhoneAssist - Quick Install Script for PiOS / Debian / Ubuntu Linux
set -e

echo "=============================================="
echo "   DolphinPhoneAssist Installer (PiOS/Linux)"
echo "=============================================="
echo ""

INSTALL_DIR="$HOME/DolphinPhoneAssist"

# 1. Check if running from the repo already
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$SCRIPT_DIR/host/host.py" ]; then
    INSTALL_DIR="$SCRIPT_DIR"
    echo "[i] Running from project directory: $INSTALL_DIR"
fi

# 2. Install system dependencies
echo "[*] Installing system dependencies..."
sudo apt update -qq
sudo apt install -y python3 python3-pip python3-venv git

# 3. Create virtual environment
VENV_DIR="$INSTALL_DIR/host/.venv"
if [ ! -d "$VENV_DIR" ]; then
    echo "[*] Creating Python virtual environment..."
    python3 -m venv --system-site-packages "$VENV_DIR"
fi
source "$VENV_DIR/bin/activate"

# 4. Install Python packages
echo "[*] Installing Python dependencies..."
pip install --quiet --upgrade pip
pip install --quiet paho-mqtt

# 5. Optionally install python-evdev for virtual keyboard/mouse (requires uinput)
echo "[*] Attempting to install evdev (for virtual keyboard/mouse mode)..."
pip install --quiet evdev 2>/dev/null || echo "[!] evdev install failed (non-critical on non-Linux). Input emulation will fall back."

# 6. Set up uinput permissions
if [ -c /dev/uinput ]; then
    echo "[*] Configuring /dev/uinput permissions..."
    sudo chmod 666 /dev/uinput 2>/dev/null || true
    if ! groups | grep -q input; then
        sudo usermod -aG input "$USER" 2>/dev/null || true
        echo "[i] Added '$USER' to 'input' group. You may need to log out/in for this to take effect."
    fi
fi

# 7. Install Dolphin DSU Profile
DOLPHIN_PROFILE_DIR="$HOME/.local/share/dolphin-emu/Config/Profiles/Wiimote"
if [ -d "$HOME/.local/share/dolphin-emu" ] || [ -d "/var/lib/flatpak/app/org.DolphinEmu.dolphin-emu" ]; then
    echo "[*] Installing Dolphin Wiimote Profile..."
    mkdir -p "$DOLPHIN_PROFILE_DIR"
    if [ -f "$INSTALL_DIR/host/profiles/DolphinPhoneAssist.ini" ]; then
        cp "$INSTALL_DIR/host/profiles/DolphinPhoneAssist.ini" "$DOLPHIN_PROFILE_DIR/"
        echo "[✓] Profile installed at $DOLPHIN_PROFILE_DIR/DolphinPhoneAssist.ini"
    fi
else
    echo "[i] Dolphin Emulator config folder not found. Skipping profile install."
    echo "[i] To manually install, copy host/profiles/DolphinPhoneAssist.ini to:"
    echo "    ~/.local/share/dolphin-emu/Config/Profiles/Wiimote/"
fi

echo ""
echo "=============================================="
echo "   Installation Complete!"
echo "=============================================="
echo ""
echo "To start the host companion:"
echo "  cd $INSTALL_DIR/host"
echo "  source .venv/bin/activate"
echo "  python3 host.py"
echo ""
echo "Optional flags:"
echo "  python3 host.py --pin 1234        # Use custom pairing PIN"
echo "  python3 host.py --mode dsu        # DSU only (Cemuhook Wiimote)"
echo "  python3 host.py --mode input      # Keyboard/Mouse only"
echo "  python3 host.py --mode both       # Both DSU + keyboard/mouse (default)"
echo ""
echo "Then connect your iPhone to the same Wi-Fi and visit:"
echo "  https://shunoni.github.io/DolphinPhoneAssist/"
echo ""
