from __future__ import annotations

import subprocess
import tempfile
import unittest
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

    def test_update_syncs_upstream_entries_while_preserving_local_choices(self) -> None:
        origin = self.root / "origin.git"
        checkout = self.root / "checkout"
        upstream_worktree = self.root / "upstream-worktree"

        def run_git(args: list[str], cwd: Path | None = None) -> str:
            result = subprocess.run(
                ["git", *args], cwd=cwd, capture_output=True, text=True, check=False
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            return result.stdout.strip()

        run_git(["init", "--bare", str(origin)])
        run_git(["init", "-b", "main", str(checkout)])
        run_git(["config", "user.name", "Test User"], cwd=checkout)
        run_git(["config", "user.email", "test@example.com"], cwd=checkout)
        (checkout / "modules").mkdir()
        (checkout / "profile.yaml").write_text(
            "enabled_modules:\n- base\n- apps\n- obsolete\n"
        )
        (checkout / "modules" / "apps.yaml").write_text(
            "description: apps\npackages:\n"
            "  - stay\n"
            "  - removed-upstream\n"
            "  - user-toggled\n"
        )
        (checkout / "modules" / "obsolete.yaml").write_text(
            "description: obsolete\npackages: []\n"
        )
        run_git(["add", "."], cwd=checkout)
        run_git(["commit", "-m", "base template"], cwd=checkout)
        initial_oid = run_git(["rev-parse", "HEAD"], cwd=checkout)
        run_git(["remote", "add", "origin", str(origin)], cwd=checkout)
        run_git(["push", "-u", "origin", "main"], cwd=checkout)
        run_git(
            ["symbolic-ref", "HEAD", "refs/heads/main"], cwd=origin
        )

        # These are the configurator's local choices and must survive the sync.
        (checkout / "profile.yaml").write_text(
            "enabled_modules:\n- base\n#- apps\n- obsolete\n"
        )
        apps_path = checkout / "modules" / "apps.yaml"
        apps_path.write_text(
            apps_path.read_text().replace("  - user-toggled\n", "  #- user-toggled\n")
        )

        run_git(["clone", str(origin), str(upstream_worktree)])
        run_git(["config", "user.name", "Upstream"], cwd=upstream_worktree)
        run_git(["config", "user.email", "upstream@example.com"], cwd=upstream_worktree)
        (upstream_worktree / "profile.yaml").write_text(
            "enabled_modules:\n- base\n- apps\n#- new-module\n"
        )
        upstream_apps = upstream_worktree / "modules" / "apps.yaml"
        upstream_apps.write_text(
            "description: upstream description change\npackages:\n"
            "  - stay # upstream changed an existing entry\n"
            "  - new-app\n"
        )
        (upstream_worktree / "modules" / "obsolete.yaml").unlink()
        (upstream_worktree / "modules" / "new-module.yaml").write_text(
            "description: new module\npackages:\n  - new-module-app\n"
        )
        run_git(["add", "-A"], cwd=upstream_worktree)
        run_git(["commit", "-m", "update template entries"], cwd=upstream_worktree)
        run_git(["push"], cwd=upstream_worktree)
        upstream_oid = run_git(["rev-parse", "HEAD"], cwd=upstream_worktree)

        results: list[tuple[bool, str, str]] = []
        worker = workspace.GitWorker("update", checkout)
        worker.completed.connect(lambda *result: results.append(result))
        with patch.object(workspace, "is_our_checkout", return_value=True):
            worker.update()

        self.assertTrue(results[0][0], results[0][1])
        profile = (checkout / "profile.yaml").read_text()
        self.assertIn("#- apps", profile)
        self.assertIn("#- new-module", profile)
        self.assertNotIn("obsolete", profile)
        apps = apps_path.read_text()
        self.assertIn("  - stay\n", apps)
        self.assertNotIn("upstream changed an existing entry", apps)
        self.assertIn("  - new-app", apps)
        self.assertIn("  #- user-toggled", apps)
        self.assertNotIn("removed-upstream", apps)
        self.assertFalse((checkout / "modules" / "obsolete.yaml").exists())
        self.assertTrue((checkout / "modules" / "new-module.yaml").exists())
        self.assertEqual(
            run_git(["rev-parse", workspace.TEMPLATE_BASE_REF], cwd=checkout),
            upstream_oid,
        )
        self.assertEqual(run_git(["rev-parse", "HEAD"], cwd=checkout), initial_oid)

    def test_reset_restores_fresh_upstream_tree_and_saves_backup(self) -> None:
        origin = self.root / "reset-origin.git"
        checkout = self.root / "reset-checkout"
        upstream_worktree = self.root / "reset-upstream"

        def run_git(args: list[str], cwd: Path | None = None) -> str:
            result = subprocess.run(
                ["git", *args], cwd=cwd, capture_output=True, text=True, check=False
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            return result.stdout.strip()

        run_git(["init", "--bare", str(origin)])
        run_git(["init", "-b", "main", str(checkout)])
        run_git(["config", "user.name", "Test User"], cwd=checkout)
        run_git(["config", "user.email", "test@example.com"], cwd=checkout)
        (checkout / "modules").mkdir()
        (checkout / ".gitignore").write_text("ignored-local/\n")
        (checkout / "profile.yaml").write_text("base_image: original\nenabled_modules:\n- base\n")
        (checkout / "modules" / "base.yaml").write_text("description: base\npackages: []\n")
        run_git(["add", "."], cwd=checkout)
        run_git(["commit", "-m", "base template"], cwd=checkout)
        run_git(["remote", "add", "origin", str(origin)], cwd=checkout)
        run_git(["push", "-u", "origin", "main"], cwd=checkout)
        run_git(["symbolic-ref", "HEAD", "refs/heads/main"], cwd=origin)

        run_git(["clone", str(origin), str(upstream_worktree)])
        run_git(["config", "user.name", "Upstream"], cwd=upstream_worktree)
        run_git(["config", "user.email", "upstream@example.com"], cwd=upstream_worktree)
        (upstream_worktree / "profile.yaml").write_text(
            "base_image: upstream\nenabled_modules:\n- base\n"
        )
        run_git(["add", "profile.yaml"], cwd=upstream_worktree)
        run_git(["commit", "-m", "upstream base"], cwd=upstream_worktree)
        run_git(["push"], cwd=upstream_worktree)

        (checkout / "profile.yaml").write_text("base_image: local\nenabled_modules:\n- custom\n")
        (checkout / "local-only.txt").write_text("keep in backup\n")
        (checkout / "ignored-local").mkdir()
        (checkout / "ignored-local" / "cache.txt").write_text("ignored data\n")

        results: list[tuple[bool, str, str]] = []
        worker = workspace.GitWorker("reset", checkout)
        worker.completed.connect(lambda *result: results.append(result))
        with patch.object(workspace, "is_our_checkout", return_value=True):
            worker.reset()

        self.assertTrue(results[0][0], results[0][1])
        self.assertIn("reset-backup-", results[0][1])
        self.assertEqual(
            (checkout / "profile.yaml").read_text(),
            "base_image: upstream\nenabled_modules:\n- base\n",
        )
        self.assertFalse((checkout / "local-only.txt").exists())
        self.assertFalse((checkout / "ignored-local").exists())
        self.assertEqual(run_git(["status", "--porcelain"], cwd=checkout), "")
        backup = Path(results[0][1].split("saved at:\n", 1)[1])
        self.assertEqual(
            (backup / "profile.yaml").read_text(),
            "base_image: local\nenabled_modules:\n- custom\n",
        )
        self.assertTrue((backup / "local-only.txt").exists())
        self.assertTrue((backup / "ignored-local" / "cache.txt").exists())


if __name__ == "__main__":
    unittest.main()
