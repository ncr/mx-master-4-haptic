# mx-master-4-haptic

Fast haptic feedback control for the Logitech MX Master 4 mouse on Linux via raw HID++2.0.

Bypasses Solaar's ~1 second CLI startup overhead by talking directly to the device over HID. Opens the device, discovers the haptic feature dynamically, and triggers waveforms instantly.

## Requirements

- Linux
- Python 3
- `python-hidapi` (`sudo pacman -S python-hidapi` on Arch, `pip install hidapi` elsewhere)
- Logitech MX Master 4 connected via Bolt USB receiver or Bluetooth

## Usage

```bash
# Play a waveform
python3 mx4haptic.py play mad

# List supported waveforms on your device
python3 mx4haptic.py list

# Demo all waveforms (2.5s between each)
python3 mx4haptic.py demo

# Get/set haptic intensity (0=off, 1-100)
python3 mx4haptic.py level
python3 mx4haptic.py level 100

# Vibrate on every desktop notification (D-Bus)
python3 mx4haptic.py listen [waveform]

# HTTP API for integration with other tools
python3 mx4haptic.py server [port]
```

## Waveforms

The MX Master 4 supports 15 haptic waveforms:

| ID | Name |
|----|------|
| 0x00 | sharp_state_change |
| 0x01 | damp_state_change |
| 0x02 | sharp_collision |
| 0x03 | damp_collision |
| 0x04 | subtle_collision |
| 0x05 | happy_alert |
| 0x06 | angry_alert |
| 0x07 | completed |
| 0x08 | square |
| 0x09 | wave |
| 0x0A | firework |
| 0x0B | mad |
| 0x0C | knock |
| 0x0D | jingle |
| 0x0E | ringing |

## HTTP API

Start the server:

```bash
python3 mx4haptic.py server 8484
```

Trigger haptics:

```bash
# GET
curl "localhost:8484/play?waveform=mad"

# POST
curl -X POST localhost:8484/play -d '{"waveform": "firework"}'

# List supported waveforms
curl localhost:8484/waveforms
```

## Claude Code integration

Add a hook to `~/.claude/settings.json` to get haptic feedback when Claude needs your attention:

```json
{
  "hooks": {
    "Notification": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 /path/to/mx4haptic.py play mad"
          }
        ]
      }
    ]
  }
}
```

## How it works

Communicates with the mouse using [Logitech's HID++2.0 protocol](https://github.com/Logitech/cpg-docs/tree/master/hidpp20):

1. Enumerates HID devices, finds the Logitech vendor-specific interface (usage page 0xFF00)
2. Resolves the HAPTIC feature ID (`0x19B0`) to a device-specific feature index via `IRoot.getFeature`
3. Queries supported waveforms via `GetCapabilities` (function 0x00)
4. Triggers waveforms via `PlayWaveform` (function 0x04)

## Related projects

- [Solaar](https://github.com/pwr-Solaar/Solaar) - Full Linux device manager for Logitech devices (supports haptic since v1.1.17)
- [mx4hyprland](https://github.com/MyrikLD/mx4hyprland) - Haptic on Hyprland window focus
- [mx4notifications](https://github.com/lukasfri/mx4notifications) - Haptic on desktop notifications

## License

MIT
