# Native/WSL Operator Runbook

This runbook keeps Obsidian-Otto operator work on one safe command surface:

- Exactly one OpenClaw runtime owns Telegram at a time.
- WSL OpenClaw can run either as a loopback shadow gateway or as the promoted live owner on port `18790`.
- Both surfaces use the same Otto-managed QMD source set and OpenClaw cron/heartbeat contracts.
- WSL shadow may use `auth none` only on local loopback for shadow testing.
- WSL live must not be promoted while Windows OpenClaw is still running.

## Daily Operator Commands

Use the desktop shortcut `Obsidian-Otto Operator` or run:

```bat
otto.bat advanced
```

Useful direct commands:

```bat
otto.bat operator-status
otto.bat operator-doctor
otto.bat operator-update
otto.bat wsl-live-preflight
otto.bat wsl-live-promote --dry-run
otto.bat wsl-live-promote --write
otto.bat wsl-live-status
otto.bat wsl-live-rollback --write
otto.bat wsl-gateway-start
otto.bat wsl-gateway-stop
otto.bat wsl-gateway-restart
otto.bat native-fallback
otto.bat docker-up
otto.bat docker-probe
```

## Startup Shortcut

Install desktop shortcuts and the login startup task:

```bat
scripts\shell\install-operator-shortcuts.bat
```

The startup task runs:

```bat
otto.bat wsl-gateway-start
```

This makes WSL gateway startup automatic after Windows login. The launcher now starts the current WSL config that is already installed:

- shadow config if the repo is still in `S2C_WSL_SHADOW_GATEWAY_READY`
- live config if the repo has already been promoted to `S4_WSL_LIVE`

Startup no longer performs an implicit Telegram cutover. Promotion and rollback are explicit commands.

To uninstall:

```bat
scripts\shell\install-operator-shortcuts.bat -Uninstall
```

## Health And Parity

`operator-status` writes:

```text
state/operator/openclaw_runtime.json
```

It checks:

- native and WSL configs both use QMD backend
- QMD source paths match after Windows/WSL path normalization
- WSL uses `/usr/bin/qmd`
- WSL can see `/mnt/c/Users/joshu/Obsidian-Otto`
- WSL can see `/mnt/c/Users/joshu/Josh Obsidian`
- exactly one Telegram owner is active
- WSL Telegram can be the active owner only after `S4_WSL_LIVE`
- cron contract exists and uses expected timezone
- creative heartbeat manifest exists
- WSL gateway probe status is recorded

`operator-doctor` runs the existing OpenClaw sync path and then reports parity. Use it when config drift appears.

`operator-update` regenerates OpenClaw tool manifest, context pack, QMD manifest, syncs config, and records operator status.

If WSL cannot see `/mnt/c`, the operator status fails closed. The gateway can still be started from Ubuntu home after copying the shadow config into `~/.openclaw/openclaw.json`, but QMD/Vault parity is not considered green until the Windows mount is visible again.

## WSL Live Promote

Run preflight first:

```bat
otto.bat wsl-live-preflight
```

Then inspect the dry run:

```bat
otto.bat wsl-live-promote --dry-run
```

Then write the live promote only after Windows OpenClaw is stopped:

```bat
otto.bat wsl-live-promote --write
```

This flow:

- keeps QMD native in Ubuntu WSL at `/usr/bin/qmd`
- keeps OpenClaw native in Ubuntu WSL
- links the Otto bridge by CLI install, not config invention
- writes a sanitized preview to `state/openclaw/ubuntu-live/openclaw.json.preview`
- updates `state/runtime/owner.json` and `state/runtime/single_owner_lock.json`

Bridge note:

- preferred WSL link flow: mirror the plugin into `/home/joshu/.openclaw/plugins-local/obsidian-otto-bridge`, then run `openclaw plugins install -l /home/joshu/.openclaw/plugins-local/obsidian-otto-bridge`
- direct `/mnt/c/.../openclaw-otto-bridge` linking may be treated as world-writable and blocked by OpenClaw
- if your OpenClaw build rejects `--force` with `--link`, plain link install is the correct fallback and is retried automatically by the migration flow

After promote, start the gateway explicitly:

```bat
otto.bat wsl-gateway-start
```

Or from WSL:

```bash
openclaw gateway run --port 18790
```

## Fallback Rule

If WSL fails:

```bat
otto.bat native-fallback
```

This restarts/probes native Windows OpenClaw and records:

```text
state/openclaw/native_fallback_last.json
```

If the repo is already in `S4_WSL_LIVE`, `native-fallback` first performs the explicit WSL rollback state write, then restarts/probes native OpenClaw.

## Safety Boundary

Do not let Windows and WSL both own Telegram. The intended split is:

- WSL Ubuntu shadow: loopback gateway with Telegram disabled.
- WSL Ubuntu live: preferred local gateway, QMD/cron parity, Telegram owner when healthy.
- Native Windows: rollback/fallback owner when WSL fails or before WSL live promote.
