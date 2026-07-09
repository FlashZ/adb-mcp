# adb-mcp

**A comprehensive, structured-output [MCP](https://modelcontextprotocol.io) server around the Android Debug Bridge.**

Give an AI agent (Claude Code, or any MCP client) direct, first-class control of an
Android device — launch apps, drive the UI, capture logs and screenshots, push/pull
files, wire up port forwards — so the workflow becomes:

```
agent → launch_package() → capture_screen() → tap_element("Send") → logcat_dump() → pull() → analyse()
```

…with **no copy/paste of shell output**, and **no unrestricted `adb shell` tool** (that
escape hatch is opt-in and off by default).

**90 tools** across 9 groups. Every tool returns structured JSON — never raw terminal text.

---

## Why

The usual loop is: you type `adb shell …`, copy the output, paste it to the AI, it
reasons, tells you the next command, you type it. adb-mcp collapses that into tools the
agent calls itself. It was built for mobile reverse-engineering / QA automation, but
works for any adb task.

## Design principles

- **Idempotent, named operations** — `force_stop(pkg)`, `reverse_port(...)` — not
  `execute_any_shell_command()`.
- **Structured outputs** — `{"pid": 8421, "status": "running"}`, not a wall of text.
- **Scoped, not omnipotent** — no generic shell by default. `run_shell` exists only as an
  explicit opt-in (`ADB_MCP_ALLOW_SHELL=1`). Destructive tools (`delete_file`,
  `clear_app_data`, `uninstall`) are clearly named and `delete_file` refuses protected
  roots (`/`, `/system`, `/data`, …).
- **Multi-device aware** — every device tool takes an optional `serial`; `get_devices`
  flags `is_usb` so you can tell a USB phone from a network/emulator target (e.g. WSA).

---

## Install

```bash
pip install adbmcp          # from PyPI
# or from a clone:
pip install -e .
```

> PyPI package name is **`adbmcp`**; the import package and `python -m` target are
> **`adb_mcp`**, and the installed console command is **`adbmcp`**.

Requires Python ≥ 3.10 and the Android platform-tools (`adb`) on your machine.
`adb` is auto-detected from `ANDROID_HOME`, the default SDK location, scoop, or `PATH`;
override with `ADB_PATH`.

## Register with an MCP client

**Claude Code** (`.mcp.json` in your project, or `claude mcp add`):

```jsonc
{
  "mcpServers": {
    "adb": {
      "command": "python",
      "args": ["-m", "adb_mcp.server"],
      "env": {
        "ADB_SERIAL": "RFCWC17BKJY",   // optional default device
        "ADB_MCP_ALLOW_SHELL": "0"      // set "1" to enable run_shell
      }
    }
  }
}
```

```bash
claude mcp add adb -- python -m adb_mcp.server
```

An example config lives in [`examples/mcp.json`](examples/mcp.json).

## Configuration

| env var | meaning |
|---|---|
| `ADB_PATH` | Path to `adb` (auto-detected if unset). |
| `ANDROID_HOME` / `ANDROID_SDK_ROOT` | SDK root used for adb auto-detection. |
| `ADB_SERIAL` | Default device serial. USB phone: `RFCWC17BKJY`; WSA/emulator: `127.0.0.1:58526`. |
| `ADB_MCP_ALLOW_SHELL` | `1`/`true` enables the opt-in `run_shell` escape hatch (default off). |

Every device-facing tool also accepts a `serial` argument to override per call, and you
can switch the session default at runtime with `set_default_device`.

---

## Tool reference (90)

### Device (15)
`get_devices` · `get_state` · `adb_version` · `get_device_properties` · `get_screen_info`
· `get_battery` · `connect` · `disconnect` · `wait_for_device` · `reboot`
· `set_default_device` · `get_default_device` · `root_adb` · `unroot_adb` · `remount`

### Apps (16)
`list_packages` · `launch_package` · `launch_activity` · `force_stop` · `kill_background`
· `clear_app_data` · `app_status` · `get_current_activity` · `get_package_info`
· `install_apk` · `uninstall` · `grant_permission` · `revoke_permission`
· `set_package_enabled` · `start_service` · `send_broadcast`

### Input (12)
`tap` · `long_press` · `swipe` · `drag` · `text` · `keyevent` · `press_home`
· `press_back` · `press_recents` · `press_power` · `press_enter` · `wake_and_unlock`

### UI automation (3)
`dump_ui` · `find_elements` · `tap_element` — parse the live view hierarchy
(uiautomator) and tap elements by text / resource-id / content-description instead of
guessing pixel coordinates.

### Logs (8)
`logcat_start` · `logcat_stop` · `logcat_dump` · `logcat_filter` · `logcat_clear`
· `get_crash_log` · `get_anr_traces` · `capture_bugreport` — background capture with
parsed records `{time, pid, tid, level, tag, message}`.

### Media (5)
`capture_screen` (inline PNG) · `capture_screen_to_file` · `capture_screen_base64`
· `record_screen_start` · `record_screen_stop`

### Files (9)
`list_files` · `file_exists` · `stat_file` · `pull` · `push` · `read_file`
· `write_file` · `make_dir` · `delete_file` — `read_file`/`write_file`/`list_files`
support `as_root` (`su -c …`) for rooted devices (WSA/Magisk).

### Network (11)
`forward_port` · `reverse_port` · `list_forwards` · `list_reverses` · `remove_forward`
· `remove_reverse` · `clear_forwards` · `get_ip_address` · `set_wifi` · `set_mobile_data`
· `set_airplane_mode` — `reverse_port` maps a device port to your PC (local API/CDN shims).

### System (11)
`get_prop` · `set_prop` · `get_setting` · `put_setting` · `list_processes` · `get_meminfo`
· `get_top` · `get_uptime` · `dumpsys` (scoped to a named service) · `list_services`
· `run_shell` (opt-in)

---

## Example: investigate an in-app action

> **Prompt:** *"Find what happens when I send a fleet."*

```
launch_package("com.geargames.homeworld")
capture_screen()                       # observe
tap_element(text="Fleet")              # navigate via the view hierarchy
logcat_start(clear=True)
tap_element(text="Send")               # trigger
logcat_dump(tags=["Unity","libc"])     # structured records
pull("/sdcard/Android/data/com.game/files/save.db", "dumps/save.db")
```

## Local-server / shim workflow

```
reverse_port(device_port=7071, host_port=7071)   # app's localhost:7071 -> your PC shim
reverse_port(device_port=7072, host_port=7072)
launch_package("com.geargames.homeworld")
logcat_filter(tags=["Curl","PlayFab"])
```

---

## Development

```bash
pip install -e ".[dev]"
pytest -q          # device-free smoke tests (imports, registration, parsers)
ruff check .
```

CI runs the same on Python 3.10–3.12.

## Safety

MCP servers execute local commands and can touch files, logs, and devices, so
overly permissive ones become dangerous when an agent chains their tools. adb-mcp is
deliberately scoped:

- **No always-on arbitrary shell.** `run_shell` is the only general-shell tool and it
  is off unless `ADB_MCP_ALLOW_SHELL=1`.
- **Injection-hardened.** `adb shell` concatenates its args through the device's `sh`,
  so every list-form command is `shlex.quote`d in one central place — a payload like
  `"; rm -rf /sdcard"` in a package name or `dumpsys` arg becomes a literal argument,
  never a second command. Covered by tests.
- **Few, guarded mutating tools** — `write_file`, `delete_file` (refuses `/`, `/system`,
  `/data`, …), `clear_app_data`, `uninstall`, `install_apk`, `set_prop`, `put_setting`,
  the `set_*` network toggles.

Point it at a device you own and trust, run one server per intended device (use
`ADB_SERIAL`/`serial`), and leave `ADB_MCP_ALLOW_SHELL` off unless you need it.
See [SECURITY.md](SECURITY.md) for the full model.

## Publishing to PyPI (maintainer)

Releases are published to PyPI by the [`release`](.github/workflows/release.yml)
workflow using **Trusted Publishing** (OIDC) — no API tokens are stored. One-time
setup on PyPI, then every tagged release publishes itself:

1. On PyPI → *Your projects* → *Publishing*, add a **pending trusted publisher**:
   - PyPI project name: `adbmcp`
   - Owner: `FlashZ`, Repository: `adb-mcp`
   - Workflow filename: `release.yml`
   - Environment: `pypi`
2. Cut a release to trigger it:
   ```bash
   git tag v0.1.0 && git push origin v0.1.0
   # or: gh release create v0.1.0 --generate-notes
   ```

The workflow builds the sdist+wheel, runs `twine check`, and uploads.

## License

MIT — see [LICENSE](LICENSE).
