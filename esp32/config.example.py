# WiFi credentials
WIFI_SSID = "your_ssid"
WIFI_PASSWORD = "your_password"

# Mode: "static" for fixed time, "sunrise" for sunrise-synced
MODE = "static"

# Static mode settings (24h format)
STATIC_START_HOUR = 7
STATIC_START_MINUTE = 30
RAMP_DURATION_MINUTES = 30

# Sunrise mode settings
LATITUDE = 38.9072
LONGITUDE = -77.0369
TIMEZONE_OFFSET = -5  # EST (adjust for DST: -4 for EDT)
SUNRISE_OFFSET_MINUTES = -30  # Start ramp 30 min before sunrise

# Tuya bulb devices
DEVICES = [
    {
        "name": "bedroom",
        "id": "your_device_id_here",
        "ip": "192.168.1.xxx",
        "key": "your_local_key_here",
        "version": 3.3,
    },
]

# Sunrise color/brightness curve (percent -> brightness, color_temp)
SUNRISE_CURVE = [
    (0,   10,   0),    # pre-dawn deep red
    (15,  50,   50),   # first light orange
    (30,  150,  150),  # dawn orange-yellow
    (50,  400,  300),  # sun cresting yellow
    (70,  700,  450),  # early morning warm white
    (85,  900,  550),  # morning light
    (100, 1000, 650),  # full daylight
]
