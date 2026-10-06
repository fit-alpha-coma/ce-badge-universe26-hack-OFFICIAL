"""Normalize Copilot CLI and Agent Host permission hook payloads."""

import json
import os
import time
import uuid


MAX_PLAINTEXT = 16 * 1024


def _first(value, *names):
    for name in names:
        if isinstance(value, dict) and value.get(name) is not None:
            return value[name]
    return None


def _object(value):
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
            return decoded if isinstance(decoded, dict) else {"value": decoded}
        except ValueError:
            return {"value": value}
    return {} if value is None else {"value": value}


def _summary(tool, permission, arguments):
    command = _first(arguments, "command", "cmd", "script")
    path = _first(arguments, "path", "filePath", "file_path")
    url = _first(arguments, "url", "uri")
    if command:
        return "Copilot wants to run: %s" % str(command).splitlines()[0][:100]
    if path:
        return "Copilot wants to use %s on %s" % (tool or permission or "a tool", path)
    if url:
        return "Copilot wants to access %s" % url
    return "Copilot requests permission for %s" % (tool or permission or "a tool")


def normalize_hook(payload):
    arguments = _object(
        _first(payload, "toolInput", "tool_input", "toolArgs", "tool_args", "input")
    )
    raw_tool = str(_first(payload, "toolName", "tool_name", "tool") or "tool")
    tool = {
        "Bash": "bash",
        "Read": "view",
        "Write": "create",
        "Edit": "edit",
        "Grep": "grep",
        "Glob": "glob",
        "WebFetch": "web_fetch",
        "WebSearch": "web_search",
    }.get(raw_tool, raw_tool)
    permission = str(_first(payload, "permissionKind", "permission_kind", "kind") or "tool")
    cwd = str(_first(payload, "cwd", "workingDirectory", "working_directory") or "")
    command = _first(arguments, "command", "cmd", "script")
    diff = _first(arguments, "diff", "patch", "edit", "newText", "new_text")
    sandbox_bypass = bool(_first(arguments, "requestSandboxBypass", "request_sandbox_bypass"))
    request = {
        "v": 1,
        "id": str(uuid.uuid4()),
        "source": str(_first(payload, "source", "client") or "copilot"),
        "session_id": str(_first(payload, "sessionId", "session_id") or ""),
        "created_at_ms": int(time.time() * 1000),
        "timeout_ms": 90000,
        "repo": os.path.basename(cwd.rstrip(os.sep)) or "Unknown repository",
        "cwd": cwd,
        "tool_name": tool,
        "permission_kind": permission,
        "summary": _summary(tool, permission, arguments),
        "command": str(command) if command is not None else "",
        "diff": str(diff) if diff is not None else "",
        "arguments": arguments,
        "context": "Requested by GitHub Copilot",
        "allow_remote": not sandbox_bypass,
        "blocked_reason": "Sandbox escape requires laptop confirmation" if sandbox_bypass else "",
        "truncated": False,
    }
    from .protocol import canonical_json, payload_digest

    request["payload_digest"] = payload_digest(request)
    encoded = canonical_json(request)
    if len(encoded) > MAX_PLAINTEXT:
        request["truncated"] = True
        request["allow_remote"] = False
        request["blocked_reason"] = "Payload exceeds the 16 KiB badge limit"
        request["diff"] = request["diff"][:3000]
        request["command"] = request["command"][:3000]
        request["arguments"] = {"preview": json.dumps(arguments, sort_keys=True)[:5000]}
        request["payload_digest"] = payload_digest(request)
    return request


def hook_result(decision):
    if decision == "allow":
        return {"behavior": "allow"}
    if decision == "deny":
        return {
            "behavior": "deny",
            "message": "Denied on Copilot Pager",
            "interrupt": False,
        }
    return {}
