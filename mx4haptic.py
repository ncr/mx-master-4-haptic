#!/usr/bin/env python3
"""MX Master 4 haptic feedback control via raw HID++2.0.

Usage:
    mx4haptic.py play <waveform>     Play a haptic waveform
    mx4haptic.py demo                Play all supported waveforms
    mx4haptic.py level [0-100]       Get or set haptic intensity
    mx4haptic.py list                List supported waveforms
    mx4haptic.py listen              Trigger haptic on desktop notifications
    mx4haptic.py server [port]       Start HTTP server for triggering haptics
"""

import sys
import struct
import logging
from enum import IntEnum

import hid

LOGITECH_VID = 0x046D
HAPTIC_FEATURE_ID = 0x19B0
USAGE_PAGE_VENDOR = 0xFF00  # Logitech vendor-specific HID++ usage page

WAVEFORMS = {
    "sharp_state_change": 0x00,
    "damp_state_change": 0x01,
    "sharp_collision": 0x02,
    "damp_collision": 0x03,
    "subtle_collision": 0x04,
    "happy_alert": 0x05,
    "angry_alert": 0x06,
    "completed": 0x07,
    "square": 0x08,
    "wave": 0x09,
    "firework": 0x0A,
    "mad": 0x0B,
    "knock": 0x0C,
    "jingle": 0x0D,
    "ringing": 0x0E,
    "whisper_collision": 0x1B,
}

log = logging.getLogger("mx4haptic")


class HidppError(Exception):
    pass


class MX4Haptic:
    """Direct HID++2.0 interface to MX Master 4 haptic feedback."""

    def __init__(self):
        self.device = None
        self.device_idx = None
        self.haptic_idx = None
        self.supported_waveforms = None

    def open(self):
        """Find and open the MX Master 4 HID++ interface."""
        for dev in hid.enumerate(LOGITECH_VID):
            if dev["usage_page"] == USAGE_PAGE_VENDOR:
                product = dev.get("product_string", "")
                log.debug("Found Logitech HID++ device: %s (path=%s, iface=%s)",
                          product, dev["path"], dev.get("interface_number"))
                self.device_idx = dev["interface_number"]
                self.device = hid.device()
                self.device.open_path(dev["path"])
                log.info("Opened: %s", product)
                break

        if not self.device:
            raise HidppError("No Logitech HID++ device found")

        self._discover_haptic()
        return self

    def close(self):
        if self.device:
            self.device.close()
            self.device = None

    def __enter__(self):
        return self.open()

    def __exit__(self, *_):
        self.close()

    def _send(self, feature_idx, function_id, *args):
        """Send HID++2.0 message and return response data."""
        # Combine feature index with function ID into the 2-byte field:
        # bits [15:8] = feature index, bits [7:4] = function ID, bits [3:0] = software ID
        idx_func = (feature_idx << 8) | (function_id << 4)

        data = bytes(args)
        if len(data) < 3:
            data += b"\x00" * (3 - len(data))

        report_id = 0x10 if len(data) <= 3 else 0x11
        packet = struct.pack(">BBH", report_id, self.device_idx, idx_func) + data
        log.debug("TX: %s", packet.hex())
        self.device.write(list(packet))

        # Read response, skip messages for other devices
        while True:
            resp = self.device.read(20, timeout_ms=2000)
            if not resp:
                raise HidppError("Device read timeout")
            resp = bytes(resp)
            log.debug("RX: %s", resp.hex())
            r_report, r_dev, r_idx_func = struct.unpack(">BBH", resp[:4])
            if r_dev == self.device_idx:
                return resp[4:]

    def _discover_haptic(self):
        """Resolve HAPTIC feature ID (0x19B0) to device-specific index."""
        # IRoot.getFeature(featureID) - feature index 0x00, function 0x00
        resp = self._send(0x00, 0x00, (HAPTIC_FEATURE_ID >> 8) & 0xFF,
                          HAPTIC_FEATURE_ID & 0xFF)
        self.haptic_idx = resp[0]
        if self.haptic_idx == 0:
            raise HidppError("Device does not support HAPTIC feature (0x19B0)")
        log.info("HAPTIC feature at index 0x%02X", self.haptic_idx)

        # GetCapabilities - function 0x00 on the haptic feature
        resp = self._send(self.haptic_idx, 0x00)
        # Bytes 4-7: waveform support bitmask (bytes 0-3 are other capability info)
        bitmask = struct.unpack(">I", resp[4:8])[0]
        self.supported_waveforms = {}
        for name, wid in WAVEFORMS.items():
            if bitmask & (1 << wid):
                self.supported_waveforms[name] = wid
        log.info("Supported waveforms: %s", list(self.supported_waveforms.keys()))

    def play(self, waveform):
        """Trigger a haptic waveform by name or ID."""
        if isinstance(waveform, str):
            waveform = waveform.lower().replace(" ", "_").replace("-", "_")
            if waveform not in WAVEFORMS:
                raise ValueError(f"Unknown waveform: {waveform}. Use 'list' to see options.")
            wid = WAVEFORMS[waveform]
        else:
            wid = int(waveform)

        # PlayWaveform - function 0x04 (function index within the feature)
        self._send(self.haptic_idx, 0x04, wid)
        log.debug("Played waveform %d", wid)

    def get_level(self):
        """Get current haptic level. Returns (enabled, level)."""
        resp = self._send(self.haptic_idx, 0x01)
        enabled = bool(resp[0] & 0x01)
        level = resp[1]
        return enabled, level

    def set_level(self, level):
        """Set haptic intensity (0=off, 1-100)."""
        if level == 0:
            self._send(self.haptic_idx, 0x02, 0x00, 50)
        else:
            self._send(self.haptic_idx, 0x02, 0x01, min(100, max(1, level)))


def cmd_play(mx, args):
    if not args:
        print("Usage: mx4haptic.py play <waveform>")
        print("Use 'mx4haptic.py list' to see available waveforms")
        return 1
    mx.play(args[0])
    print(f"Played: {args[0]}")


def cmd_demo(mx, args):
    import time
    waveforms = mx.supported_waveforms or WAVEFORMS
    for name, wid in waveforms.items():
        print(f"  [{wid:02X}] {name}...", flush=True)
        mx.play(wid)
        time.sleep(2.5)
    print("Done!")


def cmd_level(mx, args):
    if args:
        level = int(args[0])
        mx.set_level(level)
        print(f"Haptic level set to {level}")
    else:
        enabled, level = mx.get_level()
        print(f"Haptic: {'on' if enabled else 'off'}, level: {level}")


def cmd_list(mx, args):
    print("Supported waveforms on this device:")
    waveforms = mx.supported_waveforms or WAVEFORMS
    for name, wid in sorted(waveforms.items(), key=lambda x: x[1]):
        print(f"  [{wid:02X}] {name}")


def cmd_listen(mx, args):
    """Listen for D-Bus desktop notifications and trigger haptic."""
    import subprocess
    waveform = args[0] if args else "mad"
    print(f"Listening for notifications, will play '{waveform}'... (Ctrl+C to stop)")
    proc = subprocess.Popen(
        ["dbus-monitor", "--session", "interface='org.freedesktop.Notifications',member='Notify'"],
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        for line in proc.stdout:
            if "member=Notify" in line:
                try:
                    mx.play(waveform)
                except Exception as e:
                    log.warning("Haptic failed: %s", e)
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        proc.terminate()


def cmd_server(mx, args):
    """Start a simple HTTP server for triggering haptics from other tools."""
    from http.server import HTTPServer, BaseHTTPRequestHandler
    import json

    port = int(args[0]) if args else 8484

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            path = self.path.strip("/")
            if path == "play":
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length)) if length else {}
                waveform = body.get("waveform", "mad")
                try:
                    mx.play(waveform)
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b'{"ok":true}')
                except Exception as e:
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": str(e)}).encode())
            else:
                self.send_response(404)
                self.end_headers()

        def do_GET(self):
            path = self.path.strip("/")
            if path == "play":
                # GET /play?waveform=knock
                from urllib.parse import urlparse, parse_qs
                qs = parse_qs(urlparse(self.path).query)
                waveform = qs.get("waveform", ["mad"])[0]
                try:
                    mx.play(waveform)
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b'{"ok":true}')
                except Exception as e:
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": str(e)}).encode())
            elif path == "waveforms":
                waveforms = mx.supported_waveforms or WAVEFORMS
                self.send_response(200)
                self.end_headers()
                self.wfile.write(json.dumps(waveforms).encode())
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, fmt, *a):
            log.debug(fmt, *a)

    server = HTTPServer(("127.0.0.1", port), Handler)
    print(f"Haptic server on http://127.0.0.1:{port}")
    print(f"  POST /play  {{\"waveform\": \"knock\"}}")
    print(f"  GET  /play?waveform=knock")
    print(f"  GET  /waveforms")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


COMMANDS = {
    "play": cmd_play,
    "demo": cmd_demo,
    "level": cmd_level,
    "list": cmd_list,
    "listen": cmd_listen,
    "server": cmd_server,
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        return 0

    cmd = sys.argv[1]
    if cmd not in COMMANDS:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        return 1

    verbose = "-v" in sys.argv
    if verbose:
        sys.argv.remove("-v")
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    try:
        with MX4Haptic() as mx:
            return COMMANDS[cmd](mx, sys.argv[2:])
    except (HidppError, OSError) as e:
        if cmd == "play":
            return 0
        log.error("%s", e)
        return 1


if __name__ == "__main__":
    sys.exit(main() or 0)
