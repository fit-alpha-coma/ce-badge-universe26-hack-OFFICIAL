# Copilot Pager — Monday demo runbook

Run every command from the repository root unless a step says otherwise. Keep
the badge and laptop within one metre for the first physical test.

## Already prepared

- Python 3.12 virtual environment: `.host/.venv`
- Companion and runtime dependencies installed
- User hook installed at `~/.copilot/hooks/copilot-pager.json`
- Bluetooth unblocked, powered, and usable through Bleak
- Local throwaway PoC: `.demo/copilot-pager-poc`

Pairing cannot be completed until the physical badge is mounted.

## Before the 15-minute window

Run the repeatable laptop preflight:

```sh
Team2/copilot_pager/.host/demo/preflight.sh
```

Open two terminals at the repository root. Close any Copilot session that was
started before the hook was installed.

## 15-minute physical test

### 00:00–03:00 — deploy

Put the badge into USB Disk Mode by double-tapping RESET. Preview first:

```sh
python3 .github/skills/badge-app-builder/scripts/deploy_app.py \
  Team2/copilot_pager
```

If the preview lists the four runtime files (`__init__.py`, `ble_transport.py`,
`pager_protocol.py`, `icon.png`) plus `README.md`, deploy it. It must not list
`.host` or `.demo`:

```sh
python3 .github/skills/badge-app-builder/scripts/deploy_app.py \
  Team2/copilot_pager --write
```

If the destination already exists, inspect that error and rerun with
`--replace`; the deployer creates a timestamped backup first.

### 03:00–04:00 — pair

While the BADGER volume is still mounted:

```sh
Team2/copilot_pager/.host/.venv/bin/copilot-pager pair
```

Use `--mount /exact/path/to/BADGER` only when auto-discovery is ambiguous. Use
`--force` only after confirming that an existing badge pairing may be replaced.

### 04:00–06:00 — restart

Safely eject BADGER, press RESET once, and open **Copilot Pager**. It must show
`READY TO CONNECT`; `PAIR YOUR BADGE` means the state file was not provisioned.

### 06:00–10:00 — deterministic BLE tests

Terminal A:

```sh
Team2/copilot_pager/.host/demo/serve.sh
```

Terminal B:

```sh
Team2/copilot_pager/.host/.venv/bin/copilot-pager demo
```

Hold Select for one second. Terminal B must print `Badge decision: allow`.
Run the same command again, press Left, and confirm `Badge decision: deny`.

### 10:00–13:00 — real Copilot hook

In a new terminal:

```sh
cd Team2/copilot_pager/.demo/copilot-pager-poc
copilot
```

Submit exactly:

```text
Run exactly `python3 demo.py`. Do not modify any files or run any other command. Report its stdout.
```

Approve on the badge. The expected command output is:

```text
Copilot Pager: command approved on badge
```

Do not use `--allow-all` or pre-authorize `bash`.

### 13:00–15:00 — evidence

Take one photo or short video showing the pending request and both terminals.
Then run:

```sh
Team2/copilot_pager/.host/.venv/bin/copilot-pager doctor
```

Save the exact output and any badge error message.

## Stop conditions and fallback

- If discovery fails, confirm Bluetooth is on, keep the devices within one
  metre, restart the app and daemon once, and spend at most two minutes on it.
- If the safe `demo` works but Copilot does not invoke the hook, keep the BLE
  result as valid evidence and start one fresh Copilot CLI session.
- If BLE still fails, press Menu in Copilot Pager to show its non-executing
  local sample. State clearly that UI and protocol tests pass but physical BLE
  remains unverified.
- Do not test large diffs, long range, or reconnection behavior in this window.

Success is complete only when allow and deny both return over BLE and the PoC
command runs after badge approval.
