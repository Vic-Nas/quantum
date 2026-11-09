import os
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "commit_data.sh"


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
                          env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
                               "GIT_COMMITTER_EMAIL": "t@t", "GIT_CONFIG_GLOBAL": "/dev/null"}).stdout


class CommitScript(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.origin = self.root / "origin.git"
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(self.origin)], check=True)
        self.work = self.root / "work"
        git(self.root, "clone", "-q", str(self.origin), "work")
        (self.work / "data").mkdir()
        (self.work / "data" / "status.json").write_text('{\n "run_at": "old"\n}\n')
        (self.work / "README.md").write_text("readme\n")
        git(self.work, "add", "-A")
        git(self.work, "commit", "-q", "-m", "base")
        git(self.work, "push", "-q", "origin", "HEAD:main")
        # a second clone plays the person pushing while a run is in flight
        git(self.root, "clone", "-q", str(self.origin), "other")
        self.other = self.root / "other"
        self.out = self.root / "out.txt"
        self.out.write_text("")

    def run_script(self):
        return subprocess.run(["bash", str(SCRIPT)], cwd=self.work, capture_output=True, text=True,
                              env={**os.environ, "GITHUB_OUTPUT": str(self.out), "GITHUB_REF_NAME": "main",
                                   "GIT_CONFIG_GLOBAL": "/dev/null"})

    def test_no_changes(self):
        r = self.run_script()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("changed=false", self.out.read_text())

    def test_clean_change_is_pushed(self):
        (self.work / "data" / "status.json").write_text('{\n "run_at": "new"\n}\n')
        r = self.run_script()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("changed=true", self.out.read_text())
        self.assertIn("new", git(self.root, "--git-dir", str(self.origin), "show", "main:data/status.json"))

    def test_conflict_keeps_the_branch_and_leaves_no_markers(self):
        # someone pushes a change to the same file first
        (self.other / "data" / "status.json").write_text('{\n "run_at": "human"\n}\n')
        git(self.other, "commit", "-qam", "human edit")
        git(self.other, "push", "-q", "origin", "HEAD:main")
        (self.work / "data" / "status.json").write_text('{\n "run_at": "bot"\n}\n')
        r = self.run_script()
        self.assertEqual(r.returncode, 0, r.stderr)  # not red: the next run redoes the work
        self.assertIn("changed=false", self.out.read_text())
        text = (self.work / "data" / "status.json").read_text()
        self.assertNotIn("<<<<<<<", text)
        self.assertIn("human", text)  # the branch's version wins
        import json
        json.loads(text)  # still valid JSON
        self.assertEqual(git(self.work, "status", "--porcelain").strip(), "")  # no half-finished rebase or stray changes
        self.assertIn("human", git(self.root, "--git-dir", str(self.origin), "show", "main:data/status.json"))  # nothing pushed over it


if __name__ == "__main__":
    unittest.main()


DEPLOY = Path(__file__).resolve().parents[1] / "scripts" / "should_deploy.sh"


class ShouldDeploy(unittest.TestCase):
    def setUp(self):
        self.repo = Path(tempfile.mkdtemp())
        git(self.repo, "init", "-q", "-b", "main")
        (self.repo / "a").write_text("a")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "x")
        self.head = git(self.repo, "rev-parse", "HEAD").strip()

    def decide(self, mode, changed, live=None):
        out = self.repo / "out.txt"
        out.write_text("")
        env = {**os.environ, "GITHUB_OUTPUT": str(out), "GIT_CONFIG_GLOBAL": "/dev/null"}
        env.pop("QTD_SITE_URL", None)
        if live is not None:
            env["QTD_LIVE_STAMP"] = live
        subprocess.run(["bash", str(DEPLOY), mode, changed], cwd=self.repo, check=True, capture_output=True, env=env)
        return out.read_text().strip()

    def test_daily_and_push_runs_always_publish(self):
        self.assertEqual(self.decide("run", "false", self.head), "deploy=true")
        self.assertEqual(self.decide("none", "false", self.head), "deploy=true")

    def test_frequent_run_publishes_when_data_changed(self):
        self.assertEqual(self.decide("retry", "true", self.head), "deploy=true")

    def test_frequent_run_skips_when_live_site_is_current(self):
        self.assertEqual(self.decide("retry", "false", self.head), "deploy=false")

    def test_frequent_run_heals_a_stale_or_unreadable_live_site(self):
        self.assertEqual(self.decide("retry", "false", "0" * 40), "deploy=true")
        self.assertEqual(self.decide("retry", "false", ""), "deploy=true")
        self.assertEqual(self.decide("retry", "false"), "deploy=true")
