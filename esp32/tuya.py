# Minimal Tuya local protocol implementation for MicroPython
import socket
import struct
import json
from ucryptolib import aes


def _pad(data):
    """PKCS7 padding for AES."""
    pad_len = 16 - (len(data) % 16)
    return data + bytes([pad_len] * pad_len)


def _crc32(data):
    """Calculate CRC32."""
    crc = 0xffffffff
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xedb88320
            else:
                crc >>= 1
    return crc ^ 0xffffffff


class TuyaBulb:
    def __init__(self, device_id, ip, local_key, version=3.3):
        self.device_id = device_id
        self.ip = ip
        self.local_key = local_key
        self.version = version
        self.seq_num = 0
        self.sock = None

    def connect(self):
        """Connect to the device."""
        if self.sock:
            try:
                self.sock.close()
            except:
                pass
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(5)
        self.sock.connect((self.ip, 6668))

    def close(self):
        """Close connection."""
        if self.sock:
            try:
                self.sock.close()
            except:
                pass
            self.sock = None

    def _send_command(self, dps):
        """Send a SET command with the given data points."""
        self.seq_num += 1

        # Build payload
        payload = json.dumps({
            'devId': self.device_id,
            'uid': self.device_id,
            't': '0',
            'dps': dps
        }, separators=(',', ':'))

        # Encrypt
        cipher = aes(self.local_key.encode(), 1)  # Mode 1 = ECB
        encrypted = cipher.encrypt(_pad(payload.encode()))

        # Add version header for 3.3
        encrypted = b'3.3' + b'\x00' * 12 + encrypted

        # Build packet
        cmd = 0x07  # SET command
        length = len(encrypted) + 8
        header = struct.pack('>IIII', 0x000055aa, self.seq_num, cmd, length)
        crc = _crc32(header[4:] + encrypted)
        packet = header + encrypted + struct.pack('>I', crc) + struct.pack('>I', 0x0000aa55)

        # Send and receive
        self.sock.send(packet)
        response = self.sock.recv(1024)

        # Check return code
        if len(response) >= 20:
            retcode = struct.unpack('>I', response[16:20])[0]
            return retcode == 0
        return False

    def turn_on(self):
        """Turn bulb on."""
        return self._send_command({'20': True})

    def turn_off(self):
        """Turn bulb off."""
        return self._send_command({'20': False})

    def set_white_mode(self, brightness, color_temp):
        """Set white mode with brightness and color temp."""
        brightness = max(10, min(1000, int(brightness)))
        color_temp = max(0, min(1000, int(color_temp)))
        return self._send_command({
            '20': True,
            '21': 'white',
            '22': brightness,
            '23': color_temp
        })
