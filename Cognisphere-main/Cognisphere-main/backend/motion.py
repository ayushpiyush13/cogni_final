"""
CropShield AI - Arduino PIR motion monitor.

Reads the 0 / 1 lines your Arduino prints on the serial port (9600 baud) in a background thread:
    1 = motion in front of the PIR sensor     0 = clear

    monitor = MotionMonitor()          # auto-detects the Arduino
    monitor.start()
    monitor.snapshot()  ->  {"status": "detected" | "clear" | "no_signal" | "offline", "motion": bool, ...}

Settings (all optional, environment variables):
    ARDUINO_PORT      e.g. COM3 or /dev/ttyACM0 (default: auto-detect)
    ARDUINO_BAUD      default 9600
    MOTION_SIMULATE   1 = fake sensor for demos without hardware
    MOTION_STALE_S    seconds of silence before "no signal" (default 5; 0 = never - use it if your
                      sketch only prints when the state CHANGES)
    MOTION_LOG        csv file for the event history (default: motion_events.csv next to this file)

Needs:  pip install pyserial        (NOT the package called "serial")
"""
import collections
import csv
import datetime
import os
import random
import threading
import time
from pathlib import Path

try:
    import serial
    from serial.tools import list_ports
except ImportError:                      # the app still runs, the card just explains what to install
    serial = None
    list_ports = None

CLEAR_AFTER = 0.6        # seconds of "0" before motion counts as finished (filters PIR flicker)
RECENT = 8               # events kept in snapshot()
ARDUINO_VIDS = {0x2341, 0x2A03, 0x1A86, 0x0403, 0x10C4, 0x1B4F, 0x239A}   # Arduino, CH340, FTDI, CP210x, SparkFun, Adafruit
_ACTIVE_ATTR = "_cropshield_motion_active"      # lives on the threading module so it survives Streamlit reloads


def find_port():
    """Best guess for the Arduino's serial port, or None."""
    env = os.getenv("ARDUINO_PORT", "").strip()
    if env:
        return env
    if list_ports is None:
        return None
    ports = [p for p in list_ports.comports()
             if "bluetooth" not in f"{p.description} {p.hwid}".lower()]

    def score(p):
        text = f"{p.description} {p.manufacturer} {p.product}".lower()
        s = 3 if p.vid in ARDUINO_VIDS else 0
        s += 2 if any(k in text for k in ("arduino", "ch340", "ch341", "usb serial", "usb-serial", "ftdi", "cp210")) else 0
        s += 1 if any(k in (p.device or "") for k in ("ttyACM", "ttyUSB", "usbmodem", "usbserial")) else 0
        return s

    ports.sort(key=score, reverse=True)
    if ports and (score(ports[0]) > 0 or (len(ports) == 1 and ports[0].vid is not None)):
        return ports[0].device
    return None


def ports_seen():
    """Human-readable list of serial ports the computer reports (for the help message)."""
    if list_ports is None:
        return ""
    return ", ".join(f"{p.device} ({p.description})" for p in list_ports.comports()) or "none"

def port_choices():
    """[(device, description), ...] for the dropdown, Bluetooth ports left out."""
    if list_ports is None:
        return []
    return [(p.device, p.description) for p in list_ports.comports()
            if "bluetooth" not in f"{p.description} {p.hwid}".lower()]

def _friendly(err, port):
    t = str(err)
    if "PermissionError" in t or "Access is denied" in t or "busy" in t.lower() or "Errno 16" in t:
        return (f"{port} is busy. Close the Arduino IDE Serial Monitor / Plotter (only one program can use "
                "the port), then wait a few seconds.")
    if "FileNotFoundError" in t or "could not open port" in t.lower() or "No such file" in t:
        return f"Cannot open {port}. Is the Arduino plugged in? Check the port name."
    return f"{port}: {t}"


def _parse(raw):
    txt = raw.decode("utf-8", "ignore").strip()
    return int(txt) if txt in ("0", "1") else None


class MotionMonitor:
    def __init__(self, port=None, baud=None, simulate=None):
        self.port_cfg = (port or "").strip() or None
        self.baud = int(baud or os.getenv("ARDUINO_BAUD", 9600))
        self.simulate = (os.getenv("MOTION_SIMULATE", "").lower() in ("1", "true", "yes")
                         if simulate is None else bool(simulate))
        self.stale_after = float(os.getenv("MOTION_STALE_S", 5))
        self.log_file = Path(os.getenv("MOTION_LOG") or Path(__file__).with_name("motion_events.csv"))

        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread = None
        self.port = None
        self.connected = False
        self.error = ""
        self.lines = 0
        self.last_value = None
        self.last_line_ts = 0.0
        self.last_one_ts = 0.0
        self.motion = False
        self._cur = None
        self.events = collections.deque(maxlen=200)      # newest first: {"start", "end"}
        self._load_log()

    # ------------------------------------------------------------------ lifecycle
    def start(self):
        old = getattr(threading, _ACTIVE_ATTR, None)
        if old is not None and old is not self:
            old.stop()                                   # a previous copy (Streamlit reload) must release the port
        setattr(threading, _ACTIVE_ATTR, self)
        if self._thread is None or not self._thread.is_alive():
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name="motion-monitor", daemon=True)
            self._thread.start()
        return self

    def stop(self):
        self._stop.set()

    # ------------------------------------------------------------------ state machine (call under lock)
    def _feed(self, value, now):
        with self._lock:
            self.lines += 1
            self.last_line_ts = now
            self.last_value = value
            if value == 1:
                self.last_one_ts = now
                if not self.motion:
                    self.motion = True
                    self._cur = {"start": now, "end": None}
                    self.events.appendleft(self._cur)
            self._settle(now)

    def _settle(self, now):
        with self._lock:
            if self.motion and self.last_value == 0 and now - self.last_one_ts >= CLEAR_AFTER:
                self._end_event(self.last_one_ts)

    def _end_event(self, end_ts):
        with self._lock:
            if self._cur is not None:
                self._cur["end"] = max(end_ts, self._cur["start"])
                self._log_event(self._cur)
            self.motion = False
            self._cur = None

    def _on_connect(self, port):
        with self._lock:
            self.port, self.connected, self.error = port, True, ""
            self.lines, self.last_value, self.last_line_ts = 0, None, 0.0

    def _on_disconnect(self, msg):
        with self._lock:
            if self.motion:
                self._end_event(time.time())
            self.connected = False
            self.error = msg

    # ------------------------------------------------------------------ reader thread
    def _run(self):
        if self.simulate:
            return self._run_simulation()
        while not self._stop.is_set():
            if serial is None:
                self.error = "pyserial is not installed. Run:  pip install pyserial"
                self._stop.wait(5)
                continue
            port = self.port_cfg or find_port()
            if not port:
                self.connected, self.port = False, None
                self.error = ("No Arduino found. Plug it in with a data USB cable and close the Arduino Serial Monitor. "
                              f"Ports seen: {ports_seen()}. You can also set the port by hand in Sensor settings.")
                self._stop.wait(2)
                continue
            try:
                with serial.Serial(port, self.baud, timeout=1) as ser:
                    self._on_connect(port)
                    while not self._stop.is_set():
                        raw = ser.readline()
                        now = time.time()
                        value = _parse(raw) if raw else None
                        if value is not None:
                            self._feed(value, now)
                        else:
                            self._settle(now)
            except (serial.SerialException, OSError, ValueError) as e:
                self._on_disconnect(_friendly(e, port))
                self._stop.wait(2)
        self._on_disconnect("stopped")

    def _run_simulation(self):
        """Pretends to be the Arduino: quiet spells and short bursts of 'motion' at ~20 lines/s."""
        self._on_connect("SIMULATED")
        rnd = random.Random()
        phase_end, value = time.time() + rnd.uniform(3, 6), 0
        while not self._stop.is_set():
            now = time.time()
            if now >= phase_end:
                value = 1 - value
                phase_end = now + (rnd.uniform(2, 5) if value else rnd.uniform(8, 16))
            self._feed(value, now)
            self._stop.wait(0.05)
        self._on_disconnect("stopped")

    # ------------------------------------------------------------------ history file
    def _log_event(self, ev):
        try:
            new = not self.log_file.exists()
            with open(self.log_file, "a", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                if new:
                    w.writerow(["start", "end", "duration_s"])
                w.writerow([datetime.datetime.fromtimestamp(ev["start"]).isoformat(timespec="seconds"),
                            datetime.datetime.fromtimestamp(ev["end"]).isoformat(timespec="seconds"),
                            round(ev["end"] - ev["start"], 1)])
        except OSError:
            pass

    def _load_log(self):
        try:
            with open(self.log_file, newline="", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))[-self.events.maxlen:]
            for r in rows:                                  # oldest first -> appendleft keeps newest first
                self.events.appendleft({"start": datetime.datetime.fromisoformat(r["start"]).timestamp(),
                                       "end": datetime.datetime.fromisoformat(r["end"]).timestamp()})
        except (OSError, KeyError, ValueError):
            pass

    # ------------------------------------------------------------------ what the UI reads
    def snapshot(self):
        now = time.time()
        with self._lock:
            self._settle(now)
            silent = now - self.last_line_ts if self.last_line_ts else None
            if not self.connected:
                status = "offline"
            elif self.lines == 0 or (self.stale_after > 0 and silent is not None and silent > self.stale_after):
                status = "no_signal"
            else:
                status = "detected" if self.motion else "clear"
            today = datetime.date.today()
            evs = []
            for e in list(self.events)[:RECENT]:
                end = e["end"] or now
                evs.append({"start": e["start"], "end": e["end"], "duration": max(0.0, end - e["start"])})
            return {
                "status": status,
                "motion": status == "detected",
                "connected": self.connected,
                "port": self.port,
                "baud": self.baud,
                "simulated": self.simulate,
                "error": self.error,
                "lines": self.lines,
                "last_motion_ts": (self.last_one_ts or (self.events[0]["start"] if self.events else None)),
                "today": sum(1 for e in self.events if datetime.date.fromtimestamp(e["start"]) == today),
                "events": evs,
            }


def ago(ts, now=None):
    """'just now', '12 s ago', '3 min ago', '2 h ago', '5 d ago' (or '-' when unknown)."""
    if not ts:
        return "-"
    d = max(0, (now or time.time()) - ts)
    if d < 3:
        return "just now"
    if d < 60:
        return f"{int(d)} s ago"
    if d < 3600:
        return f"{int(d // 60)} min ago"
    if d < 86400:
        return f"{int(d // 3600)} h ago"
    return f"{int(d // 86400)} d ago"


if __name__ == "__main__":                       # quick check from a terminal: python motion.py
    m = MotionMonitor().start()
    try:
        while True:
            s = m.snapshot()
            print(f"{s['status']:10s} port={s['port']} lines={s['lines']} today={s['today']} {s['error']}")
            time.sleep(1)
    except KeyboardInterrupt:
        m.stop()
