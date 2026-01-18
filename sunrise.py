"""
Sunrise Alarm - Gradually brightens Tuya smart bulbs synced to sunrise.

Usage:
    python sunrise.py              # Run the sunrise routine (for scheduled task)
    python sunrise.py --test       # Quick 1-minute test ramp
    python sunrise.py --status     # Check bulb connectivity
    python sunrise.py --next       # Show next sunrise time
"""

import argparse
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
import urllib.request

import tinytuya

CONFIG_PATH = Path(__file__).parent / "config.json"


def load_config():
    """Load configuration from config.json."""
    with open(CONFIG_PATH) as f:
        return json.load(f)


def get_sunrise_time(lat: float, lon: float, date: datetime = None) -> datetime:
    """Fetch sunrise time from sunrise-sunset.org API."""
    if date is None:
        date = datetime.now()

    url = f"https://api.sunrise-sunset.org/json?lat={lat}&lng={lon}&date={date.strftime('%Y-%m-%d')}&formatted=0"

    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            data = json.loads(response.read().decode())
            if data["status"] == "OK":
                # Parse ISO format and convert to local time
                sunrise_utc = datetime.fromisoformat(data["results"]["sunrise"].replace("Z", "+00:00"))
                # Convert to naive datetime in local time
                sunrise_local = sunrise_utc.astimezone().replace(tzinfo=None)
                return sunrise_local
    except Exception as e:
        print(f"Failed to fetch sunrise time: {e}")
        # Fallback to 7:00 AM
        return datetime.now().replace(hour=7, minute=0, second=0, microsecond=0)

    return None


def connect_bulb(device: dict) -> tinytuya.BulbDevice:
    """Connect to a Tuya bulb device."""
    bulb = tinytuya.BulbDevice(device["id"], device["ip"], device["key"])
    bulb.set_version(float(device["version"]))
    bulb.set_socketPersistent(True)
    bulb.set_socketTimeout(5)
    return bulb


def check_bulb_status(device: dict) -> dict:
    """Check if a bulb is reachable and get its status."""
    try:
        bulb = connect_bulb(device)
        status = bulb.status()
        if "Error" in status:
            return {"reachable": False, "error": status["Error"]}
        return {"reachable": True, "status": status}
    except Exception as e:
        return {"reachable": False, "error": str(e)}


def interpolate_curve(curve: list, percent: float) -> tuple:
    """Interpolate brightness and color_temp from the sunrise curve at a given percent."""
    # Find the two keyframes we're between
    prev_point = curve[0]
    next_point = curve[-1]

    for i, point in enumerate(curve):
        if point["percent"] >= percent:
            next_point = point
            prev_point = curve[max(0, i - 1)]
            break

    # Handle exact match
    if prev_point["percent"] == next_point["percent"]:
        return prev_point["brightness"], prev_point["color_temp"]

    # Linear interpolation between keyframes
    range_pct = next_point["percent"] - prev_point["percent"]
    local_pct = (percent - prev_point["percent"]) / range_pct

    brightness = prev_point["brightness"] + (next_point["brightness"] - prev_point["brightness"]) * local_pct
    color_temp = prev_point["color_temp"] + (next_point["color_temp"] - prev_point["color_temp"]) * local_pct

    return int(brightness), int(color_temp)


def set_bulb_white(bulb: tinytuya.BulbDevice, brightness: int, color_temp: int):
    """Set bulb to white mode with brightness and color temp in a single command.

    Uses raw DPS values (10-1000 scale) to avoid flash when turning on.
    Sends all values together so bulb doesn't briefly restore previous state.
    """
    # Clamp values to valid range (10-1000 for brightness, 0-1000 for color temp)
    brightness = max(10, min(1000, int(brightness)))
    color_temp = max(0, min(1000, int(color_temp)))

    payload = bulb.generate_payload(tinytuya.CONTROL, {
        '20': True,      # Turn on
        '21': 'white',   # White mode
        '22': brightness,  # Brightness (10-1000)
        '23': color_temp   # Color temp (0-1000)
    })
    return bulb._send_receive(payload)


def run_sunrise_ramp(device: dict, duration_seconds: int, config: dict):
    """Run the sunrise brightness/color ramp on a single bulb."""
    bulb = connect_bulb(device)
    curve = config["sunrise_curve"]

    # Set initial state from curve (single command turns on + sets brightness)
    brightness, color_temp = interpolate_curve(curve, 0)
    set_bulb_white(bulb, brightness, color_temp)

    print(f"  Starting sunrise ramp for {device['name']} ({duration_seconds}s)")

    start_time = time.time()
    for i in range(duration_seconds):
        # Calculate progress percentage
        percent = (i / duration_seconds) * 100
        brightness, color_temp = interpolate_curve(curve, percent)

        try:
            set_bulb_white(bulb, brightness, color_temp)
        except Exception as e:
            print(f"  Warning: Failed to update bulb: {e}")

        # Sleep until next second
        target_time = start_time + i + 1
        sleep_time = target_time - time.time()
        if sleep_time > 0:
            time.sleep(sleep_time)

    # Set final values from curve
    brightness, color_temp = interpolate_curve(curve, 100)
    set_bulb_white(bulb, brightness, color_temp)
    print(f"  Completed sunrise ramp for {device['name']}")


def cmd_status(config: dict):
    """Check connectivity to all enabled bulbs."""
    print("Checking bulb status...\n")

    for device in config["devices"]:
        status_str = "(disabled)" if not device.get("enabled", True) else ""
        print(f"{device['name']} @ {device['ip']} {status_str}")

        if not device.get("enabled", True):
            continue

        result = check_bulb_status(device)
        if result["reachable"]:
            dps = result["status"].get("dps", {})
            on_off = "ON" if dps.get("20") else "OFF"
            brightness = dps.get("22", "?")
            print(f"  Status: {on_off}, Brightness: {brightness}")
        else:
            print(f"  UNREACHABLE: {result['error']}")
        print()


def cmd_next(config: dict):
    """Show the next scheduled sunrise time."""
    loc = config["location"]
    sunrise = get_sunrise_time(loc["latitude"], loc["longitude"])
    offset = config.get("sunrise_offset_minutes", 0)

    start_time = sunrise + timedelta(minutes=offset)

    # If already past today's sunrise, show tomorrow's
    if start_time < datetime.now():
        tomorrow = datetime.now() + timedelta(days=1)
        sunrise = get_sunrise_time(loc["latitude"], loc["longitude"], tomorrow)
        start_time = sunrise + timedelta(minutes=offset)

    print(f"Location: {loc['latitude']}, {loc['longitude']}")
    print(f"Actual sunrise: {sunrise.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Ramp start ({offset:+d} min): {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Ramp duration: {config['ramp_duration_minutes']} minutes")


def cmd_test(config: dict, duration: int = 60):
    """Run a quick test ramp."""
    print(f"Running {duration}-second test ramp...\n")

    enabled_devices = [d for d in config["devices"] if d.get("enabled", True)]

    if not enabled_devices:
        print("No enabled devices in config.json")
        return

    for device in enabled_devices:
        run_sunrise_ramp(device, duration_seconds=duration, config=config)

    print("\nTest complete!")


def cmd_run(config: dict):
    """Run the sunrise ramp (intended for scheduled task)."""
    print(f"Sunrise alarm triggered at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    enabled_devices = [d for d in config["devices"] if d.get("enabled", True)]

    if not enabled_devices:
        print("No enabled devices in config.json")
        return

    duration_seconds = config["ramp_duration_minutes"] * 60

    for device in enabled_devices:
        try:
            run_sunrise_ramp(device, duration_seconds, config)
        except Exception as e:
            print(f"Error with {device['name']}: {e}")

    print(f"\nSunrise complete at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


def main():
    parser = argparse.ArgumentParser(description="Sunrise alarm for Tuya smart bulbs")
    parser.add_argument("--test", nargs="?", const=60, type=int, metavar="SECONDS",
                        help="Run test ramp (default 60 seconds)")
    parser.add_argument("--status", action="store_true", help="Check bulb connectivity")
    parser.add_argument("--next", action="store_true", help="Show next sunrise time")
    args = parser.parse_args()

    config = load_config()

    if args.status:
        cmd_status(config)
    elif args.next:
        cmd_next(config)
    elif args.test is not None:
        cmd_test(config, duration=args.test)
    else:
        cmd_run(config)


if __name__ == "__main__":
    main()
