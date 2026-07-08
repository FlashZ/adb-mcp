# Security model

MCP servers execute local commands and can touch files, logs, and connected
devices. Overly permissive servers become dangerous when an agent chains their
tools together, so adb-mcp is deliberately **scoped, not omnipotent**. This
document states exactly what it will and won't do.

## Principles

1. **No always-on arbitrary shell.** There is no general `adb shell <anything>`
   tool by default. A single opt-in escape hatch, `run_shell`, exists only when
   you explicitly set `ADB_MCP_ALLOW_SHELL=1`; otherwise it returns an error and
   runs nothing. Prefer the ~90 specific, named tools.

2. **Every tool is named and idempotent**, returning structured JSON — not raw
   terminal text that an agent has to re-parse and that can smuggle control data.

3. **Device-side shell-injection is neutralized centrally.** `adb shell a b c`
   concatenates its arguments and runs the result through the device's
   `/system/bin/sh`. That means any tool passing a user-controlled string into a
   device command (a package name, a `dumpsys` argument, a settings value) is a
   potential injection point that would *bypass* the `run_shell` gate.

   adb-mcp closes this in one place: `core.shell(...)`/`shell_rc(...)` quote every
   token of a list-form command with `shlex.quote` before handing a single
   command string to `adb shell`. A payload like `"; rm -rf /sdcard"` therefore
   arrives as one literal argument, never as a second command. String-form calls
   (used only for deliberately-composed device shell such as `su -c '…'`) pass
   through verbatim, and every such call site quotes its untrusted substrings.
   This behavior is covered by tests
   (`test_quote_argv_neutralizes_metacharacters`,
   `test_shell_list_mode_sends_single_quoted_command`).

4. **Destructive tools are few, clearly named, and guarded.** The only mutating
   tools are `write_file`, `delete_file`, `clear_app_data`, `uninstall`,
   `install_apk`, `set_prop`, `put_setting`, and the `set_*` network toggles.
   `delete_file` refuses protected roots (`/`, `/system`, `/data`, `/sdcard`,
   `/vendor`, `/product`). Host-side file writes (`pull`, screenshots, recordings,
   bugreports) only go where the caller specifies.

5. **Scope inputs, not just outputs.** `dumpsys` accepts a service *name* only
   (rejecting `/`, `;`, and whitespace); `record_screen_start` validates the
   `size` format; free-form values elsewhere are quoted per principle 3.

## Operating guidance

- Point the server at a **device you own and trust**. adb itself grants broad
  control of a device; this server is a convenience layer over it, not a
  sandbox.
- Leave `ADB_MCP_ALLOW_SHELL` **unset/`0`** unless you specifically need the
  escape hatch, and turn it back off afterwards.
- Run one server per intended device; use `ADB_SERIAL` / the `serial` arg so a
  tool call can't accidentally target the wrong device when several are attached.
- Treat the agent driving this server as you would any operator with a USB cable
  and `adb` — the tools are safe from injection, but they still *do real things*
  to the device.

## Reporting

Found a way to escape the intended scope (e.g. a tool that lets an argument
become a second device command, or a destructive action without its guard)?
Please open an issue describing the tool, the input, and the observed effect.
