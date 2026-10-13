from __future__ import annotations

import subprocess
import tempfile
import unittest
from hashlib import sha1
from pathlib import Path
from unittest.mock import patch

from configurator import workspace


class WorkspaceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.root = Path(self.tempdir.name)
        self.project = self.root / "image-project"
        (self.project / "modules").mkdir(parents=True)
        (self.project / "profile.yaml").write_text("name: test\n")

    def test_recognizes_project(self) -> None:
        self.assertTrue(workspace.is_project(self.project))
        self.assertFalse(workspace.is_project(self.root))

    def test_normalizes_git_remote(self) -> None:
        self.assertEqual(
            workspace.normalized_remote(" HTTPS://GitHub.com/WeeCragLinux/kinetic-image-builder.git/ "),
            "https://github.com/weecraglinux/kinetic-image-builder",
        )

    def test_remembers_project_location(self) -> None:
        config_dir = self.root / "config"
        with (
            patch.object(workspace, "CONFIG_ROOT", config_dir),
            patch.object(workspace, "SETTINGS_FILE", config_dir / "settings.json"),
        ):
            workspace.save_checkout(self.project)
            self.assertEqual(workspace.saved_checkout(), self.project.resolve())

    def test_clone_does_not_overwrite_existing_non_project(self) -> None:
        worker = workspace.GitWorker("clone", self.root)
        results: list[tuple[bool, str, str]] = []
        worker.completed.connect(lambda *result: results.append(result))
        with patch.object(workspace, "git_output") as run_git:
            worker.clone()
        run_git.assert_not_called()
        self.assertFalse(results[0][0])

    def test_clone_reuses_existing_project_without_git(self) -> None:
        worker = workspace.GitWorker("clone", self.project)
        results: list[tuple[bool, str, str]] = []
        worker.completed.connect(lambda *result: results.append(result))
        with patch.object(workspace, "git_output") as run_git:
            worker.clone()
        run_git.assert_not_called()
        self.assertTrue(results[0][0])
        self.assertEqual(Path(results[0][2]), self.project)

    def test_clone_runs_git_and_checks_result(self) -> None:
        destination = self.root / "new-project"

        def fake_git(args: list[str], cwd: Path | None = None):
            destination.mkdir()
            (destination / "modules").mkdir()
            (destination / "profile.yaml").write_text("name: test\n")
            return subprocess.CompletedProcess(args, 0, "", "")

        worker = workspace.GitWorker("clone", destination)
        results: list[tuple[bool, str, str]] = []
        worker.completed.connect(lambda *result: results.append(result))
        with patch.object(workspace, "git_output", side_effect=fake_git):
            worker.clone()
        self.assertTrue(results[0][0])
        self.assertEqual(Path(results[0][2]), destination)

    def git(self, args: list[str], cwd: Path | None = None) -> str:
        result = subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True, check=False
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout.strip()

    def make_remote_project(self, name: str) -> tuple[Path, Path, Path]:
        origin = self.root / f"{name}-origin.git"
        checkout = self.root / f"{name}-checkout"
        upstream_worktree = self.root / f"{name}-upstream"

        self.git(["init", "--bare", str(origin)])
        self.git(["init", "-b", "main", str(checkout)])
        self.git(["config", "user.name", "Test User"], cwd=checkout)
        self.git(["config", "user.email", "test@example.com"], cwd=checkout)
        (checkout / "modules").mkdir()
        (checkout / ".gitignore").write_text("ignored-local/\n")
        (checkout / "profile.yaml").write_text(
            "base_image: ghcr.io/example/default\n"
            "enabled_modules:\n"
            "- base\n"
            "- browsers\n"
            "- terra\n"
        )
        (checkout / "modules" / "browsers.yaml").write_text(
            "description: original browser module\npackages:\n"
            "  #- browser-app\n"
            "  - remove-later\n"
        )
        (checkout / "modules" / "terra.yaml").write_text(
            "description: Terra repositories\npackages: []\n"
        )
        (checkout / "template-version.txt").write_text("template v1\n")
        self.git(["add", "."], cwd=checkout)
        self.git(["commit", "-m", "base template"], cwd=checkout)
        self.git(["remote", "add", "origin", str(origin)], cwd=checkout)
        self.git(["push", "-u", "origin", "main"], cwd=checkout)
        self.git(["symbolic-ref", "HEAD", "refs/heads/main"], cwd=origin)

        self.git(["clone", str(origin), str(upstream_worktree)])
        self.git(["config", "user.name", "Upstream"], cwd=upstream_worktree)
        self.git(["config", "user.email", "upstream@example.com"], cwd=upstream_worktree)
        (upstream_worktree / "profile.yaml").write_text(
            "base_image: ghcr.io/example/default\n"
            "enabled_modules:\n"
            "- base\n"
            "- browsers\n"
            "- terra\n"
            "#- new-module\n"
        )
        (upstream_worktree / "modules" / "browsers.yaml").write_text(
            "description: latest upstream browser module\npackages:\n"
            "  #- browser-app\n"
            "  - remove-later\n"
            "  - new-upstream-app\n"
        )
        (upstream_worktree / "modules" / "new-module.yaml").write_text(
            "description: new upstream module\npackages:\n  - new-module-app\n"
        )
        (upstream_worktree / "template-version.txt").write_text("template v2\n")
        (upstream_worktree / "removed-upstream-file.txt").write_text("new file\n")
        self.git(["add", "-A"], cwd=upstream_worktree)
        self.git(["commit", "-m", "upstream template update"], cwd=upstream_worktree)
        self.git(["push"], cwd=upstream_worktree)
        return origin, checkout, upstream_worktree

    def corrupt_git_metadata(self, checkout: Path) -> None:
        broken_oid = sha1(b"a corrupt unreachable object").hexdigest()
        ref = checkout / ".git" / "refs" / "remotes" / "origin" / "main"
        ref.parent.mkdir(parents=True, exist_ok=True)
        ref.write_text(f"{broken_oid}\n")
        object_path = checkout / ".git" / "objects" / broken_oid[:2] / broken_oid[2:]
        object_path.parent.mkdir(parents=True, exist_ok=True)
        object_path.write_bytes(b"")

    def customize_project(self, checkout: Path) -> None:
        (checkout / "profile.yaml").write_text(
            "base_image: ghcr.io/example/nvidia\n"
            "enabled_modules:\n"
            "- base\n"
            "- browsers\n"
            "#- terra\n"
            "- local-module\n"
        )
        browsers = checkout / "modules" / "browsers.yaml"
        browsers.write_text(
            "description: a manual edit that update should replace\npackages:\n"
            "  - browser-app\n"
            "  #- remove-later\n"
            "  - local-only-app\n"
        )
        (checkout / "modules" / "local-module.yaml").write_text(
            "description: local module\npackages:\n  - local-package\n"
        )
        (checkout / "local-only.txt").write_text("local file\n")
        (checkout / "ignored-local").mkdir()
        (checkout / "ignored-local" / "cache.txt").write_text("ignored data\n")

    def run_worker(self, operation: str, checkout: Path, origin: Path):
        results: list[tuple[bool, str, str]] = []
        worker = workspace.GitWorker(operation, checkout)
        worker.completed.connect(lambda *result: results.append(result))
        with patch.object(workspace, "REPOSITORY_URL", str(origin)):
            getattr(worker, operation)()
        self.assertEqual(len(results), 1)
        return results[0]

    def test_update_fresh_clones_and_reapplies_choices_with_broken_git_metadata(self) -> None:
        origin, checkout, upstream_worktree = self.make_remote_project("update")
        self.customize_project(checkout)
        self.corrupt_git_metadata(checkout)
        upstream_oid = self.git(["rev-parse", "HEAD"], cwd=upstream_worktree)

        success, detail, result_path = self.run_worker("update", checkout, origin)

        self.assertTrue(success, detail)
        self.assertEqual(Path(result_path), checkout.resolve())
        self.assertIn("update-backup-", detail)
        profile = (checkout / "profile.yaml").read_text()
        self.assertIn("base_image: ghcr.io/example/nvidia", profile)
        self.assertIn("- browsers", profile)
        self.assertIn("#- terra", profile)
        self.assertIn("#- new-module", profile)
        self.assertNotIn("local-module", profile)
        browsers = (checkout / "modules" / "browsers.yaml").read_text()
        self.assertIn("description: latest upstream browser module", browsers)
        self.assertIn("  - browser-app", browsers)
        self.assertIn("  #- remove-later", browsers)
        self.assertIn("  - new-upstream-app", browsers)
        self.assertNotIn("local-only-app", browsers)
        self.assertEqual((checkout / "template-version.txt").read_text(), "template v2\n")
        self.assertTrue((checkout / "removed-upstream-file.txt").is_file())
        self.assertFalse((checkout / "modules" / "local-module.yaml").exists())
        self.assertFalse((checkout / "local-only.txt").exists())
        self.assertFalse((checkout / "ignored-local").exists())
        self.assertEqual(self.git(["rev-parse", "HEAD"], cwd=checkout), upstream_oid)
        self.assertEqual(
            self.git(["config", "--get", "remote.origin.url"], cwd=checkout), str(origin)
        )

        backup = Path(detail.rsplit("saved at:\n", 1)[1])
        self.assertIn("local-only-app", (backup / "modules" / "browsers.yaml").read_text())
        self.assertTrue((backup / "local-only.txt").is_file())

    def test_reset_fresh_clones_without_reapplying_choices_and_keeps_backup(self) -> None:
        origin, checkout, upstream_worktree = self.make_remote_project("reset")
        self.customize_project(checkout)
        self.corrupt_git_metadata(checkout)
        upstream_oid = self.git(["rev-parse", "HEAD"], cwd=upstream_worktree)

        success, detail, result_path = self.run_worker("reset", checkout, origin)

        self.assertTrue(success, detail)
        self.assertEqual(Path(result_path), checkout.resolve())
        self.assertIn("reset-backup-", detail)
        self.assertEqual(
            (checkout / "profile.yaml").read_text(),
            (upstream_worktree / "profile.yaml").read_text(),
        )
        self.assertEqual(
            (checkout / "modules" / "browsers.yaml").read_text(),
            (upstream_worktree / "modules" / "browsers.yaml").read_text(),
        )
        self.assertFalse((checkout / "local-only.txt").exists())
        self.assertFalse((checkout / "ignored-local").exists())
        self.assertEqual(self.git(["rev-parse", "HEAD"], cwd=checkout), upstream_oid)

        backup = Path(detail.rsplit("saved at:\n", 1)[1])
        self.assertIn("local-only-app", (backup / "modules" / "browsers.yaml").read_text())
        self.assertTrue((backup / "local-only.txt").is_file())


if __name__ == "__main__":
    unittest.main()
