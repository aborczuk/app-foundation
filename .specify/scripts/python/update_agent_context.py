#!/usr/bin/env python3
# ruff: noqa: D101, D103
"""Python entrypoint for update-agent-context with shell-compatible behavior."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path


@dataclass
class RuntimeContext:
    repo_root: Path
    current_branch: str
    has_git: bool
    feature_dir: Path
    impl_plan: Path
    template_file: Path
    agent_type: str


@dataclass
class PlanData:
    language: str
    framework: str
    storage: str
    project_type: str


def log_info(message: str) -> None:
    print(f"INFO: {message}")


def log_success(message: str) -> None:
    print(f"\u2713 {message}")


def log_error(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)


def log_warning(message: str) -> None:
    print(f"WARNING: {message}", file=sys.stderr)


def _run_git(args: list[str], cwd: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return None
    return result.stdout.strip()


def _get_repo_root(script_path: Path) -> Path:
    cwd = Path.cwd()
    git_root = _run_git(["rev-parse", "--show-toplevel"], cwd)
    if git_root:
        return Path(git_root).resolve()
    return script_path.resolve().parents[3]


def _has_git(repo_root: Path) -> bool:
    return _run_git(["rev-parse", "--show-toplevel"], repo_root) is not None


def _get_current_branch(repo_root: Path) -> str:
    override = os.environ.get("SPECIFY_FEATURE", "").strip()
    if override:
        return override

    branch = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], repo_root)
    if branch:
        return branch

    specs_dir = repo_root / "specs"
    highest = -1
    latest_feature = ""
    if specs_dir.is_dir():
        for candidate in specs_dir.iterdir():
            if not candidate.is_dir():
                continue
            match = re.match(r"^([0-9]{3})-", candidate.name)
            if not match:
                continue
            number = int(match.group(1), 10)
            if number > highest:
                highest = number
                latest_feature = candidate.name
    if latest_feature:
        return latest_feature
    return "main"


def _find_feature_dir_by_prefix(repo_root: Path, branch_name: str) -> Path:
    specs_dir = repo_root / "specs"
    match = re.match(r"^([0-9]{3})-", branch_name)
    if not match:
        return specs_dir / branch_name

    prefix = match.group(1)
    matches = sorted(item.name for item in specs_dir.glob(f"{prefix}-*") if item.is_dir())
    if len(matches) == 0:
        return specs_dir / branch_name
    if len(matches) == 1:
        return specs_dir / matches[0]

    log_error(
        f"Multiple spec directories found with prefix '{prefix}': {' '.join(matches)}"
    )
    log_error("Please ensure only one spec directory exists per numeric prefix.")
    return specs_dir / branch_name


def _build_context(script_path: Path, argv: list[str]) -> RuntimeContext:
    repo_root = _get_repo_root(script_path)
    current_branch = _get_current_branch(repo_root)
    has_git = _has_git(repo_root)
    feature_dir = _find_feature_dir_by_prefix(repo_root, current_branch)
    return RuntimeContext(
        repo_root=repo_root,
        current_branch=current_branch,
        has_git=has_git,
        feature_dir=feature_dir,
        impl_plan=feature_dir / "plan.md",
        template_file=repo_root / ".specify" / "templates" / "agent-file-template.md",
        agent_type=argv[0] if argv else "",
    )


def validate_environment(ctx: RuntimeContext) -> bool:
    if not ctx.current_branch:
        log_error("Unable to determine current feature")
        if ctx.has_git:
            log_info("Make sure you're on a feature branch")
        else:
            log_info("Set SPECIFY_FEATURE environment variable or create a feature first")
        return False

    if not ctx.impl_plan.is_file():
        log_error(f"No plan.md found at {ctx.impl_plan}")
        log_info("Make sure you're working on a feature with a corresponding spec directory")
        if not ctx.has_git:
            log_info("Use: export SPECIFY_FEATURE=your-feature-name or create a new feature first")
        return False

    if not ctx.template_file.is_file():
        log_warning(f"Template file not found at {ctx.template_file}")
        log_warning("Creating new agent files will fail")

    return True


def _extract_plan_field(field_name: str, plan_text: str) -> str:
    pattern = re.compile(rf"^\*\*{re.escape(field_name)}\*\*: (.*)$", re.MULTILINE)
    match = pattern.search(plan_text)
    if not match:
        return ""
    value = match.group(1).strip()
    if "NEEDS CLARIFICATION" in value:
        return ""
    if value == "N/A":
        return ""
    return value


def parse_plan_data(plan_file: Path) -> PlanData | None:
    if not plan_file.is_file():
        log_error(f"Plan file not found: {plan_file}")
        return None
    if not os.access(plan_file, os.R_OK):
        log_error(f"Plan file is not readable: {plan_file}")
        return None

    log_info(f"Parsing plan data from {plan_file}")
    plan_text = plan_file.read_text(encoding="utf-8")
    language = _extract_plan_field("Language/Version", plan_text)
    framework = _extract_plan_field("Primary Dependencies", plan_text)
    storage = _extract_plan_field("Storage", plan_text)
    project_type = _extract_plan_field("Project Type", plan_text)

    if language:
        log_info(f"Found language: {language}")
    else:
        log_warning("No language information found in plan")
    if framework:
        log_info(f"Found framework: {framework}")
    if storage and storage != "N/A":
        log_info(f"Found database: {storage}")
    if project_type:
        log_info(f"Found project type: {project_type}")

    return PlanData(
        language=language,
        framework=framework,
        storage=storage,
        project_type=project_type,
    )


def format_technology_stack(language: str, framework: str) -> str:
    parts: list[str] = []
    if language and language != "NEEDS CLARIFICATION":
        parts.append(language)
    if framework and framework not in {"NEEDS CLARIFICATION", "N/A"}:
        parts.append(framework)
    if len(parts) == 0:
        return ""
    if len(parts) == 1:
        return parts[0]
    return " + ".join(parts)


def get_project_structure(project_type: str) -> str:
    if "web" in project_type:
        return "backend/\nfrontend/\ntests/"
    return "src/\ntests/"


def get_commands_for_language(language: str) -> str:
    if "Python" in language:
        return "cd src && pytest && ruff check ."
    if "Rust" in language:
        return "cargo test && cargo clippy"
    if "JavaScript" in language or "TypeScript" in language:
        return "npm test && npm run lint"
    return f"# Add commands for {language}"


def get_language_conventions(language: str) -> str:
    return f"{language}: Follow standard conventions"


def _write_atomic(path: Path, content: str) -> None:
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        delete=False,
    ) as temp_file:
        temp_file.write(content)
        temp_path = Path(temp_file.name)
    temp_path.replace(path)


def _cursor_frontmatter() -> str:
    return "\n".join(
        [
            "---",
            'description: Project Development Guidelines',
            'globs: ["**/*"]',
            "alwaysApply: true",
            "---",
            "",
        ]
    )


def create_new_agent_content(
    target_file: Path,
    project_name: str,
    current_date: str,
    branch: str,
    plan_data: PlanData,
    template_file: Path,
) -> str:
    if not template_file.is_file():
        raise FileNotFoundError(f"Template not found at {template_file}")
    if not os.access(template_file, os.R_OK):
        raise PermissionError(f"Template file is not readable: {template_file}")

    log_info("Creating new agent context file from template...")
    content = template_file.read_text(encoding="utf-8")

    if plan_data.language and plan_data.framework:
        tech_stack = f"- {plan_data.language} + {plan_data.framework} ({branch})"
        recent_change = f"- {branch}: Added {plan_data.language} + {plan_data.framework}"
    elif plan_data.language:
        tech_stack = f"- {plan_data.language} ({branch})"
        recent_change = f"- {branch}: Added {plan_data.language}"
    elif plan_data.framework:
        tech_stack = f"- {plan_data.framework} ({branch})"
        recent_change = f"- {branch}: Added {plan_data.framework}"
    else:
        tech_stack = f"- ({branch})"
        recent_change = f"- {branch}: Added"

    substitutions = {
        "[PROJECT NAME]": project_name,
        "[DATE]": current_date,
        "[EXTRACTED FROM ALL PLAN.MD FILES]": tech_stack,
        "[ACTUAL STRUCTURE FROM PLANS]": get_project_structure(plan_data.project_type),
        "[ONLY COMMANDS FOR ACTIVE TECHNOLOGIES]": get_commands_for_language(plan_data.language),
        "[LANGUAGE-SPECIFIC, ONLY FOR LANGUAGES IN USE]": get_language_conventions(plan_data.language),
        "[LAST 3 FEATURES AND WHAT THEY ADDED]": recent_change,
    }
    for key, value in substitutions.items():
        content = content.replace(key, value)
    content = content.replace("\\n", "\n")

    if target_file.suffix == ".mdc":
        content = _cursor_frontmatter() + content

    if not content.endswith("\n"):
        content += "\n"
    return content


def _replace_last_updated(line: str, current_date: str) -> str:
    pattern = r"(\*\*Last\ updated\*\*:.*?)([0-9]{4}-[0-9]{2}-[0-9]{2})"
    if re.search(pattern, line):
        return re.sub(pattern, rf"\g<1>{current_date}", line)
    return line


def update_existing_agent_content(
    target_file: Path,
    current_date: str,
    branch: str,
    plan_data: PlanData,
) -> str:
    log_info("Updating existing agent context file...")
    lines = target_file.read_text(encoding="utf-8").splitlines()
    output: list[str] = []

    tech_stack = format_technology_stack(plan_data.language, plan_data.framework)
    new_tech_entries: list[str] = []
    if tech_stack and tech_stack not in "\n".join(lines):
        new_tech_entries.append(f"- {tech_stack} ({branch})")
    if (
        plan_data.storage
        and plan_data.storage not in {"N/A", "NEEDS CLARIFICATION"}
        and plan_data.storage not in "\n".join(lines)
    ):
        new_tech_entries.append(f"- {plan_data.storage} ({branch})")

    new_change_entry = ""
    if tech_stack:
        new_change_entry = f"- {branch}: Added {tech_stack}"
    elif plan_data.storage and plan_data.storage not in {"N/A", "NEEDS CLARIFICATION"}:
        new_change_entry = f"- {branch}: Added {plan_data.storage}"

    has_active_technologies = "## Active Technologies" in lines
    has_recent_changes = "## Recent Changes" in lines

    in_tech_section = False
    in_changes_section = False
    tech_entries_added = False
    existing_changes_count = 0

    for line in lines:
        if line == "## Active Technologies":
            output.append(line)
            in_tech_section = True
            continue
        if in_tech_section and line.startswith("## "):
            if not tech_entries_added and new_tech_entries:
                output.extend(new_tech_entries)
                tech_entries_added = True
            output.append(line)
            in_tech_section = False
            continue
        if in_tech_section and line == "":
            if not tech_entries_added and new_tech_entries:
                output.extend(new_tech_entries)
                tech_entries_added = True
            output.append(line)
            continue

        if line == "## Recent Changes":
            output.append(line)
            if new_change_entry:
                output.append(new_change_entry)
            in_changes_section = True
            continue
        if in_changes_section and line.startswith("## "):
            output.append(line)
            in_changes_section = False
            continue
        if in_changes_section and line.startswith("- "):
            if existing_changes_count < 2:
                output.append(line)
                existing_changes_count += 1
            continue

        output.append(_replace_last_updated(line, current_date))

    if in_tech_section and not tech_entries_added and new_tech_entries:
        output.extend(new_tech_entries)
        tech_entries_added = True

    if not has_active_technologies and new_tech_entries:
        output.append("")
        output.append("## Active Technologies")
        output.extend(new_tech_entries)

    if not has_recent_changes and new_change_entry:
        output.append("")
        output.append("## Recent Changes")
        output.append(new_change_entry)

    content = "\n".join(output)
    if target_file.suffix == ".mdc":
        first_line = output[0] if output else ""
        if first_line != "---":
            content = _cursor_frontmatter() + content
    if not content.endswith("\n"):
        content += "\n"
    return content


def update_agent_file(
    target_file: Path,
    agent_name: str,
    ctx: RuntimeContext,
    plan_data: PlanData,
) -> bool:
    if not str(target_file) or not agent_name:
        log_error("update_agent_file requires target_file and agent_name parameters")
        return False

    log_info(f"Updating {agent_name} context file: {target_file}")
    project_name = ctx.repo_root.name
    current_date = date.today().isoformat()
    target_file.parent.mkdir(parents=True, exist_ok=True)

    if not target_file.is_file():
        try:
            content = create_new_agent_content(
                target_file=target_file,
                project_name=project_name,
                current_date=current_date,
                branch=ctx.current_branch,
                plan_data=plan_data,
                template_file=ctx.template_file,
            )
            _write_atomic(target_file, content)
            log_success(f"Created new {agent_name} context file")
            return True
        except FileNotFoundError as exc:
            log_error(str(exc))
            return False
        except PermissionError as exc:
            log_error(str(exc))
            return False
        except Exception as exc:
            log_error(f"Failed to create new agent file: {exc}")
            return False

    if not os.access(target_file, os.R_OK):
        log_error(f"Cannot read existing file: {target_file}")
        return False
    if not os.access(target_file, os.W_OK):
        log_error(f"Cannot write to existing file: {target_file}")
        return False

    try:
        content = update_existing_agent_content(
            target_file=target_file,
            current_date=current_date,
            branch=ctx.current_branch,
            plan_data=plan_data,
        )
        _write_atomic(target_file, content)
        log_success(f"Updated existing {agent_name} context file")
        return True
    except Exception as exc:
        log_error(f"Failed to update existing agent file: {exc}")
        return False


def _agent_entries(repo_root: Path) -> list[tuple[str, Path, str]]:
    agents_file = repo_root / "AGENTS.md"
    return [
        ("claude", repo_root / "CLAUDE.md", "Claude Code"),
        ("gemini", repo_root / "GEMINI.md", "Gemini CLI"),
        ("copilot", repo_root / ".github" / "agents" / "copilot-instructions.md", "GitHub Copilot"),
        ("cursor-agent", repo_root / ".cursor" / "rules" / "specify-rules.mdc", "Cursor IDE"),
        ("qwen", repo_root / "QWEN.md", "Qwen Code"),
        ("opencode", agents_file, "opencode"),
        ("codex", agents_file, "Codex CLI"),
        ("windsurf", repo_root / ".windsurf" / "rules" / "specify-rules.md", "Windsurf"),
        ("kilocode", repo_root / ".kilocode" / "rules" / "specify-rules.md", "Kilo Code"),
        ("auggie", repo_root / ".augment" / "rules" / "specify-rules.md", "Auggie CLI"),
        ("roo", repo_root / ".roo" / "rules" / "specify-rules.md", "Roo Code"),
        ("codebuddy", repo_root / "CODEBUDDY.md", "CodeBuddy CLI"),
        ("qodercli", repo_root / "QODER.md", "Qoder CLI"),
        ("amp", agents_file, "Amp"),
        ("shai", repo_root / "SHAI.md", "SHAI"),
        ("kiro-cli", agents_file, "Kiro CLI"),
        ("agy", repo_root / ".agent" / "rules" / "specify-rules.md", "Antigravity"),
        ("bob", agents_file, "IBM Bob"),
    ]


def update_specific_agent(ctx: RuntimeContext, plan_data: PlanData) -> bool:
    if ctx.agent_type == "generic":
        log_info("Generic agent: no predefined context file. Use the agent-specific update script for your agent.")
        return True

    lookup = {key: (path, label) for key, path, label in _agent_entries(ctx.repo_root)}
    match = lookup.get(ctx.agent_type)
    if not match:
        log_error(f"Unknown agent type '{ctx.agent_type}'")
        log_error(
            "Expected: claude|gemini|copilot|cursor-agent|qwen|opencode|codex|windsurf|kilocode|auggie|roo|codebuddy|amp|shai|kiro-cli|agy|bob|qodercli|generic"
        )
        return False

    path, label = match
    return update_agent_file(path, label, ctx, plan_data)


def update_all_existing_agents(ctx: RuntimeContext, plan_data: PlanData) -> bool:
    found_agent = False
    all_ok = True

    ordered_checks: list[tuple[Path, str]] = [
        (ctx.repo_root / "CLAUDE.md", "Claude Code"),
        (ctx.repo_root / "GEMINI.md", "Gemini CLI"),
        (ctx.repo_root / ".github" / "agents" / "copilot-instructions.md", "GitHub Copilot"),
        (ctx.repo_root / ".cursor" / "rules" / "specify-rules.mdc", "Cursor IDE"),
        (ctx.repo_root / "QWEN.md", "Qwen Code"),
        (ctx.repo_root / "AGENTS.md", "Codex/opencode"),
        (ctx.repo_root / ".windsurf" / "rules" / "specify-rules.md", "Windsurf"),
        (ctx.repo_root / ".kilocode" / "rules" / "specify-rules.md", "Kilo Code"),
        (ctx.repo_root / ".augment" / "rules" / "specify-rules.md", "Auggie CLI"),
        (ctx.repo_root / ".roo" / "rules" / "specify-rules.md", "Roo Code"),
        (ctx.repo_root / "CODEBUDDY.md", "CodeBuddy CLI"),
        (ctx.repo_root / "SHAI.md", "SHAI"),
        (ctx.repo_root / "QODER.md", "Qoder CLI"),
        (ctx.repo_root / "AGENTS.md", "Kiro CLI"),
        (ctx.repo_root / ".agent" / "rules" / "specify-rules.md", "Antigravity"),
        (ctx.repo_root / "AGENTS.md", "IBM Bob"),
    ]

    for path, label in ordered_checks:
        if path.is_file():
            found_agent = True
            if not update_agent_file(path, label, ctx, plan_data):
                all_ok = False

    if not found_agent:
        log_info("No existing agent files found, creating default Claude file...")
        if not update_agent_file(ctx.repo_root / "CLAUDE.md", "Claude Code", ctx, plan_data):
            all_ok = False

    return all_ok


def print_summary(ctx: RuntimeContext, plan_data: PlanData) -> None:
    print()
    log_info("Summary of changes:")
    if plan_data.language:
        print(f"  - Added language: {plan_data.language}")
    if plan_data.framework:
        print(f"  - Added framework: {plan_data.framework}")
    if plan_data.storage and plan_data.storage != "N/A":
        print(f"  - Added database: {plan_data.storage}")

    print()
    log_info(
        "Usage: update-agent-context.sh [claude|gemini|copilot|cursor-agent|qwen|opencode|codex|windsurf|kilocode|auggie|roo|codebuddy|amp|shai|kiro-cli|agy|bob|qodercli]"
    )


def main(argv: list[str]) -> int:
    script_path = Path(__file__)
    ctx = _build_context(script_path, argv)
    if not validate_environment(ctx):
        return 1

    log_info(f"=== Updating agent context files for feature {ctx.current_branch} ===")
    plan_data = parse_plan_data(ctx.impl_plan)
    if plan_data is None:
        log_error("Failed to parse plan data")
        return 1

    if not ctx.agent_type:
        log_info("No agent specified, updating all existing agent files...")
        success = update_all_existing_agents(ctx, plan_data)
    else:
        log_info(f"Updating specific agent: {ctx.agent_type}")
        success = update_specific_agent(ctx, plan_data)

    print_summary(ctx, plan_data)
    if success:
        log_success("Agent context update completed successfully")
        return 0
    log_error("Agent context update completed with errors")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
