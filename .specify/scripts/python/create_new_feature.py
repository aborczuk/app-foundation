#!/usr/bin/env python3
"""Python entrypoint for create-new-feature workflow with shell-compatible behavior."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


def _usage(program: str) -> str:
    return "\n".join(
        [
            f"Usage: {program} [--json] [--short-name <name>] [--number N] [--base <branch>] <feature_description>",
            "",
            "Options:",
            "  --json              Output in JSON format",
            "  --short-name <name> Provide a custom short name (2-4 words) for the branch",
            "  --number N          Specify branch number manually (overrides auto-detection)",
            "  --base <branch>     Create feature branch from this base (default: main)",
            "  --help, -h          Show this help message",
            "",
            "Examples:",
            f"  {program} 'Add user authentication system' --short-name 'user-auth'",
            f"  {program} 'Implement OAuth2 integration for API' --number 5",
            f"  {program} 'Implement OAuth2 integration for API' --base main",
        ]
    )


def _parse_args(argv: list[str], program: str) -> tuple[bool, str, str, str, str]:
    """Parse CLI arguments for the create-feature flow."""
    json_mode = False
    short_name = ""
    branch_number = ""
    base_branch = ""
    args: list[str] = []

    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg == "--json":
            json_mode = True
        elif arg == "--short-name":
            if index + 1 >= len(argv) or argv[index + 1].startswith("--"):
                print("Error: --short-name requires a value", file=sys.stderr)
                raise SystemExit(1)
            index += 1
            short_name = argv[index]
        elif arg == "--number":
            if index + 1 >= len(argv) or argv[index + 1].startswith("--"):
                print("Error: --number requires a value", file=sys.stderr)
                raise SystemExit(1)
            index += 1
            branch_number = argv[index]
        elif arg == "--base":
            if index + 1 >= len(argv) or argv[index + 1].startswith("--"):
                print("Error: --base requires a value", file=sys.stderr)
                raise SystemExit(1)
            index += 1
            base_branch = argv[index]
        elif arg in {"--help", "-h"}:
            print(_usage(program))
            raise SystemExit(0)
        else:
            args.append(arg)
        index += 1

    raw_feature_description = " ".join(args)
    if not raw_feature_description:
        print(
            f"Usage: {program} [--json] [--short-name <name>] [--number N] [--base <branch>] <feature_description>",
            file=sys.stderr,
        )
        raise SystemExit(1)
    feature_description = raw_feature_description.strip()
    if not feature_description:
        print("Error: Feature description cannot be empty or contain only whitespace", file=sys.stderr)
        raise SystemExit(1)
    return json_mode, short_name, branch_number, base_branch, feature_description


def _run_git(args: list[str], repo_root: Path, *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=check,
        capture_output=True,
        text=True,
    )


def _resolve_base_ref(requested: str, repo_root: Path) -> str | None:
    """Resolve a deterministic base ref for feature-branch creation."""
    if requested:
        direct = _run_git(["rev-parse", "--verify", "--quiet", f"{requested}^{{commit}}"], repo_root, check=False)
        if direct.returncode == 0:
            return requested
        prefixed = _run_git(["rev-parse", "--verify", "--quiet", f"origin/{requested}^{{commit}}"], repo_root, check=False)
        if prefixed.returncode == 0:
            return f"origin/{requested}"
        return None

    for candidate in ("main", "origin/main", "master", "origin/master"):
        resolved = _run_git(["rev-parse", "--verify", "--quiet", f"{candidate}^{{commit}}"], repo_root, check=False)
        if resolved.returncode == 0:
            return candidate
    return None


def _working_tree_dirty(repo_root: Path) -> bool:
    """Return True when tracked or untracked changes are present."""
    status = _run_git(["status", "--porcelain"], repo_root, check=False)
    return bool(status.stdout.strip())


def _count_rev_list(repo_root: Path, range_expr: str) -> int:
    """Return commit count for a rev-list range expression."""
    result = _run_git(["rev-list", "--count", range_expr], repo_root, check=False)
    raw = (result.stdout or "").strip()
    try:
        return int(raw) if raw else 0
    except ValueError:
        return 0


def _ensure_main_branch_ready(repo_root: Path, base_ref: str) -> int:
    """Enforce clean and synced main before branching from main."""
    if base_ref not in {"main", "origin/main"}:
        return 0

    has_main = _run_git(["rev-parse", "--verify", "--quiet", "main^{commit}"], repo_root, check=False)
    if has_main.returncode != 0:
        print("Error: Local 'main' branch is required for deterministic /speckit.specify branching.", file=sys.stderr)
        print("Create or fetch 'main', then retry (or pass --base <branch> intentionally).", file=sys.stderr)
        return 1

    current_branch = (_run_git(["branch", "--show-current"], repo_root, check=False).stdout or "").strip()
    if current_branch != "main":
        if _working_tree_dirty(repo_root):
            print(f"Error: You are on '{current_branch}' with uncommitted changes.", file=sys.stderr)
            print("To branch off main, commit/stash/discard current changes first, then rerun /speckit.specify.", file=sys.stderr)
            return 1
        switch_result = _run_git(["switch", "main"], repo_root, check=False)
        if switch_result.returncode != 0:
            print("Error: Failed to switch to 'main' before feature scaffolding.", file=sys.stderr)
            print("Switch to 'main' manually and rerun /speckit.specify.", file=sys.stderr)
            return 1

    if _working_tree_dirty(repo_root):
        print("Error: Local 'main' has uncommitted changes.", file=sys.stderr)
        print("Should these be committed first? Commit/stash/discard them, then rerun /speckit.specify.", file=sys.stderr)
        return 1

    has_origin_main = _run_git(["rev-parse", "--verify", "--quiet", "origin/main^{commit}"], repo_root, check=False)
    if has_origin_main.returncode == 0:
        ahead_count = _count_rev_list(repo_root, "origin/main..main")
        behind_count = _count_rev_list(repo_root, "main..origin/main")
        if ahead_count > 0:
            print(f"Error: Local 'main' has {ahead_count} commit(s) not pushed to origin/main.", file=sys.stderr)
            print("Should these be pushed first? Push main, then rerun /speckit.specify.", file=sys.stderr)
            return 1
        if behind_count > 0:
            print(f"Error: Local 'main' is {behind_count} commit(s) behind origin/main.", file=sys.stderr)
            print("Pull/rebase main first so feature branches start from up-to-date main.", file=sys.stderr)
            return 1

    return 0


def _find_repo_root(start_dir: Path) -> Path | None:
    candidate = start_dir.resolve()
    while True:
        if (candidate / ".git").exists() or (candidate / ".specify").exists():
            return candidate
        if candidate == candidate.parent:
            return None
        candidate = candidate.parent


def _get_repo_root(script_dir: Path) -> tuple[Path, bool]:
    cwd = Path.cwd()
    try:
        result = _run_git(["rev-parse", "--show-toplevel"], cwd, check=True)
        return Path(result.stdout.strip()).resolve(), True
    except Exception:
        root = _find_repo_root(script_dir)
        if root is None:
            print(
                "Error: Could not determine repository root. Please run this script from within the repository.",
                file=sys.stderr,
            )
            raise SystemExit(1)
        return root, False


def _get_highest_from_specs(specs_dir: Path) -> int:
    highest = 0
    if not specs_dir.is_dir():
        return highest
    for entry in specs_dir.iterdir():
        if not entry.is_dir():
            continue
        match = re.match(r"^([0-9]+)", entry.name)
        if not match:
            number = 0
        else:
            number = int(match.group(1), 10)
        highest = max(highest, number)
    return highest


def _clean_git_branch_output(line: str) -> str:
    cleaned = re.sub(r"^[* ]*", "", line.strip())
    cleaned = re.sub(r"^remotes/[^/]*/", "", cleaned)
    return cleaned


def _get_highest_from_branches(repo_root: Path) -> int:
    highest = 0
    try:
        branches_output = _run_git(["branch", "-a"], repo_root, check=True).stdout
    except Exception:
        return 0

    for raw_line in branches_output.splitlines():
        cleaned = _clean_git_branch_output(raw_line)
        if re.match(r"^[0-9]{3}-", cleaned):
            number = int(cleaned[:3], 10)
            highest = max(highest, number)
    return highest


def _check_existing_branches(specs_dir: Path, repo_root: Path) -> int:
    try:
        _run_git(["fetch", "--all", "--prune"], repo_root, check=True)
    except Exception:
        pass
    highest_branch = _get_highest_from_branches(repo_root)
    highest_spec = _get_highest_from_specs(specs_dir)
    return max(highest_branch, highest_spec) + 1


def _clean_branch_name(name: str) -> str:
    lowered = name.lower()
    lowered = re.sub(r"[^a-z0-9]", "-", lowered)
    lowered = re.sub(r"-+", "-", lowered)
    lowered = lowered.strip("-")
    return lowered


_STOP_WORDS = {
    "i",
    "a",
    "an",
    "the",
    "to",
    "for",
    "of",
    "in",
    "on",
    "at",
    "by",
    "with",
    "from",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
    "have",
    "has",
    "had",
    "do",
    "does",
    "did",
    "will",
    "would",
    "should",
    "could",
    "can",
    "may",
    "might",
    "must",
    "shall",
    "this",
    "that",
    "these",
    "those",
    "my",
    "your",
    "our",
    "their",
    "want",
    "need",
    "add",
    "get",
    "set",
}


def _generate_branch_name(description: str) -> str:
    clean_name = re.sub(r"[^a-z0-9]", " ", description.lower())
    meaningful_words: list[str] = []
    for word in clean_name.split():
        if word in _STOP_WORDS:
            continue
        if len(word) >= 3:
            meaningful_words.append(word)
            continue
        if re.search(rf"\b{re.escape(word.upper())}\b", description):
            meaningful_words.append(word)

    if meaningful_words:
        max_words = 4 if len(meaningful_words) == 4 else 3
        return "-".join(meaningful_words[:max_words])

    cleaned = _clean_branch_name(description)
    parts = [part for part in cleaned.split("-") if part]
    return "-".join(parts[:3])


def _branch_exists(repo_root: Path, branch_name: str) -> bool:
    try:
        result = _run_git(["branch", "--list", branch_name], repo_root, check=True)
    except Exception:
        return False
    return bool(result.stdout.strip())


def _is_permission_error(stderr_text: str) -> bool:
    return bool(
        re.search(
            r"permission denied|operation not permitted|read-only|unable to create|could not lock ref|failed to lock|index\.lock",
            stderr_text,
            flags=re.IGNORECASE,
        )
    )


def main(argv: list[str]) -> int:
    """Create a feature branch/spec scaffold with deterministic base checks."""
    program = Path(sys.argv[0]).name
    json_mode, short_name, branch_number, base_branch, feature_description = _parse_args(argv, program)

    script_dir = Path(__file__).resolve().parent
    repo_root, has_git = _get_repo_root(script_dir)
    os.chdir(repo_root)

    specs_dir = repo_root / "specs"
    specs_dir.mkdir(parents=True, exist_ok=True)

    if short_name:
        branch_suffix = _clean_branch_name(short_name)
    else:
        branch_suffix = _generate_branch_name(feature_description)

    if not branch_number:
        if has_git:
            branch_number = str(_check_existing_branches(specs_dir, repo_root))
        else:
            branch_number = str(_get_highest_from_specs(specs_dir) + 1)

    try:
        feature_num = f"{int(branch_number, 10):03d}"
    except ValueError:
        print(f"Error: --number must be numeric, got '{branch_number}'", file=sys.stderr)
        return 1

    branch_name = f"{feature_num}-{branch_suffix}"

    max_branch_length = 244
    if len(branch_name) > max_branch_length:
        max_suffix_length = max_branch_length - 4
        truncated_suffix = branch_suffix[:max_suffix_length].rstrip("-")
        original_branch_name = branch_name
        branch_name = f"{feature_num}-{truncated_suffix}"
        print("[specify] Warning: Branch name exceeded GitHub's 244-byte limit", file=sys.stderr)
        print(f"[specify] Original: {original_branch_name} ({len(original_branch_name)} bytes)", file=sys.stderr)
        print(f"[specify] Truncated to: {branch_name} ({len(branch_name)} bytes)", file=sys.stderr)

    if has_git:
        base_selection = base_branch or os.getenv("SPECIFY_BASE_BRANCH", "")
        base_ref = _resolve_base_ref(base_selection, repo_root)
        if base_ref is None:
            if base_selection:
                print(f"Error: Could not resolve base branch '{base_selection}'.", file=sys.stderr)
                print("Provide a valid branch via --base <branch>.", file=sys.stderr)
            else:
                print("Error: Could not resolve a deterministic base branch.", file=sys.stderr)
                print("Expected one of: main, origin/main, master, origin/master.", file=sys.stderr)
                print("Use --base <branch> to select a specific base.", file=sys.stderr)
            return 1

        readiness_status = _ensure_main_branch_ready(repo_root, base_ref)
        if readiness_status != 0:
            return readiness_status

        try:
            _run_git(["checkout", "-b", branch_name, base_ref], repo_root, check=True)
        except subprocess.CalledProcessError as exc:
            branch_create_error = re.sub(r"\s+", " ", (exc.stderr or "").strip())

            if _branch_exists(repo_root, branch_name):
                print(
                    f"Error: Branch '{branch_name}' already exists. Please use a different feature name or specify a different number with --number.",
                    file=sys.stderr,
                )
                return 1

            if _is_permission_error(branch_create_error):
                print(
                    f"Error: Failed to create git branch '{branch_name}' because repository metadata is not writable in this environment.",
                    file=sys.stderr,
                )
                print(
                    "Hint: rerun with write-enabled git permissions, or create the branch manually and then rerun /speckit.specify in update mode.",
                    file=sys.stderr,
                )
                if branch_create_error:
                    print(f"[specify] git stderr: {branch_create_error}", file=sys.stderr)
                return 1

            print(f"Error: Failed to create git branch '{branch_name}' from '{base_ref}'.", file=sys.stderr)
            print("Please ensure your working tree is clean and the base branch is valid.", file=sys.stderr)
            return 1
    else:
        print(f"[specify] Warning: Git repository not detected; skipped branch creation for {branch_name}", file=sys.stderr)

    feature_dir = specs_dir / branch_name
    feature_dir.mkdir(parents=True, exist_ok=True)

    template = repo_root / ".specify" / "templates" / "spec-template.md"
    spec_file = feature_dir / "spec.md"
    if template.is_file():
        shutil.copyfile(template, spec_file)
    else:
        spec_file.touch()

    os.environ["SPECIFY_FEATURE"] = branch_name

    if json_mode:
        print(
            (
                '{"BRANCH_NAME":"%s","SPEC_FILE":"%s","FEATURE_NUM":"%s"}'
                % (branch_name, str(spec_file), feature_num)
            )
        )
    else:
        print(f"BRANCH_NAME: {branch_name}")
        print(f"SPEC_FILE: {spec_file}")
        print(f"FEATURE_NUM: {feature_num}")
        print(f"SPECIFY_FEATURE environment variable set to: {branch_name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
