# Copilot Pager

Copilot Pager turns the GitHub Universe 2026 badge into a secure, pocket-sized
approval screen for GitHub Copilot. A permission request pauses on the laptop,
travels over encrypted Bluetooth LE, and shows the exact command, edit, URL, or
tool arguments on the badge. Hold Select to approve once, press Left to deny,
or hold Right to review the native prompt on the laptop.

```text
Copilot CLI / VS Code
          │ permissionRequest hook
          ▼
local hook client ── authenticated localhost IPC ── companion daemon
                                                        ⇅ encrypted BLE
                                                  Universe badge
```

No GitHub token, Wi-Fi credential, command history, or pairing secret is kept
in this repository.

## Controls

| Control | Pending request |
| --- | --- |
| Up / Down | Scroll wrapped code and arguments |
| Right tap | Move to the next detail section |
| Hold Select for 1 second | Approve this invocation once |
| Left or Back | Deny |
| Hold Right for 1 second | Defer to Copilot's normal laptop prompt |
| Home | Return to the badge launcher |

The Menu pad opens a labeled, non-executing sample request from the setup or
idle screen. The case lights chase while a real decision is pending.

## Try it virtually

Open the [Badgeware Web Simulator](https://try.badgewa.re). In its Files panel,
upload these three files from this folder:

- `__init__.py`
- `ble_transport.py`
- `pager_protocol.py`

Open the uploaded `__init__.py` and press **Run** (or F5). Click the virtual
badge once to give it keyboard focus, then use:

| Key | Virtual action |
| --- | --- |
| Space | Open the safe demo; hold to approve |
| Left arrow | Deny |
| Right arrow | Change section; hold to defer |
| Up / Down arrows | Scroll |
| Escape | Home |

The demo is clearly labeled and cannot execute a command. The public simulator
models the older A/B/C controls, so Space stands in for the 2026 Menu control on
the setup screen. It verifies the interface and decision flow, not Bluetooth.

## Install

The badge app uses only the firmware modules. The laptop companion requires
Python 3.11 or newer, Bluetooth, and the dependencies declared in `.host`.

From the repository root:

```sh
python3.11 -m venv Team2/copilot_pager/.host/.venv
Team2/copilot_pager/.host/.venv/bin/pip install -e Team2/copilot_pager/.host

# Put the badge in USB Disk Mode, then preview and deploy the app.
python3 .github/skills/badge-app-builder/scripts/deploy_app.py Team2/copilot_pager
python3 .github/skills/badge-app-builder/scripts/deploy_app.py \
  Team2/copilot_pager --write

# While the BADGER volume is still mounted, provision a fresh 256-bit key.
Team2/copilot_pager/.host/.venv/bin/copilot-pager pair

# Install the user-level Copilot hook without touching repository hooks.
Team2/copilot_pager/.host/.venv/bin/copilot-pager install-hooks
```

On Windows, activate the virtual environment and use `copilot-pager` directly.
If mount discovery is ambiguous, pass `pair --mount /path/to/BADGER`. Re-pairing
requires the explicit `--force` option.

Safely eject and restart the badge, open Copilot Pager, then keep the bridge
running in a terminal:

```sh
copilot-pager serve
```

Start a new Copilot CLI session after installing the hook. In VS Code, select
the **Copilot** session target (Agent Host); it uses the same Copilot SDK hook
contract. Run a harmless sample end to end with:

```sh
copilot-pager doctor
copilot-pager demo
```

Hook failures, an offline badge, or an unavailable daemon return `{}` with a
successful process exit, so Copilot falls back to its native approval prompt.
The bridge waits at most two seconds for an initially offline badge and at most
90 seconds for an active decision.

## What appears on the badge

The 320×240 interface has GitHub Primer-inspired colors and separate Summary,
Command, Changes, Arguments, and Context pages. Requests are limited to 16 KiB.
If the full operation does not fit, approval is disabled and the badge directs
you to the laptop. Sandbox-bypass requests behave the same way because Copilot
requires those escalations to be confirmed locally.

Risk colors are informational. The project never auto-approves requests and
never creates session-wide or permanent tool permissions.

## Security model

- USB provisioning creates a random one-to-one 256-bit key. The laptop copy is
  stored with owner-only permissions; the badge copy lives in `/state`.
- Every BLE message uses ChaCha20-Poly1305 with a fresh nonce. Decisions include
  the device ID, request ID, and payload digest, so stale or modified responses
  are rejected.
- BLE writes use acknowledgements and badge decisions use indications when the
  firmware supports them. Reconnects resend the same request ID and do not
  create a second approval.
- The daemon binds only to `127.0.0.1`; hook clients authenticate with a second
  random token. Payloads and decisions are not persisted or logged.
- One badge pairs to one laptop in v1. Run `pair --force` to replace that trust.

The optional VS Code Local-harness adapter is in
`.host/templates/vscode-local-preview.json`. It is not installed automatically:
the Local hooks feature is Preview and uses a different `PreToolUse` contract.
Its adapter sends only shell, edit, create, and web-fetch tools to the badge and
returns `ask` when Pager defers.

## Checks

The protocol has independent badge and desktop implementations tested against
the RFC 8439 vector and against each other:

```sh
PYTHONPATH=Team2/copilot_pager/.host/src \
  python3.11 -m unittest discover Team2/copilot_pager/.host/tests -v

python3 .github/skills/badge-app-builder/scripts/validate_app.py \
  Team2/copilot_pager
python3 .github/skills/badge-app-builder/scripts/validate_submissions.py Team2
```

The simulator can verify the screens and decision controls using its safe demo,
but it cannot emulate Bluetooth or the dedicated 2026 Menu/Back touch pads.
Before relying on real approvals, test advertising, round trips, reconnects,
range, case lights, and sustained scrolling on a physical 2026 badge.

## Troubleshooting

| Symptom | Resolution |
| --- | --- |
| Pager stays on Pair Your Badge | Pair while the BADGER volume is mounted, safely eject, and restart |
| `doctor` says daemon not running | Start `copilot-pager serve` under the same user account |
| Badge is not found | Open the Pager app, enable laptop Bluetooth, and remove stale OS pairings |
| Copilot immediately shows its laptop prompt | Check the daemon and badge with `doctor`; fallback is intentional |
| Copilot ignores a newly installed hook | Start a new CLI or VS Code Copilot Agent Host session |
| Hook cannot reach the daemon in a sandbox | Allow the Pager config path and localhost IPC in Copilot's sandbox policy |

To remove the integration without touching other Copilot customizations, run
`copilot-pager uninstall-hooks`. Pairing data can then be removed from the
badge's `/state/copilot_pager.json` in USB Disk Mode.
