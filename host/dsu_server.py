"""
DolphinPhoneAssist - Cemuhook DSU UDP Server
Implements Cemuhook / DSU Protocol v1001 for native motion streaming in Dolphin.
Default UDP Port: 26760
"""

import socket
import struct
import zlib
import time
import threading

PROTOCOL_VERSION = 1001
MAGIC_SERVER = b"DSUS"
MAGIC_CLIENT = b"DSUC"

TYPE_VERSION = 0x100000
TYPE_CONTROLLER_INFO = 0x100001
TYPE_CONTROLLER_DATA = 0x100002

SLOT_DISCONNECTED = 0
SLOT_RESERVED = 1
SLOT_CONNECTED = 2

MODEL_NONE = 0
MODEL_PARTIAL_GYRO = 1
MODEL_FULL_GYRO = 2

CONNECTION_NONE = 0
CONNECTION_USB = 1
CONNECTION_BLUETOOTH = 2

BATTERY_FULL = 0x04

class DSUServer:
    def __init__(self, host="127.0.0.1", port=26760):
        self.host = host
        self.port = port
        self.server_id = 0x1337BEEF
        self.packet_counter = 0
        self.running = False
        self.socket = None
        self.subscribed_clients = {}  # (addr, port) -> expiration timestamp
        self.mac_address = bytes([0x00, 0x1F, 0x32, 0xDE, 0xAD, 0x01])
        
        # Controller current state
        self.buttons = {
            "up": 0, "down": 0, "left": 0, "right": 0,
            "a": 0, "b": 0,
            "minus": 0, "home": 0, "plus": 0,
            "one": 0, "two": 0
        }
        self.motion = {
            "accel_x": 0.0, "accel_y": 0.0, "accel_z": 1.0,
            "gyro_pitch": 0.0, "gyro_yaw": 0.0, "gyro_roll": 0.0
        }
        self.lock = threading.Lock()

    def start(self):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind((self.host, self.port))
        self.running = True

        # Listener thread for incoming Dolphin requests
        self.listen_thread = threading.Thread(target=self._listen_loop, daemon=True)
        self.listen_thread.start()

        # Stream sender thread (60-100Hz)
        self.stream_thread = threading.Thread(target=self._stream_loop, daemon=True)
        self.stream_thread.start()
        print(f"[DSU] Server started on UDP {self.host}:{self.port}")

    def stop(self):
        self.running = False
        if self.socket:
            try:
                self.socket.close()
            except Exception:
                pass

    def update_input(self, buttons=None, motion=None):
        with self.lock:
            if buttons:
                self.buttons.update(buttons)
            if motion:
                self.motion.update(motion)

    def _pack_header(self, msg_type, payload_len):
        # 16-byte header: MAGIC(4) + version(2) + length(2) + crc32(4) + server_id(4)
        # Followed by msg_type(4)
        header_without_crc = struct.pack(
            "<4sHHII",
            MAGIC_SERVER,
            PROTOCOL_VERSION,
            payload_len,
            0, # CRC placeholder
            self.server_id
        )
        return header_without_crc, msg_type

    def _finalize_packet(self, header_without_crc, msg_type, payload):
        full_packet = header_without_crc + struct.pack("<I", msg_type) + payload
        # Calculate CRC32 of entire packet with CRC field = 0
        crc = zlib.crc32(full_packet) & 0xFFFFFFFF
        # Insert CRC back into bytes 8..11
        final_packet = full_packet[:8] + struct.pack("<I", crc) + full_packet[12:]
        return final_packet

    def _handle_version(self, client_addr):
        # Payload for version: uint16 max_version
        payload = struct.pack("<H", PROTOCOL_VERSION)
        header_no_crc, msg_type = self._pack_header(TYPE_VERSION, len(payload))
        packet = self._finalize_packet(header_no_crc, msg_type, payload)
        self.socket.sendto(packet, client_addr)

    def _handle_controller_info(self, client_addr, slot=0):
        # Payload: slot(1B), state(1B), model(1B), connection(1B), mac(6B), battery(1B)
        payload = struct.pack(
            "<BBBB6sB",
            slot,
            SLOT_CONNECTED,
            MODEL_FULL_GYRO,
            CONNECTION_BLUETOOTH,
            self.mac_address,
            BATTERY_FULL
        )
        header_no_crc, msg_type = self._pack_header(TYPE_CONTROLLER_INFO, len(payload))
        packet = self._finalize_packet(header_no_crc, msg_type, payload)
        self.socket.sendto(packet, client_addr)

    def _listen_loop(self):
        while self.running:
            try:
                data, addr = self.socket.recvfrom(1024)
                if len(data) < 20:
                    continue

                magic, version, length, crc, client_id, msg_type = struct.unpack("<4sHHIII", data[:20])
                if magic != MAGIC_CLIENT:
                    continue

                if msg_type == TYPE_VERSION:
                    self._handle_version(addr)
                elif msg_type == TYPE_CONTROLLER_INFO:
                    self._handle_controller_info(addr)
                elif msg_type == TYPE_CONTROLLER_DATA:
                    # Client subscription request
                    if len(data) >= 24:
                        sub_flags = data[20]
                        sub_slot = data[21]
                        # Register/refresh client subscription (valid for 5 seconds)
                        self.subscribed_clients[addr] = time.time() + 5.0
                        self._handle_controller_info(addr, sub_slot)
            except Exception as e:
                if self.running:
                    pass

    def _stream_loop(self):
        while self.running:
            time.sleep(0.012) # ~80Hz stream
            now = time.time()

            # Clean expired clients
            expired = [addr for addr, exp in self.subscribed_clients.items() if now > exp]
            for addr in expired:
                del self.subscribed_clients[addr]

            if not self.subscribed_clients:
                continue

            self.packet_counter = (self.packet_counter + 1) & 0xFFFFFFFF

            with self.lock:
                b = self.buttons
                m = self.motion

                # Digital Button 1:
                # bit 0: Left, bit 1: Down, bit 2: Right, bit 3: Up
                # bit 4: Options(+), bit 5: R3, bit 6: L3, bit 7: Share(-)
                btn_dpad_left = (b.get("left", 0) & 1)
                btn_dpad_down = (b.get("down", 0) & 1) << 1
                btn_dpad_right = (b.get("right", 0) & 1) << 2
                btn_dpad_up = (b.get("up", 0) & 1) << 3
                btn_plus = (b.get("plus", 0) & 1) << 4
                btn_minus = (b.get("minus", 0) & 1) << 7
                digital_btn_1 = btn_dpad_left | btn_dpad_down | btn_dpad_right | btn_dpad_up | btn_plus | btn_minus

                # Digital Button 2:
                # bit 0: Square(1), bit 1: Cross(A), bit 2: Circle(2), bit 3: Triangle(B)
                btn_1 = (b.get("one", 0) & 1)
                btn_a = (b.get("a", 0) & 1) << 1
                btn_2 = (b.get("two", 0) & 1) << 2
                btn_b = (b.get("b", 0) & 1) << 3
                digital_btn_2 = btn_1 | btn_a | btn_2 | btn_b

                # PS/Home button
                home_btn = (b.get("home", 0) & 1)

                timestamp_us = int(now * 1000000) & 0xFFFFFFFFFFFFFFFF

                # Motion data:
                # Accel X, Y, Z (g's)
                # Gyro Pitch, Yaw, Roll (deg/s)
                ax = float(m.get("accel_x", 0.0))
                ay = float(m.get("accel_y", 0.0))
                az = float(m.get("accel_z", 1.0))
                gp = float(m.get("gyro_pitch", 0.0))
                gy = float(m.get("gyro_yaw", 0.0))
                gr = float(m.get("gyro_roll", 0.0))

            # Build 80-byte controller data payload (Offsets 20..99)
            # 0..10: slot, state, model, connection, mac, battery
            # 11: active=1
            # 12..15: packet_counter
            # 16: digital_1
            # 17: digital_2
            # 18: home_btn
            # 19: touch_btn (0)
            # 20..23: sticks left_x, left_y, right_x, right_y (128 neutral)
            # 24..27: analog dpad (left, down, right, up)
            # 28..31: analog buttons (L2, R2, L1, R1)
            # 32..43: touch data (12 bytes zeros)
            # 44..51: motion timestamp uint64
            # 52..75: 6 floats (ax, ay, az, gp, gy, gr)
            payload = struct.pack(
                "<BBBB6sB B I B B B B 4B 4B 4B 12s Q 6f",
                0,                  # slot
                SLOT_CONNECTED,     # state
                MODEL_FULL_GYRO,    # model
                CONNECTION_BLUETOOTH, # connection
                self.mac_address,   # MAC
                BATTERY_FULL,       # battery
                1,                  # active / connected flag
                self.packet_counter,# packet counter
                digital_btn_1,      # digital button 1
                digital_btn_2,      # digital button 2
                home_btn,           # PS/Home
                0,                  # Touch button
                128, 128, 128, 128, # Sticks (neutral)
                0, 0, 0, 0,         # Analog Dpad
                0, 0, 0, 0,         # Analog Triggers
                b"\x00" * 12,       # Touchpad 1 & 2
                timestamp_us,       # Motion timestamp
                ax, ay, az,         # Accelerometer
                gp, gy, gr          # Gyroscope
            )

            header_no_crc, msg_type = self._pack_header(TYPE_CONTROLLER_DATA, len(payload))
            packet = self._finalize_packet(header_no_crc, msg_type, payload)

            for client_addr in list(self.subscribed_clients.keys()):
                try:
                    self.socket.sendto(packet, client_addr)
                except Exception:
                    pass
