import network
import ntptime
import time
import urequests
import gc
from machine import RTC

import config
from tuya import TuyaBulb


def connect_wifi():
    """Connect to WiFi."""
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)

    if wlan.isconnected():
        print("Already connected to WiFi")
        return True

    print(f"Connecting to {config.WIFI_SSID}...")
    wlan.connect(config.WIFI_SSID, config.WIFI_PASSWORD)

    max_wait = 20
    while max_wait > 0:
        if wlan.isconnected():
            break
        max_wait -= 1
        print(".", end="")
        time.sleep(1)

    if wlan.isconnected():
        print(f"\nConnected! IP: {wlan.ifconfig()[0]}")
        return True
    else:
        print("\nFailed to connect")
        return False


def sync_time():
    """Sync time via NTP."""
    print("Syncing time via NTP...")
    try:
        ntptime.settime()
        rtc = RTC()
        dt = rtc.datetime()
        print(f"Time synced: {dt[0]}-{dt[1]:02d}-{dt[2]:02d} {dt[4]:02d}:{dt[5]:02d}:{dt[6]:02d} UTC")
        return True
    except Exception as e:
        print(f"NTP sync failed: {e}")
        return False


def get_sunrise_time():
    """Fetch sunrise time from API."""
    url = f"https://api.sunrise-sunset.org/json?lat={config.LATITUDE}&lng={config.LONGITUDE}&formatted=0"

    try:
        print("Fetching sunrise time...")
        response = urequests.get(url)
        data = response.json()
        response.close()

        if data["status"] == "OK":
            sunrise_str = data["results"]["sunrise"]
            time_part = sunrise_str.split("T")[1].split("+")[0].split("-")[0]
            hour, minute, second = map(int, time_part.split(":"))

            # Convert UTC to local time
            hour += config.TIMEZONE_OFFSET
            if hour < 0:
                hour += 24
            elif hour >= 24:
                hour -= 24

            print(f"Sunrise (local): {hour:02d}:{minute:02d}:{second:02d}")
            return (hour, minute, second)
    except Exception as e:
        print(f"Failed to fetch sunrise: {e}")

    return (7, 0, 0)


def interpolate_curve(curve, percent):
    """Interpolate brightness and color_temp from curve."""
    prev_point = curve[0]
    next_point = curve[-1]

    for i, point in enumerate(curve):
        if point[0] >= percent:
            next_point = point
            prev_point = curve[max(0, i - 1)]
            break

    if prev_point[0] == next_point[0]:
        return prev_point[1], prev_point[2]

    range_pct = next_point[0] - prev_point[0]
    local_pct = (percent - prev_point[0]) / range_pct

    brightness = int(prev_point[1] + (next_point[1] - prev_point[1]) * local_pct)
    color_temp = int(prev_point[2] + (next_point[2] - prev_point[2]) * local_pct)

    return brightness, color_temp


def run_sunrise_ramp(bulb, duration_seconds):
    """Run the sunrise ramp on a bulb."""
    print(f"Starting sunrise ramp ({duration_seconds}s)...")

    bulb.connect()
    brightness, color_temp = interpolate_curve(config.SUNRISE_CURVE, 0)
    bulb.set_white_mode(brightness, color_temp)

    start = time.time()

    for i in range(duration_seconds):
        percent = (i / duration_seconds) * 100
        brightness, color_temp = interpolate_curve(config.SUNRISE_CURVE, percent)

        try:
            bulb.set_white_mode(brightness, color_temp)
        except Exception as e:
            print(f"Error setting bulb: {e}")
            try:
                bulb.connect()
            except:
                pass

        if i % 60 == 0:
            print(f"  {i}s: {percent:.0f}% brightness={brightness} temp={color_temp}")
            gc.collect()

        elapsed = time.time() - start
        sleep_time = (i + 1) - elapsed
        if sleep_time > 0:
            time.sleep(sleep_time)

    brightness, color_temp = interpolate_curve(config.SUNRISE_CURVE, 100)
    bulb.set_white_mode(brightness, color_temp)
    bulb.close()

    print("Sunrise ramp complete!")


def get_current_time():
    """Get current local time as tuple (hour, minute, second)."""
    rtc = RTC()
    dt = rtc.datetime()  # (year, month, day, weekday, hour, minute, second, subsecond)
    # RTC is in UTC, adjust for timezone
    hour = (dt[4] + config.TIMEZONE_OFFSET) % 24
    return (hour, dt[5], dt[6])


def time_to_seconds(h, m, s):
    """Convert time to seconds since midnight."""
    return h * 3600 + m * 60 + s


def main():
    print("\n=== Sunrise Alarm ESP32 ===\n")

    mode = getattr(config, 'MODE', 'sunrise')
    print(f"Mode: {mode}")

    if not connect_wifi():
        print("Cannot continue without WiFi")
        return

    if not sync_time():
        print("Warning: time may be inaccurate")

    bulbs = []
    for dev in config.DEVICES:
        bulb = TuyaBulb(dev["id"], dev["ip"], dev["key"], dev["version"])
        bulbs.append((dev["name"], bulb))

    print(f"\nConfigured {len(bulbs)} bulb(s)")

    sunrise_time = None
    ramp_triggered_today = False
    last_hour = -1

    while True:
        gc.collect()

        now = get_current_time()
        now_secs = time_to_seconds(*now)

        if mode == "static":
            # Static mode: fixed start time from config
            ramp_start_secs = time_to_seconds(config.STATIC_START_HOUR, config.STATIC_START_MINUTE, 0)
        else:
            # Sunrise mode: fetch sunrise and calculate offset
            if sunrise_time is None or (now[0] == 3 and now[1] == 0 and last_hour != 3):
                sunrise_time = get_sunrise_time()
                ramp_triggered_today = False

            sunrise_secs = time_to_seconds(*sunrise_time)
            ramp_start_secs = sunrise_secs + (config.SUNRISE_OFFSET_MINUTES * 60)
            if ramp_start_secs < 0:
                ramp_start_secs += 86400

        last_hour = now[0]

        # Check if time to start ramp (within 30 second window)
        if not ramp_triggered_today and abs(now_secs - ramp_start_secs) < 30:
            print(f"\n*** ALARM at {now[0]:02d}:{now[1]:02d}:{now[2]:02d} ***\n")
            ramp_triggered_today = True

            duration = config.RAMP_DURATION_MINUTES * 60
            for name, bulb in bulbs:
                print(f"Running ramp for {name}")
                try:
                    run_sunrise_ramp(bulb, duration)
                except Exception as e:
                    print(f"Error with {name}: {e}")

        # Reset trigger after noon
        if now[0] >= 12:
            ramp_triggered_today = False

        # Status every 10 minutes
        if now[1] % 10 == 0 and now[2] < 15:
            ramp_h = ramp_start_secs // 3600
            ramp_m = (ramp_start_secs % 3600) // 60
            print(f"[{now[0]:02d}:{now[1]:02d}] Next ramp: {ramp_h:02d}:{ramp_m:02d}, triggered: {ramp_triggered_today}")

        time.sleep(10)


def test_bulb(duration=60):
    """Quick test - run sunrise ramp."""
    print(f"\n=== TEST MODE ({duration}s) ===\n")

    if not connect_wifi():
        return

    for dev in config.DEVICES:
        print(f"Testing {dev['name']}...")
        bulb = TuyaBulb(dev["id"], dev["ip"], dev["key"], dev["version"])
        try:
            run_sunrise_ramp(bulb, duration)
        except Exception as e:
            print(f"Error: {e}")


# To test: import main; main.test_bulb(60)
# To run: import main; main.main()

if __name__ == "__main__":
    main()
