#!/usr/bin/env python3
"""Smoke-test the feature bootstrap workflow contract."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def _usage() -> str:
    """Return the usage text for the specify smoke test."""
    return (
        "Usage:\n"
        "  .specify/scripts/test_specify.py\n\n"
        "What it checks:\n"
        "  1. create-new-feature.py still creates a branch/spec pair in a writeable temp repo.\n"
        "  2. create-new-feature.py reports a permission-specific error when git metadata is not writable.\n"
    )


def _init_git_repo(repo_dir: Path) -> None:
    """Create a lightweight git repo for the smoke test."""
    subprocess.run(["git", "init", "-q"], cwd=repo_dir, check=True)


def _run_create_feature(repo_dir: Path, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    """Run the feature bootstrap entrypoint with the requested arguments."""
    script = Path(__file__).resolve().parents[1] / "scripts" / "python" / "create_new_feature.py"
    return subprocess.run(
        [sys.executable, str(script), *args],
        cwd=repo_dir,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


def _write_spec_template(repo_dir: Path) -> None:
    """Seed the minimal spec template required by the bootstrap flow."""
    template_dir = repo_dir / ".specify" / "templates"
    template_dir.mkdir(parents=True, exist_ok=True)
    (template_dir / "spec-template.md").write_text(
        "# [FEATURE_NAME]\n\n## Summary\n\n[SUMMARY]\n",
        encoding="utf-8",
    )


def _verify_success_payload(success_output: str, test_dir: Path) -> None:
    """Assert the success payload created the expected branch/spec pair."""
    payload = json.loads(success_output)
    branch_name = payload["BRANCH_NAME"]
    spec_file = Path(payload["SPEC_FILE"]).resolve()

    if not branch_name.endswith("smoke-test"):
        raise SystemExit(f"Unexpected branch name: {branch_name}")
    if not spec_file.exists():
        raise SystemExit(f"Spec file was not created: {spec_file}")

    expected_spec = (test_dir / "specs" / branch_name / "spec.md").resolve()
    if spec_file != expected_spec:
        raise SystemExit(f"Unexpected spec path: {spec_file} != {expected_spec}")


def _write_fake_git(fake_bin: Path, real_git: Path) -> None:
    """Create a fake git wrapper that denies branch creation."""
    fake_bin.mkdir(parents=True, exist_ok=True)
    wrapper = fake_bin / "git"
    wrapper.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "from __future__ import annotations",
                "",
                "import os",
                "import subprocess",
                "import sys",
                "",
                "real_git = os.environ['REAL_GIT']",
                "args = sys.argv[1:]",
                "if len(args) >= 3 and args[0] == 'switch' and args[1] == '-c':",
                "    print(\"fatal: cannot lock ref 'refs/heads/test-branch': Permission denied\", file=sys.stderr)",
                "    raise SystemExit(1)",
                "raise SystemExit(subprocess.run([real_git, *args], check=False).returncode)",
                "",
            ]
        ),
        encoding="utf-8",
    )
    wrapper.chmod(0o755)


def main(argv: list[str]) -> int:
    """Run the specify smoke test."""
    for arg in argv:
        if arg in {"--help", "-h"}:
            print(_usage())
            return 0
        print(_usage(), file=sys.stderr)
        return 1

    repo_root = Path(__file__).resolve().parents[2]
    tmp_root = Path(tempfile.mkdtemp(prefix="specify-smoke-"))
    try:
        _write_spec_template(tmp_root)
        _init_git_repo(tmp_root)

        success_output = _run_create_feature(
            tmp_root,
            "--json",
            "--short-name",
            "smoke test",
            "Feature creation smoke test",
        )
        if success_output.returncode != 0:
            print(success_output.stderr, file=sys.stderr, end="")
            return success_output.returncode

        _verify_success_payload(success_output.stdout, tmp_root)

        fake_bin = tmp_root / "fake-bin"
        real_git = shutil.which("git") or "git"
        _write_fake_git(fake_bin, real_git)

        fail_env = os.environ.copy()
        fail_env["PATH"] = f"{fake_bin}:{fail_env.get('PATH', '')}"
        fail_env["REAL_GIT"] = str(real_git)
        fail_result = _run_create_feature(
            tmp_root,
            "--json",
            "--short-name",
            "locked branch",
            "Feature creation failure smoke test",
            env=fail_env,
        )
        if fail_result.returncode == 0:
            print("Expected create_new_feature.py to fail when git branch creation is denied", file=sys.stderr)
            return 1

        if "repository metadata is not writable in this environment" not in fail_result.stderr:
            print("Permission-specific message missing from failure output", file=sys.stderr)
            print(fail_result.stderr, file=sys.stderr, end="")
            return 1

        if "fatal: cannot lock ref" not in fail_result.stderr:
            print("Underlying git stderr missing from failure output", file=sys.stderr)
            print(fail_result.stderr, file=sys.stderr, end="")
            return 1

        print(tmp_root)
        return 0
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
