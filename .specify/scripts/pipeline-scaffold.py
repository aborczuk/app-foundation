#!/usr/bin/env python3
"""Pre-scaffold output artifacts from templates before LLM fills them.

Creates empty file structures from templates, resolving variable substitutions.
Prevents LLM from regenerating structural/format content (headers, fixed fields, etc.).

Usage:
    pipeline-scaffold.py <command-name> [--feature-dir <dir>] [KEY=value ...] [--force]

Examples:
    pipeline-scaffold.py speckit.research --feature-dir specs/020-app-foundation
    pipeline-scaffold.py speckit.sketch.hud-code TASK_ID=T010 DESCRIPTION="Setup DB"
    pipeline-scaffold.py speckit.e2e --feature-dir specs/020-app-foundation FEATURE_SLUG=020
"""

import argparse
import sys
import re
from pathlib import Path
from datetime import datetime
import yaml


def main():
    parser = argparse.ArgumentParser(
        description="Scaffold output artifacts from templates"
    )
    parser.add_argument("command", help="Command name (e.g. speckit.research)")
    parser.add_argument(
        "--feature-dir", help="Feature directory (for feature-level artifacts)"
    )
    parser.add_argument(
        "--force", action="store_true", help="Overwrite existing files"
    )
    parser.add_argument(
        "substitutions",
        nargs="*",
        help="Variable substitutions: KEY=value (e.g. TASK_ID=T010)",
    )

    args = parser.parse_args()

    # Locate manifest and template directory
    repo_root = Path(__file__).parent.parent.parent
    manifest_path = repo_root / ".specify" / "command-manifest.yaml"
    template_dir = repo_root / ".specify" / "templates"

    if not manifest_path.exists():
        print(f"ERROR: Manifest not found: {manifest_path}", file=sys.stderr)
        sys.exit(1)

    # Load manifest
    try:
        with open(manifest_path) as f:
            manifest = yaml.safe_load(f)
    except Exception as e:
        print(f"ERROR: Failed to load manifest: {e}", file=sys.stderr)
        sys.exit(1)

    # Find command in manifest
    if "commands" not in manifest or args.command not in manifest["commands"]:
        print(f"ERROR: Command not found in manifest: {args.command}", file=sys.stderr)
        sys.exit(1)

    command_def = manifest["commands"][args.command]
    artifacts = command_def.get("artifacts", [])

    if not artifacts:
        print(f"No artifacts for command: {args.command}", file=sys.stderr)
        sys.exit(0)

    # Build substitution variables
    vars_dict = {
        "DATE": datetime.now().strftime("%Y-%m-%d"),
        "REPO_ROOT": str(repo_root),
        "FEATURE_DIR": args.feature_dir or "",
    }

    # Parse KEY=value substitutions
    for sub in args.substitutions:
        if "=" in sub:
            key, val = sub.split("=", 1)
            vars_dict[key] = val

    # Process each artifact
    created_count = 0
    skipped_count = 0

    for artifact in artifacts:
        output_path_template = artifact.get("output_path", "")
        template_name = artifact.get("template", "")

        if not output_path_template:
            continue

        # Resolve output path by substituting variables
        output_path = resolve_path(output_path_template, vars_dict)

        # Skip if already exists and not --force
        if Path(output_path).exists() and not args.force:
            print(f"[pipeline-scaffold] Skipping (exists): {output_path}", file=sys.stderr)
            skipped_count += 1
            continue

        # Skip if no template (LLM generates it)
        if not template_name:
            print(
                f"[pipeline-scaffold] Skipping (no template): {output_path}",
                file=sys.stderr,
            )
            skipped_count += 1
            continue

        # Verify template exists
        template_path = template_dir / template_name
        if not template_path.exists():
            print(f"ERROR: Template not found: {template_path}", file=sys.stderr)
            sys.exit(1)

        # Create parent directory
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        # Copy template
        content = template_path.read_text()

        # Perform substitutions in content
        content = substitute_vars(content, vars_dict)

        # Write file
        Path(output_path).write_text(content)

        print(f"[pipeline-scaffold] Created: {output_path}", file=sys.stderr)
        created_count += 1

    if created_count == 0 and skipped_count == 0:
        print(f"ERROR: No artifacts resolved for command: {args.command}", file=sys.stderr)
        sys.exit(1)

    print(
        f"[pipeline-scaffold] Done — Created: {created_count}, Skipped: {skipped_count}",
        file=sys.stderr,
    )


def resolve_path(path_template: str, vars_dict: dict[str, str]) -> str:
    """Resolve a path template by substituting variables.

    Replaces ${VAR} and $VAR patterns with corresponding values from vars_dict.
    """
    result = path_template
    for key, value in vars_dict.items():
        # Replace ${KEY} patterns
        result = result.replace("${" + key + "}", value)
        # Replace $KEY patterns (word boundaries)
        result = re.sub(r"\$" + key + r"\b", value, result)
    return result


def substitute_vars(content: str, vars_dict: dict[str, str]) -> str:
    """Perform scalar substitutions in file content.

    Replaces [KEY] patterns with corresponding values from vars_dict.
    """
    result = content
    for key, value in vars_dict.items():
        # Replace [KEY] patterns
        result = result.replace("[" + key + "]", value)
    return result


if __name__ == "__main__":
    main()
