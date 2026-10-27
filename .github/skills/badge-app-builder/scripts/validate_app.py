#!/usr/bin/env python3
"""Validate a badge app for emulator and physical hardware compatibility."""

from __future__ import annotations

import argparse
import ast
import re
import struct
import sys
import zlib
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
APP_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
RESERVED_APPS = {"menu", "startup"}

# Built-in apps that intentionally have no persistent update()/run() frame
# loop. mass_storage draws a message, calls powman.reset_into_msc(), and reboots.
LIFECYCLE_OPTIONAL_PATHS = {Path("badge/apps/mass_storage")}


# `display` is a legitimate runtime-provided badgeware object (backlight
# control, etc.), inherited from Pimoroni's firmware. It was missing here;
# apps are allowed to `from badgeware import display`.
BADGEWARE_NAMES = {"State", "fatal_error", "display"}

HARDWARE_ONLY_MODULES = {
    "aioble",
    "bluetooth",
    "board",
    "machine",
    "micropython",
    "ntptime",
    "pimoroni",
    "pimoroni_i2c",
    "powman",
    "rp2",
    "st7789",
}

DESKTOP_ONLY_MODULES = {
    "cv2",
    "numpy",
    "pandas",
    "pathlib",
    "PIL",
    "pygame",
    "requests_html",
    "scipy",
    "subprocess",
    "tkinter",
}

SIMULATOR_MOCKS = {"badgeware", "network", "urequest", "urllib", "urandom", "aye_arr"}
LOAD_CALLS = {
    ("image", "load"),
}
LIFECYCLE_NAMES = ("update", "init", "on_exit")
RUN_PARAMETER_NAMES = ("update", "fps", "init", "on_exit")


@dataclass(order=True)
class Issue:
    severity: str
    message: str
    path: Path | None = None
    line: int | None = None

    def render(self, base: Path) -> str:
        location = ""
        if self.path is not None:
            try:
                display_path = self.path.relative_to(base)
            except ValueError:
                display_path = self.path
            location = str(display_path)
            if self.line is not None:
                location += f":{self.line}"
            location += ": "
        return f"{self.severity}: {location}{self.message}"


def png_info(path: Path) -> tuple[int, int, int, int]:
    data = path.read_bytes()
    if not data.startswith(PNG_SIGNATURE):
        raise ValueError("not a PNG file")

    offset = len(PNG_SIGNATURE)
    info = None
    interlace = None
    idat_data = bytearray()
    saw_idat = False
    saw_iend = False
    palette_entries = None
    while offset < len(data):
        if offset + 12 > len(data):
            raise ValueError("truncated PNG chunk")
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        chunk_type = data[offset + 4 : offset + 8]
        chunk_end = offset + 12 + length
        if chunk_end > len(data):
            raise ValueError("truncated PNG chunk data")
        chunk_data = data[offset + 8 : offset + 8 + length]
        expected_crc = struct.unpack(">I", data[offset + 8 + length : chunk_end])[0]
        actual_crc = zlib.crc32(chunk_type + chunk_data) & 0xFFFFFFFF
        if expected_crc != actual_crc:
            raise ValueError(f"invalid {chunk_type.decode(errors='replace')} CRC")

        if info is None:
            if chunk_type != b"IHDR" or length != 13:
                raise ValueError("PNG must begin with a 13-byte IHDR")
            (
                width,
                height,
                bit_depth,
                color_type,
                compression,
                filter_method,
                interlace,
            ) = struct.unpack(">IIBBBBB", chunk_data)
            if width < 1 or height < 1:
                raise ValueError("PNG width and height must be positive")
            if compression != 0 or filter_method != 0 or interlace not in {0, 1}:
                raise ValueError("unsupported PNG compression, filter, or interlace method")
            info = (width, height, bit_depth, color_type)
        elif chunk_type == b"IHDR":
            raise ValueError("duplicate PNG IHDR")

        if chunk_type == b"PLTE":
            if palette_entries is not None:
                raise ValueError("duplicate PNG PLTE")
            if saw_idat:
                raise ValueError("PNG PLTE must appear before IDAT")
            if length < 3 or length > 768 or length % 3 != 0:
                raise ValueError("invalid PNG PLTE length")
            palette_entries = length // 3
        if chunk_type == b"IDAT":
            if info[3] == 3:
                if palette_entries is None:
                    raise ValueError("indexed PNG requires PLTE before IDAT")
                if palette_entries > 2 ** info[2]:
                    raise ValueError("PNG palette has too many entries for bit depth")
            saw_idat = True
            idat_data.extend(chunk_data)
        if chunk_type == b"IEND":
            if length != 0:
                raise ValueError("invalid PNG IEND")
            saw_iend = True
            offset = chunk_end
            break
        offset = chunk_end

    if info is None or not saw_idat or not saw_iend:
        raise ValueError("PNG requires IHDR, IDAT, and IEND chunks")
    if offset != len(data):
        raise ValueError("unexpected data after PNG IEND")
    try:
        scanlines = zlib.decompress(bytes(idat_data))
    except zlib.error as error:
        raise ValueError(f"invalid PNG image data: {error}") from error
    validate_scanlines(scanlines, *info, interlace or 0)
    return info


def validate_scanlines(
    data: bytes,
    width: int,
    height: int,
    bit_depth: int,
    color_type: int,
    interlace: int,
) -> None:
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(color_type)
    valid_depths = {
        0: {1, 2, 4, 8, 16},
        2: {8, 16},
        3: {1, 2, 4, 8},
        4: {8, 16},
        6: {8, 16},
    }
    if channels is None or bit_depth not in valid_depths[color_type]:
        raise ValueError("invalid PNG color type or bit depth")

    passes = [(0, 0, 1, 1)]
    if interlace == 1:
        passes = [
            (0, 0, 8, 8),
            (4, 0, 8, 8),
            (0, 4, 4, 8),
            (2, 0, 4, 4),
            (0, 2, 2, 4),
            (1, 0, 2, 2),
            (0, 1, 1, 2),
        ]

    offset = 0
    for x_start, y_start, x_step, y_step in passes:
        pass_width = (
            0 if width <= x_start else (width - x_start + x_step - 1) // x_step
        )
        pass_height = (
            0 if height <= y_start else (height - y_start + y_step - 1) // y_step
        )
        if pass_width == 0 or pass_height == 0:
            continue
        row_bytes = (pass_width * channels * bit_depth + 7) // 8
        for _ in range(pass_height):
            if offset >= len(data):
                raise ValueError("truncated PNG scanlines")
            if data[offset] > 4:
                raise ValueError("invalid PNG scanline filter")
            offset += 1 + row_bytes
            if offset > len(data):
                raise ValueError("truncated PNG scanline")
    if offset != len(data):
        raise ValueError("unexpected PNG scanline data")


def resolve_app(value: str, repo_root: Path) -> Path:
    candidate = Path(value)
    if candidate.exists():
        return candidate.resolve()
    named = repo_root / "badge" / "apps" / value
    return named.resolve()


def module_root(name: str) -> str:
    return name.split(".", 1)[0]


def local_modules(app_dir: Path) -> set[str]:
    modules = {path.stem for path in app_dir.glob("*.py")}
    modules.update(
        path.name
        for path in app_dir.iterdir()
        if path.is_dir() and not path.name.startswith(".")
    )
    return modules


def included_app_path(path: Path, app_dir: Path) -> bool:
    """Match deployment filtering for generated and app-private directories."""
    relative = path.relative_to(app_dir)
    return not any(
        part.startswith(".") or part == "__pycache__" for part in relative.parts
    )


class AppVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.functions: set[str] = set()
        self.function_nodes: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}
        self.bindings: set[str] = set()
        self.binding_kinds: dict[str, str] = {}
        self.imports: list[tuple[str, int]] = []
        self.badgeware_names: list[tuple[str, int]] = []
        self.asset_paths: list[tuple[str, int]] = []
        self.resolution_warnings: list[tuple[str, int]] = []
        self._depth = 0

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if self._depth == 0:
            self.functions.add(node.name)
            self.function_nodes[node.name] = node
            self.bindings.add(node.name)
            self.binding_kinds[node.name] = "function"
        self._depth += 1
        self.generic_visit(node)
        self._depth -= 1

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if self._depth == 0 and isinstance(node.target, ast.Name):
            self.bindings.add(node.target.id)
            if isinstance(node.value, ast.Lambda):
                kind = "function"
            elif isinstance(node.value, (ast.Name, ast.Attribute)):
                kind = "alias"
            elif isinstance(
                node.value,
                (
                    ast.Constant,
                    ast.Dict,
                    ast.List,
                    ast.Set,
                    ast.Tuple,
                ),
            ):
                kind = "non-callable"
            else:
                kind = "unknown"
            self.binding_kinds[node.target.id] = kind
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        if self._depth == 0:
            self.functions.add(node.name)
            self.function_nodes[node.name] = node
            self.bindings.add(node.name)
            self.binding_kinds[node.name] = "async-function"
        self._depth += 1
        self.generic_visit(node)
        self._depth -= 1

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.imports.append((alias.name, node.lineno))
            if self._depth == 0:
                binding = alias.asname or module_root(alias.name)
                self.bindings.add(binding)
                self.binding_kinds[binding] = "module"

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        self.imports.append((module, node.lineno))
        if self._depth == 0:
            for alias in node.names:
                binding = alias.asname or alias.name
                self.bindings.add(binding)
                self.binding_kinds[binding] = "imported"
        if module == "badgeware":
            self.badgeware_names.extend((alias.name, node.lineno) for alias in node.names)

    def visit_Call(self, node: ast.Call) -> None:
        owner = None
        method = None
        if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
            owner = node.func.value.id
            method = node.func.attr
        elif isinstance(node.func, ast.Name):
            owner = node.func.id

        if (owner, method) in LOAD_CALLS and node.args:
            argument = node.args[0]
            if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                self.asset_paths.append((argument.value, node.lineno))

        if (
            owner in {"shape", "shapes"}
            and method == "rectangle"
            and len(node.args) >= 4
            and all(
                isinstance(argument, ast.Constant)
                and isinstance(argument.value, (int, float))
                for argument in node.args[:4]
            )
        ):
            x, y, width, height = [argument.value for argument in node.args[:4]]
            if x == 0 and y == 0 and (width > 160 or height > 120):
                self.resolution_warnings.append(
                    (
                        f"Full-screen rectangle is {width}x{height}; badge drawing "
                        "coordinates use the 160x120 logical framebuffer.",
                        node.lineno,
                    )
                )
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        if self._depth == 0:
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self.bindings.add(target.id)
                    if isinstance(node.value, ast.Lambda):
                        kind = "function"
                    elif isinstance(node.value, (ast.Name, ast.Attribute)):
                        kind = "alias"
                    elif isinstance(
                        node.value,
                        (ast.Constant, ast.Dict, ast.List, ast.Set, ast.Tuple),
                    ):
                        kind = "non-callable"
                    else:
                        kind = "unknown"
                    self.binding_kinds[target.id] = kind
        if isinstance(node.value, ast.Constant) and isinstance(
            node.value.value, (int, float)
        ):
            for target in node.targets:
                if not isinstance(target, ast.Name):
                    continue
                if target.id in {"SCREEN_WIDTH", "DISPLAY_WIDTH"} and node.value.value > 160:
                    self.resolution_warnings.append(
                        (
                            f"{target.id} is {node.value.value}; app coordinates should "
                            "normally use logical width 160.",
                            node.lineno,
                        )
                    )
                if target.id in {"SCREEN_HEIGHT", "DISPLAY_HEIGHT"} and node.value.value > 120:
                    self.resolution_warnings.append(
                        (
                            f"{target.id} is {node.value.value}; app coordinates should "
                            "normally use logical height 120.",
                            node.lineno,
                        )
                    )
        self.generic_visit(node)


def parse_python(path: Path, issues: list[Issue]) -> tuple[ast.AST | None, AppVisitor | None]:
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (OSError, UnicodeError, SyntaxError) as error:
        line = getattr(error, "lineno", None)
        issues.append(Issue("ERROR", f"Python syntax/read failure: {error}", path, line))
        return None, None

    visitor = AppVisitor()
    visitor.visit(tree)
    return tree, visitor


def required_parameters(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> list[str]:
    positional = [*node.args.posonlyargs, *node.args.args]
    required_count = len(positional) - len(node.args.defaults)
    required = [argument.arg for argument in positional[:required_count]]
    required.extend(
        argument.arg
        for argument, default in zip(node.args.kwonlyargs, node.args.kw_defaults)
        if default is None
    )
    return required


def resolve_asset(asset: str, app_dir: Path, repo_root: Path) -> Path | None:
    if asset.startswith("/system/"):
        return repo_root / "badge" / asset.removeprefix("/system/")
    if asset.startswith("/"):
        return None
    return app_dir / asset


def validate_app(app_dir: Path, repo_root: Path, target: str = "both") -> list[Issue]:
    issues: list[Issue] = []
    if not app_dir.is_dir():
        return [Issue("ERROR", f"App directory does not exist: {app_dir}")]

    lifecycle_optional = any(
        app_dir.resolve() == (repo_root / path).resolve()
        for path in LIFECYCLE_OPTIONAL_PATHS
    )

    if not APP_NAME_RE.fullmatch(app_dir.name):
        issues.append(
            Issue(
                "ERROR",
                "App directory name must start with a lowercase letter or number and "
                "contain only lowercase letters, numbers, hyphens, or underscores.",
                app_dir,
            )
        )

    for path in sorted(app_dir.rglob("*")):
        if not included_app_path(path, app_dir):
            continue
        if path.is_symlink():
            issues.append(
                Issue(
                    "ERROR",
                    "Symlinks are not safe to deploy; copy the file or directory "
                    "into the app.",
                    path,
                )
            )

    entrypoint = app_dir / "__init__.py"
    if not entrypoint.is_file():
        if (app_dir / "__init__.mpy").is_file():
            if target in {"both", "emulator"}:
                issues.append(
                    Issue(
                        "ERROR",
                        "Only __init__.mpy is present; validation and simulator "
                        "testing require source __init__.py.",
                        app_dir,
                    )
                )
        else:
            issues.append(
                Issue(
                    "ERROR",
                    "Missing required __init__.py or __init__.mpy",
                    entrypoint,
                )
            )
            return issues

    icon = app_dir / "icon.png"
    if not icon.is_file():
        issues.append(
            Issue(
                "WARNING",
                "Missing icon.png; the current launcher uses a fallback icon, but "
                "a 24x24 PNG is recommended.",
                app_dir,
            )
        )
    else:
        try:
            width, height, _, _ = png_info(icon)
            if (width, height) != (24, 24):
                issues.append(
                    Issue(
                        "WARNING",
                        f"icon.png is {width}x{height}; new launcher icons should be "
                        "24x24, though the current menu scales other sizes.",
                        icon,
                    )
                )
        except (OSError, ValueError, struct.error) as error:
            issues.append(Issue("ERROR", f"Invalid icon.png: {error}", icon))

    parsed: dict[Path, AppVisitor] = {}
    for python_file in sorted(app_dir.rglob("*.py")):
        if not included_app_path(python_file, app_dir) or python_file.is_symlink():
            continue
        _, visitor = parse_python(python_file, issues)
        if visitor is not None:
            parsed[python_file] = visitor

    entry_visitor = parsed.get(entrypoint)
    if entry_visitor is not None:
        if (
            "update" not in entry_visitor.bindings
            and not lifecycle_optional
        ):
            issues.append(
                Issue(
                    "ERROR",
                    "Required update binding is missing. Define update() or import it "
                    "into __init__.py.",
                    entrypoint,
                )
            )
        for lifecycle_name in LIFECYCLE_NAMES:
            node = entry_visitor.function_nodes.get(lifecycle_name)
            kind = entry_visitor.binding_kinds.get(lifecycle_name)
            if kind == "async-function":
                issues.append(
                    Issue(
                        "ERROR",
                        f"{lifecycle_name}() must be synchronous; the launcher does "
                        "not await coroutine functions.",
                        entrypoint,
                        node.lineno if node is not None else None,
                    )
                )
            elif kind in {"module", "non-callable"}:
                issues.append(
                    Issue(
                        "ERROR",
                        f"{lifecycle_name} is bound as {kind} and cannot be used as "
                        "a launcher callback.",
                        entrypoint,
                    )
                )
            elif kind == "unknown":
                issues.append(
                    Issue(
                        "WARNING",
                        f"Could not prove that {lifecycle_name} is callable; verify "
                        "the assigned value accepts no arguments.",
                        entrypoint,
                    )
                )
            if node is None:
                continue
            required = required_parameters(node)
            if required:
                issues.append(
                    Issue(
                        "ERROR",
                        f"{lifecycle_name}() must be callable with no arguments; "
                        f"required parameter(s): {', '.join(required)}.",
                        entrypoint,
                        node.lineno,
                    )
                )

    locals_ = local_modules(app_dir)
    loaded_pngs: set[Path] = set()
    for python_file, visitor in parsed.items():
        for name, line in visitor.badgeware_names:
            if name == "*":
                issues.append(
                    Issue(
                        "WARNING",
                        "Wildcard badgeware import hides which hardware APIs the app uses.",
                        python_file,
                        line,
                    )
                )
            elif name not in BADGEWARE_NAMES:
                issues.append(
                    Issue(
                        "ERROR",
                        f"'{name}' is a Universe 2025 Badgeware API. Use the Universe "
                        "2026 runtime globals instead.",
                        python_file,
                        line,
                    )
                )

        for imported, line in visitor.imports:
            root = module_root(imported)
            if root in locals_ or root in {"", "__future__"}:
                continue
            if target in {"both", "hardware"} and root in DESKTOP_ONLY_MODULES:
                issues.append(
                    Issue(
                        "ERROR",
                        f"Desktop-only module '{root}' is not available in badge MicroPython.",
                        python_file,
                        line,
                    )
                )
            if target in {"both", "emulator"} and (
                root in HARDWARE_ONLY_MODULES or root.startswith("breakout_")
            ):
                issues.append(
                    Issue(
                        "WARNING",
                        f"'{root}' requires physical hardware and is not modeled by the "
                        "current emulator.",
                        python_file,
                        line,
                    )
                )
            if target == "emulator" and root == "bluetooth":
                issues.append(
                    Issue(
                        "WARNING",
                        "BLE behavior is hardware-only; the current emulator does not "
                        "provide a bluetooth module.",
                        python_file,
                        line,
                    )
                )

        for asset, line in visitor.asset_paths:
            asset_path = resolve_asset(asset, app_dir, repo_root)
            if asset_path is None:
                continue
            asset_path = asset_path.resolve()
            if not asset_path.is_file():
                issues.append(
                    Issue("ERROR", f"Referenced asset does not exist: {asset}", python_file, line)
                )
            elif asset_path.suffix.lower() == ".png":
                loaded_pngs.add(asset_path)

        for message, line in visitor.resolution_warnings:
            issues.append(Issue("WARNING", message, python_file, line))

        if python_file == entrypoint:
            try:
                tree = ast.parse(python_file.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, SyntaxError):
                tree = None
            if isinstance(tree, ast.Module):
                saw_module_scope_run = False
                guarded_run = False
                for statement in tree.body:
                    value = None
                    if isinstance(statement, ast.Expr):
                        value = statement.value
                    elif isinstance(statement, (ast.Assign, ast.AnnAssign)):
                        value = statement.value

                    while isinstance(value, ast.Attribute):
                        value = value.value
                    if (
                        isinstance(value, ast.Call)
                        and isinstance(value.func, ast.Name)
                        and value.func.id == "run"
                    ):
                        saw_module_scope_run = True
                        if (
                            not value.args
                            or not isinstance(value.args[0], ast.Name)
                            or value.args[0].id != "update"
                        ):
                            issues.append(
                                Issue(
                                    "ERROR",
                                    "run() must receive update as its first argument.",
                                    python_file,
                                    value.lineno,
                                )
                            )
                        if len(value.args) > len(RUN_PARAMETER_NAMES):
                            issues.append(
                                Issue(
                                    "ERROR",
                                    "run() accepts at most update, fps, init, and on_exit.",
                                    python_file,
                                    value.lineno,
                                )
                            )
                        positional_names = set(
                            RUN_PARAMETER_NAMES[: len(value.args)]
                        )
                        invalid_keywords = sorted(
                            keyword.arg or "**kwargs"
                            for keyword in value.keywords
                            if keyword.arg not in RUN_PARAMETER_NAMES
                            or keyword.arg in positional_names
                        )
                        if invalid_keywords:
                            issues.append(
                                Issue(
                                    "ERROR",
                                    "run() has unsupported or duplicate argument(s): "
                                    + ", ".join(invalid_keywords),
                                    python_file,
                                    value.lineno,
                                )
                            )

                    if not isinstance(statement, ast.If):
                        continue
                    test = statement.test
                    if not (
                        isinstance(test, ast.Compare)
                        and isinstance(test.left, ast.Name)
                        and test.left.id == "__name__"
                        and len(test.ops) == 1
                        and isinstance(test.ops[0], ast.Eq)
                        and len(test.comparators) == 1
                        and isinstance(test.comparators[0], ast.Constant)
                        and test.comparators[0].value == "__main__"
                    ):
                        continue
                    for guarded in statement.body:
                        if not isinstance(guarded, ast.Expr):
                            continue
                        call = guarded.value
                        if (
                            isinstance(call, ast.Call)
                            and isinstance(call.func, ast.Name)
                            and call.func.id == "run"
                        ):
                            guarded_run = True
                            issues.append(
                                Issue(
                                    "ERROR",
                                    "run() is guarded by if __name__ == '__main__', which is "
                                    "the archived launcher pattern. Call run() at module scope "
                                    "so the 2026 launcher can enter the app on import.",
                                    python_file,
                                    guarded.lineno,
                                )
                            )
                if (
                    not saw_module_scope_run
                    and not guarded_run
                    and not lifecycle_optional
                ):
                    issues.append(
                        Issue(
                            "ERROR",
                            "Missing module-scope run() call. The 2026 launcher imports the "
                            "app and requires it to call run(update) while loading.",
                            entrypoint,
                        )
                    )

    estimated_bytes = 0
    image_count = 0
    for png in sorted(app_dir.rglob("*.png")):
        if not included_app_path(png, app_dir) or png.is_symlink():
            continue
        try:
            width, height, _, color_type = png_info(png)
        except (OSError, ValueError, struct.error) as error:
            issues.append(Issue("ERROR", f"Invalid PNG: {error}", png))
            continue
        if png.resolve() in loaded_pngs:
            image_count += 1
            bytes_per_pixel = 1 if color_type == 3 else 2
            estimated_bytes += width * height * bytes_per_pixel

    if estimated_bytes > 400 * 1024:
        issues.append(
            Issue(
                "WARNING",
                f"{image_count} statically referenced PNGs estimate to "
                f"{estimated_bytes / 1024:.1f} KiB decoded, above the "
                "400 KiB high-risk guideline for RP2350 SRAM. Load assets on "
                "demand and verify memory on hardware.",
                app_dir,
            )
        )
    elif estimated_bytes > 200 * 1024:
        issues.append(
            Issue(
                "WARNING",
                f"{image_count} statically referenced PNGs estimate to "
                f"{estimated_bytes / 1024:.1f} KiB decoded. Profile asset use and "
                "verify memory on hardware.",
                app_dir,
            )
        )

    if (app_dir / "secrets.py").exists():
        issues.append(
            Issue(
                "ERROR",
                "App-local secrets.py risks credential deployment or commits. Use the "
                "badge root secrets.py and never copy credentials implicitly.",
                app_dir / "secrets.py",
            )
        )

    return issues


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("app", help="App name or path")
    parser.add_argument(
        "--target",
        choices=("both", "emulator", "hardware"),
        default="both",
        help="Compatibility target (default: both)",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=REPO_ROOT,
        help="Repository root used to resolve /system paths",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = args.repo_root.resolve()
    app_dir = resolve_app(args.app, repo_root)
    issues = validate_app(app_dir, repo_root, args.target)

    errors = [issue for issue in issues if issue.severity == "ERROR"]
    warnings = [issue for issue in issues if issue.severity == "WARNING"]
    for issue in errors + warnings:
        print(issue.render(repo_root))

    if errors:
        print(f"FAILED: {len(errors)} error(s), {len(warnings)} warning(s)")
        return 1
    print(f"OK: {app_dir} ({len(warnings)} warning(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
