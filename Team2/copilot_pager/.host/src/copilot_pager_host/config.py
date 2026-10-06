"""Private configuration and provisioning helpers."""

import json
import os
import platform
import secrets


def config_dir():
    override = os.environ.get("COPILOT_PAGER_HOME")
    if override:
        return os.path.abspath(os.path.expanduser(override))
    if os.name == "nt":
        root = os.environ.get("APPDATA") or os.path.expanduser("~")
        return os.path.join(root, "Copilot Pager")
    if platform.system() == "Darwin":
        return os.path.expanduser("~/Library/Application Support/copilot-pager")
    root = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(root, "copilot-pager")


def config_path():
    return os.path.join(config_dir(), "config.json")


def ensure_private_dir(path):
    os.makedirs(path, mode=0o700, exist_ok=True)
    if os.name != "nt":
        os.chmod(path, 0o700)


def save_config(value):
    directory = config_dir()
    ensure_private_dir(directory)
    destination = config_path()
    temporary = destination + ".tmp"
    with open(temporary, "w", encoding="utf-8") as output:
        json.dump(value, output, indent=2, sort_keys=True)
        output.write("\n")
    if os.name != "nt":
        os.chmod(temporary, 0o600)
    os.replace(temporary, destination)


def load_config(required=False):
    try:
        with open(config_path(), "r", encoding="utf-8") as source:
            value = json.load(source)
        if not isinstance(value, dict):
            raise ValueError("configuration must be an object")
        return value
    except (OSError, ValueError, TypeError):
        if required:
            raise RuntimeError("Copilot Pager is not paired; run 'copilot-pager pair'")
        return None


def new_config(device_id, key_hex):
    return {
        "version": 1,
        "device_id": device_id,
        "key": key_hex,
        "laptop": platform.node() or "Laptop",
        "ipc_host": "127.0.0.1",
        "ipc_port": 47653,
        "ipc_token": secrets.token_hex(32),
    }


def badge_mount(explicit=None):
    if explicit:
        path = os.path.abspath(os.path.expanduser(explicit))
        if not os.path.isdir(path):
            raise RuntimeError("Badge mount does not exist: %s" % path)
        return path
    username = os.environ.get("USER") or os.environ.get("USERNAME") or ""
    candidates = [
        "/Volumes/BADGER",
        os.path.join("/media", username, "BADGER"),
        os.path.join("/run/media", username, "BADGER"),
        "/mnt/BADGER",
    ]
    if os.name == "nt":
        candidates.extend("%s:\\" % letter for letter in "DEFGHIJKLMNOPQRSTUVWXYZ")
    found = [path for path in candidates if os.path.isdir(os.path.join(path, "system", "apps"))]
    if len(found) != 1:
        raise RuntimeError(
            "Expected one mounted BADGER volume; use --mount when none or several are mounted"
        )
    return found[0]


def provision_badge(mount, config, force=False):
    state_dir = os.path.join(mount, "state")
    os.makedirs(state_dir, exist_ok=True)
    destination = os.path.join(state_dir, "copilot_pager.json")
    if os.path.exists(destination) and not force:
        raise RuntimeError("Badge is already paired; pass --force to replace its pairing")
    value = {
        "version": 1,
        "device_id": config["device_id"],
        "key": config["key"],
        "laptop": config["laptop"],
    }
    temporary = destination + ".tmp"
    with open(temporary, "w", encoding="utf-8") as output:
        json.dump(value, output, separators=(",", ":"))
        output.write("\n")
    os.replace(temporary, destination)
    return destination


def create_pairing(mount, force=False):
    device_id = "pager-" + secrets.token_hex(4)
    value = new_config(device_id, secrets.token_hex(32))
    provision_badge(mount, value, force=force)
    save_config(value)
    return value

