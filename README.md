# Tuya Sunrise Alarm

A sunrise alarm system that gradually brightens Tuya smart bulbs, simulating a natural sunrise to help you wake up.

## Features

- **Sunrise simulation** - Gradual 30-minute ramp from dim warm red to bright daylight
- **Two modes**:
  - `static` - Fixed daily start time (default: 7:30 AM)
  - `sunrise` - Synced to actual sunrise via API
- **Local control** - No cloud dependency after initial setup
- **ESP32 standalone** - Runs autonomously on MicroPython

## Hardware

- ESP32 (any variant with WiFi)
- Tuya-compatible smart bulbs (tested with 120V A19 9W bulbs, protocol v3.3)

## Setup

### 1. Get Tuya Device Keys

You need local keys for your bulbs (one-time cloud access required):

```bash
pip install tinytuya
python -m tinytuya wizard
```

Follow the prompts to link your Tuya IoT account and extract device keys.

### 2. Configure

Edit `esp32/config.py`:

```python
# WiFi
WIFI_SSID = "your_ssid"
WIFI_PASSWORD = "your_password"

# Mode: "static" or "sunrise"
MODE = "static"
STATIC_START_HOUR = 7
STATIC_START_MINUTE = 30

# Devices
DEVICES = [
    {
        "name": "bedroom",
        "id": "your_device_id",
        "ip": "192.168.1.xxx",
        "key": "your_local_key",
        "version": 3.3,
    },
]
```

### 3. Flash ESP32

```bash
# Install MicroPython
esptool.py --chip esp32 erase_flash
esptool.py --chip esp32 write_flash -z 0x1000 esp32-xxx.bin

# Upload files
mpremote connect COM3 fs cp esp32/config.py :config.py
mpremote connect COM3 fs cp esp32/tuya.py :tuya.py
mpremote connect COM3 fs cp esp32/main.py :main.py
```

### 4. Run

Reset the ESP32 - it will auto-run `main.py` on boot.

## Files

```
├── esp32/
│   ├── config.py      # ESP32 configuration
│   ├── main.py        # Main alarm loop
│   └── tuya.py        # Tuya local protocol implementation
├── config.json        # Desktop script configuration
├── sunrise.py         # Desktop version (requires tinytuya)
└── devices.json       # Device keys from tinytuya wizard
```

## Desktop Usage

For testing or running from a PC instead of ESP32:

```bash
pip install tinytuya

python sunrise.py --status    # Check bulb connectivity
python sunrise.py --test 60   # Run 60-second test ramp
python sunrise.py --next      # Show next sunrise time
python sunrise.py             # Run full sunrise ramp
```

## Sunrise Curve

The brightness/color temperature ramp simulates natural sunrise:

| Progress | Brightness | Color Temp | Description |
|----------|------------|------------|-------------|
| 0% | 10 | 0 (warm) | Pre-dawn deep red |
| 15% | 50 | 50 | First light orange |
| 30% | 150 | 150 | Dawn orange-yellow |
| 50% | 400 | 300 | Sun cresting yellow |
| 70% | 700 | 450 | Early morning warm white |
| 85% | 900 | 550 | Morning light |
| 100% | 1000 | 650 (cool) | Full daylight |

## License

MIT
