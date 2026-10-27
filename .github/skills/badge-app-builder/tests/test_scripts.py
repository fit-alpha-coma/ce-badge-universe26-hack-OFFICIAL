from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"


def load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPT_DIR / f"{name}.py")
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


scaffold_app = load_script("scaffold_app")
validate_app = load_script("validate_app")
deploy_app = load_script("deploy_app")
validate_submissions = load_script("validate_submissions")


class SkillScriptTests(unittest.TestCase):
    def create_system_font(self, root: Path):
        font = root / "badge" / "assets" / "fonts" / "nope.ppf"
        font.parent.mkdir(parents=True)
        font.write_bytes(b"test-font")

    def test_scaffold_creates_valid_app(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.create_system_font(root)
            apps = root / "badge" / "apps"
            app_dir = scaffold_app.scaffold("demo-app", "Demo App", apps)

            self.assertTrue((app_dir / "__init__.py").is_file())
            self.assertTrue((app_dir / "assets").is_dir())
            self.assertEqual(validate_app.png_info(app_dir / "icon.png")[:2], (24, 24))
            issues = validate_app.validate_app(app_dir, root)
            self.assertFalse([issue for issue in issues if issue.severity == "ERROR"])
            self.assertFalse(
                [issue for issue in issues if "__main__" in issue.message]
            )

    def test_scaffold_accepts_digit_leading_app_name(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.create_system_font(root)
            app_dir = scaffold_app.scaffold(
                "30_minutes", "30 Minutes", root / "badge" / "apps"
            )

            issues = validate_app.validate_app(app_dir, root)

            self.assertFalse([issue for issue in issues if issue.severity == "ERROR"])

    def test_validator_rejects_main_guarded_run(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.create_system_font(root)
            apps = root / "badge" / "apps"
            app_dir = scaffold_app.scaffold("demo-app", "Demo App", apps)
            init_file = app_dir / "__init__.py"
            source = init_file.read_text(encoding="utf-8")
            source = source.replace(
                "run(update)", 'if __name__ == "__main__":\n    run(update)'
            )
            init_file.write_text(source, encoding="utf-8")

            issues = validate_app.validate_app(app_dir, root)

            self.assertTrue(
                any(
                    issue.severity == "ERROR" and "__main__" in issue.message
                    for issue in issues
                )
            )

    def test_validate_requires_module_scope_run(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            app_dir = root / "badge" / "apps" / "missing-run"
            app_dir.mkdir(parents=True)
            (app_dir / "__init__.py").write_text(
                "def update():\n    pass\n", encoding="utf-8"
            )

            issues = validate_app.validate_app(app_dir, root)

            self.assertTrue(
                any(
                    issue.severity == "ERROR"
                    and "Missing module-scope run()" in issue.message
                    for issue in issues
                )
            )

    def test_team_mass_storage_requires_standard_lifecycle(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            app_dir = root / "Team1" / "mass_storage"
            app_dir.mkdir(parents=True)
            (app_dir / "__init__.py").write_text("value = 1\n", encoding="utf-8")

            issues = validate_app.validate_app(app_dir, root)
            messages = {
                issue.message for issue in issues if issue.severity == "ERROR"
            }

            self.assertTrue(
                any("Required update binding is missing" in message for message in messages)
            )
            self.assertTrue(
                any("Missing module-scope run()" in message for message in messages)
            )

    def test_validator_checks_run_arguments(self):
        cases = {
            "missing callback": "run()",
            "wrong callback": "run(other)",
            "unknown keyword": "run(update, extra=True)",
            "duplicate argument": "run(update, 60, fps=30)",
        }
        for name, run_call in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                app_dir = root / "badge" / "apps" / "invalid-run"
                app_dir.mkdir(parents=True)
                (app_dir / "__init__.py").write_text(
                    "def update():\n"
                    "    pass\n"
                    "def other():\n"
                    "    pass\n"
                    f"{run_call}\n",
                    encoding="utf-8",
                )

                issues = validate_app.validate_app(app_dir, root)

                self.assertTrue(
                    any(
                        issue.severity == "ERROR" and "run()" in issue.message
                        for issue in issues
                    )
                )

    def test_validator_accepts_run_lifecycle_arguments(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            app_dir = root / "badge" / "apps" / "valid-run"
            app_dir.mkdir(parents=True)
            (app_dir / "__init__.py").write_text(
                "def init():\n"
                "    pass\n"
                "def update():\n"
                "    pass\n"
                "def on_exit():\n"
                "    pass\n"
                "run(update, fps=30, init=init, on_exit=on_exit)\n",
                encoding="utf-8",
            )

            issues = validate_app.validate_app(app_dir, root)

            self.assertFalse(
                any(
                    issue.severity == "ERROR" and "run()" in issue.message
                    for issue in issues
                )
            )

    def test_scaffold_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            apps = Path(temp)
            scaffold_app.scaffold("demo", "Demo", apps)
            with self.assertRaises(FileExistsError):
                scaffold_app.scaffold("demo", "Demo", apps)

    def test_submission_validator_checks_every_team_app(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.create_system_font(root)
            team = root / "Team1"
            scaffold_app.scaffold("working", "Working", team)
            broken = team / "broken"
            broken.mkdir()
            (broken / "__init__.py").write_text("value = 1\n", encoding="utf-8")

            app_count, error_count, warning_count = (
                validate_submissions.validate_teams([team], root)
            )

            self.assertEqual(app_count, 2)
            self.assertGreater(error_count, 0)
            self.assertGreaterEqual(warning_count, 1)

    def test_submission_validator_allows_empty_team_folder(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            team = root / "Team1"
            team.mkdir()

            result = validate_submissions.validate_teams([team], root)

            self.assertEqual(result, (0, 0, 0))

    def test_submission_validator_ignores_generated_only_folders(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            team = root / "Team1"
            generated = team / "removed-app" / "__pycache__"
            generated.mkdir(parents=True)
            (generated / "__init__.cpython-312.pyc").write_bytes(b"bytecode")

            result = validate_submissions.validate_teams([team], root)

            self.assertEqual(result, (0, 0, 0))

    def test_submission_validator_checks_incomplete_app_folders(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            team = root / "Team1"
            incomplete = team / "incomplete"
            incomplete.mkdir(parents=True)
            (incomplete / "icon.png").write_bytes(b"not-a-png")

            app_count, error_count, _ = validate_submissions.validate_teams(
                [team], root
            )

            self.assertEqual(app_count, 1)
            self.assertGreater(error_count, 0)

    def test_scaffold_escapes_title(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.create_system_font(root)
            app_dir = scaffold_app.scaffold(
                "quoted", 'Mona\'s "Badge"', root / "badge" / "apps"
            )
            issues = validate_app.validate_app(app_dir, root)
            self.assertFalse([issue for issue in issues if issue.severity == "ERROR"])

    def test_validator_requires_update(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            app_dir = root / "badge" / "apps" / "broken"
            app_dir.mkdir(parents=True)
            (app_dir / "__init__.py").write_text("value = 1\n", encoding="utf-8")
            issues = validate_app.validate_app(app_dir, root)
            self.assertTrue(
                any(
                    issue.severity == "ERROR" and "update()" in issue.message
                    for issue in issues
                )
            )

    def test_validator_accepts_imported_update(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            app_dir = root / "badge" / "apps" / "modular"
            app_dir.mkdir(parents=True)
            (app_dir / "__init__.py").write_text(
                "from game import update\nrun(update)\n", encoding="utf-8"
            )
            (app_dir / "game.py").write_text(
                "def update():\n    pass\n", encoding="utf-8"
            )
            issues = validate_app.validate_app(app_dir, root)
            self.assertFalse(
                any(
                    issue.severity == "ERROR" and "update binding" in issue.message
                    for issue in issues
                )
            )

    def test_validator_rejects_required_lifecycle_arguments(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            app_dir = root / "badge" / "apps" / "arguments"
            app_dir.mkdir(parents=True)
            (app_dir / "__init__.py").write_text(
                "def init(required):\n"
                "    pass\n"
                "def update(required, optional=1):\n"
                "    pass\n",
                encoding="utf-8",
            )
            issues = validate_app.validate_app(app_dir, root)
            lifecycle_errors = [
                issue
                for issue in issues
                if issue.severity == "ERROR" and "callable with no arguments" in issue.message
            ]
            self.assertEqual(len(lifecycle_errors), 2)

    def test_png_validation_rejects_header_only_file(self):
        with tempfile.TemporaryDirectory() as temp:
            png = Path(temp) / "broken.png"
            png.write_bytes(
                validate_app.PNG_SIGNATURE
                + b"\x00\x00\x00\rIHDR"
                + b"\x00\x00\x00\x18\x00\x00\x00\x18\x08\x02\x00\x00\x00"
            )
            with self.assertRaises(ValueError):
                validate_app.png_info(png)

    def test_png_validation_rejects_invalid_compressed_data(self):
        with tempfile.TemporaryDirectory() as temp:
            png = Path(temp) / "broken.png"
            ihdr = b"\x00\x00\x00\x18\x00\x00\x00\x18\x08\x02\x00\x00\x00"
            png.write_bytes(
                validate_app.PNG_SIGNATURE
                + scaffold_app.png_chunk(b"IHDR", ihdr)
                + scaffold_app.png_chunk(b"IDAT", b"not-zlib-data")
                + scaffold_app.png_chunk(b"IEND", b"")
            )
            with self.assertRaises(ValueError):
                validate_app.png_info(png)

    def test_png_validation_requires_palette_for_indexed_images(self):
        with tempfile.TemporaryDirectory() as temp:
            png = Path(temp) / "indexed.png"
            ihdr = b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x03\x00\x00\x00"
            png.write_bytes(
                validate_app.PNG_SIGNATURE
                + scaffold_app.png_chunk(b"IHDR", ihdr)
                + scaffold_app.png_chunk(b"IDAT", b"x\x9cc`\x00\x00\x00\x02\x00\x01")
                + scaffold_app.png_chunk(b"IEND", b"")
            )
            with self.assertRaisesRegex(ValueError, "requires PLTE"):
                validate_app.png_info(png)

    def test_validator_rejects_async_and_non_callable_lifecycle(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            app_dir = root / "badge" / "apps" / "invalid-callbacks"
            app_dir.mkdir(parents=True)
            (app_dir / "__init__.py").write_text(
                "async def update():\n"
                "    pass\n"
                "init = 1\n",
                encoding="utf-8",
            )
            issues = validate_app.validate_app(app_dir, root)
            messages = [issue.message for issue in issues if issue.severity == "ERROR"]
            self.assertTrue(any("synchronous" in message for message in messages))
            self.assertTrue(any("non-callable" in message for message in messages))

    def test_validator_warns_on_physical_display_coordinates(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            app_dir = root / "badge" / "apps" / "oversized"
            app_dir.mkdir(parents=True)
            (app_dir / "__init__.py").write_text(
                "SCREEN_WIDTH = 320\n"
                "def update():\n"
                "    return shape.rectangle(0, 0, 320, 240)\n",
                encoding="utf-8",
            )
            issues = validate_app.validate_app(app_dir, root)
            self.assertTrue(
                any("logical" in issue.message for issue in issues)
            )

    def test_deploy_is_dry_run_by_default(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.create_system_font(root)
            app_dir = scaffold_app.scaffold(
                "demo", "Demo", root / "badge" / "apps"
            )
            mount = root / "BADGER"
            (mount / "system" / "apps").mkdir(parents=True)

            destination = deploy_app.deploy(app_dir, mount, False, False, root)
            self.assertFalse(destination.exists())

    def test_deploy_rejects_secrets_hidden_files_and_bytecode(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.create_system_font(root)
            app_dir = scaffold_app.scaffold(
                "demo", "Demo", root / "badge" / "apps"
            )
            (app_dir / "secrets.py").write_text("TOKEN = 'nope'\n", encoding="utf-8")
            (app_dir / ".hidden").write_text("hidden", encoding="utf-8")
            (app_dir / "cache.pyc").write_bytes(b"bytecode")
            mount = root / "BADGER"
            (mount / "system" / "apps").mkdir(parents=True)

            with self.assertRaises(RuntimeError):
                deploy_app.deploy(app_dir, mount, True, False, root)

    def test_validator_rejects_non_png_symlink(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            app_dir = root / "badge" / "apps" / "linked"
            app_dir.mkdir(parents=True)
            (app_dir / "__init__.py").write_text(
                "def update():\n    pass\n", encoding="utf-8"
            )
            outside = root / "outside.json"
            outside.write_text("{}\n", encoding="utf-8")
            (app_dir / "data.json").symlink_to(outside)
            issues = validate_app.validate_app(app_dir, root)
            self.assertTrue(
                any(issue.severity == "ERROR" and "Symlinks" in issue.message for issue in issues)
            )

    def test_validator_ignores_hidden_host_environment(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            app_dir = root / "badge" / "apps" / "companion-app"
            app_dir.mkdir(parents=True)
            (app_dir / "__init__.py").write_text(
                "def update():\n    pass\nrun(update)\n", encoding="utf-8"
            )
            host_package = app_dir / ".host" / ".venv" / "site-packages"
            host_package.mkdir(parents=True)
            (host_package / "desktop_only.py").write_text(
                "import pathlib\nimport subprocess\n", encoding="utf-8"
            )
            (app_dir / ".host" / ".venv" / "python").symlink_to(
                host_package / "desktop_only.py"
            )

            issues = validate_app.validate_app(app_dir, root)

            self.assertFalse(
                any(
                    issue.severity == "ERROR"
                    and (
                        "Desktop-only module" in issue.message
                        or "Symlinks are not safe" in issue.message
                    )
                    for issue in issues
                )
            )

    def test_deploy_writes_and_backs_up_replacement(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.create_system_font(root)
            app_dir = scaffold_app.scaffold(
                "demo", "Demo", root / "badge" / "apps"
            )
            mount = root / "BADGER"
            apps_dir = mount / "system" / "apps"
            existing = apps_dir / "demo"
            existing.mkdir(parents=True)
            (existing / "old.txt").write_text("old", encoding="utf-8")

            destination = deploy_app.deploy(app_dir, mount, True, True, root)

            self.assertTrue((destination / "__init__.py").is_file())
            backups = list((mount / ".badge-app-backups").glob("demo-*"))
            self.assertEqual(len(backups), 1)
            self.assertEqual((backups[0] / "old.txt").read_text(encoding="utf-8"), "old")

    def test_deploy_refuses_reserved_system_apps(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            app_dir = root / "badge" / "apps" / "menu"
            app_dir.mkdir(parents=True)
            (app_dir / "__init__.py").write_text(
                "def update():\n    pass\n", encoding="utf-8"
            )
            mount = root / "BADGER"
            (mount / "system" / "apps").mkdir(parents=True)
            with self.assertRaises(RuntimeError):
                deploy_app.deploy(app_dir, mount, True, True, root)


if __name__ == "__main__":
    unittest.main()
