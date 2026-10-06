"""Command-line interface and Copilot hook entrypoint."""

import argparse
import asyncio
import json
import os
import secrets
import sys

from .config import (
    badge_mount,
    config_dir,
    create_pairing,
    load_config,
)
from .ipc import request_sync, run_server
from .normalize import hook_result, normalize_hook
from .protocol import payload_digest


HOOK_FILENAME = "copilot-pager.json"


def copilot_home():
    return os.path.abspath(
        os.path.expanduser(os.environ.get("COPILOT_HOME") or "~/.copilot")
    )


def hook_path():
    return os.path.join(copilot_home(), "hooks", HOOK_FILENAME)


def hook_document():
    return {
        "version": 1,
        "hooks": {
            "permissionRequest": [
                {
                    "type": "command",
                    "exec": sys.executable,
                    "args": ["-m", "copilot_pager_host.cli", "hook"],
                    "timeoutSec": 95,
                }
            ]
        },
    }


def write_private_json(path, value):
    directory = os.path.dirname(path)
    os.makedirs(directory, mode=0o700, exist_ok=True)
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as output:
        json.dump(value, output, indent=2, sort_keys=True)
        output.write("\n")
    if os.name != "nt":
        os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def command_pair(args):
    mount = badge_mount(args.mount)
    value = create_pairing(mount, force=args.force)
    print("Paired %s with %s" % (value["device_id"], value["laptop"]))
    print("Pairing saved to %s/state/copilot_pager.json" % mount)
    print("Safely eject the badge and restart it, then run: copilot-pager serve")
    return 0


def command_install(_args):
    destination = hook_path()
    write_private_json(destination, hook_document())
    print("Installed the user-level Copilot hook at %s" % destination)
    print("It applies to Copilot CLI and VS Code Copilot Agent Host sessions.")
    return 0


def command_uninstall(_args):
    destination = hook_path()
    try:
        os.remove(destination)
        print("Removed %s" % destination)
    except FileNotFoundError:
        print("Copilot Pager hook was not installed")
    return 0


def command_hook(_args):
    # stdout is exclusively the hook decision JSON. Diagnostics go to stderr.
    try:
        raw = sys.stdin.buffer.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise RuntimeError("hook payload exceeds 1 MiB")
        payload = json.loads(raw.decode("utf-8"))
        request = normalize_hook(payload)
        config = load_config(required=True)
        response = request_sync(config, "request", request, timeout=92.0)
        decision = response.get("decision", "defer")
        print(json.dumps(hook_result(decision), separators=(",", ":")))
    except Exception as error:
        print("Copilot Pager fallback: %s" % error, file=sys.stderr)
        print("{}")
    return 0


def command_hook_local(_args):
    """Preview adapter for VS Code's extension-host Local harness."""
    try:
        raw = sys.stdin.buffer.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise RuntimeError("hook payload exceeds 1 MiB")
        payload = json.loads(raw.decode("utf-8"))
        side_effecting = ("bash", "powershell", "edit", "create", "web_fetch")
        request = normalize_hook(payload)
        if request["tool_name"] not in side_effecting:
            print("{}")
            return 0
        config = load_config(required=True)
        decision = request_sync(config, "request", request, timeout=92.0).get(
            "decision", "defer"
        )
        local_decision = {"allow": "allow", "deny": "deny", "defer": "ask"}[decision]
        output = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": local_decision,
                "permissionDecisionReason": "Reviewed with Copilot Pager",
            }
        }
        print(json.dumps(output, separators=(",", ":")))
    except Exception as error:
        print("Copilot Pager local fallback: %s" % error, file=sys.stderr)
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "ask",
                        "permissionDecisionReason": "Copilot Pager unavailable; review locally",
                    }
                },
                separators=(",", ":"),
            )
        )
    return 0


def demo_request():
    value = {
        "v": 1,
        "id": "demo-" + secrets.token_hex(8),
        "source": "DEMO",
        "session_id": "demo",
        "repo": "octocat/hello-world",
        "tool_name": "bash",
        "permission_kind": "commands",
        "summary": "Copilot wants to run the project test suite",
        "command": "npm test -- --runInBand",
        "diff": "- const status = 'pending';\n+ const status = 'verified';",
        "arguments": {"cwd": "/workspace/hello-world"},
        "context": "Safe demonstration: no command will be executed.",
        "allow_remote": True,
        "truncated": False,
        "timeout_ms": 90000,
        "demo": True,
    }
    value["payload_digest"] = payload_digest(value)
    return value


def command_demo(_args):
    try:
        config = load_config(required=True)
        response = request_sync(config, "demo", demo_request(), timeout=92.0)
        print("Badge decision: %s (demo only; nothing executed)" % response["decision"])
        return 0
    except Exception as error:
        print("Demo failed: %s" % error, file=sys.stderr)
        return 1


def command_doctor(_args):
    failures = 0
    print("Python: %s" % sys.version.split()[0])
    if sys.version_info < (3, 11):
        print("  FAIL: Python 3.11 or newer is required")
        failures += 1
    else:
        print("  PASS")
    config = load_config()
    print("Pairing: %s" % ("PASS (%s)" % config["device_id"] if config else "FAIL"))
    failures += 0 if config else 1
    print("Hook: %s" % ("PASS" if os.path.isfile(hook_path()) else "NOT INSTALLED"))
    if config:
        try:
            status = request_sync(config, "status", timeout=1.5)["status"]
            print("Daemon: PASS (badge %s)" % ("connected" if status["connected"] else "disconnected"))
        except Exception as error:
            print("Daemon: NOT RUNNING (%s)" % error)
    print("Private config: %s" % config_dir())
    return 1 if failures else 0


def command_serve(_args):
    try:
        from .bridge import PagerBridge

        config = load_config(required=True)
        bridge = PagerBridge(config)
        print(
            "Copilot Pager daemon listening on %s:%s for %s"
            % (config["ipc_host"], config["ipc_port"], config["device_id"])
        )
        asyncio.run(run_server(bridge, config))
        return 0
    except KeyboardInterrupt:
        print("\nCopilot Pager stopped")
        return 0
    except Exception as error:
        print("Daemon failed: %s" % error, file=sys.stderr)
        return 1


def build_parser():
    parser = argparse.ArgumentParser(prog="copilot-pager", description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    pair = subparsers.add_parser("pair", help="provision a mounted badge over USB")
    pair.add_argument("--mount", help="path to the mounted BADGER volume")
    pair.add_argument("--force", action="store_true", help="replace existing pairing")
    pair.set_defaults(handler=command_pair)

    subparsers.add_parser("serve", help="run the persistent BLE bridge").set_defaults(
        handler=command_serve
    )
    subparsers.add_parser("install-hooks", help="install the user-level Copilot hook").set_defaults(
        handler=command_install
    )
    subparsers.add_parser("uninstall-hooks", help="remove only the Pager hook").set_defaults(
        handler=command_uninstall
    )
    subparsers.add_parser("doctor", help="check pairing, hook, and daemon status").set_defaults(
        handler=command_doctor
    )
    subparsers.add_parser("demo", help="send a safe sample request to the badge").set_defaults(
        handler=command_demo
    )
    subparsers.add_parser("hook", help="internal Copilot permission hook").set_defaults(
        handler=command_hook
    )
    subparsers.add_parser(
        "hook-local", help="Preview adapter for VS Code Local hooks"
    ).set_defaults(
        handler=command_hook_local
    )
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
