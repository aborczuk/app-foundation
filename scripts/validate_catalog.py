"""Validate catalog.yaml against the expected schema.

Checks:
- Required top-level sections present (system, components, resources, external_services)
- Each component has required fields (name, kind, type, lifecycle, spec, behavior_map)
- Each resource has required fields (name, kind, type)
- Each external_service has required fields (name, type, used_by)
- All depends_on references resolve to a known resource or external_service name
- All spec and behavior_map file paths exist on disk
- All used_by references resolve to a known component name

Usage:
    python scripts/validate_catalog.py
    python scripts/validate_catalog.py --catalog path/to/catalog.yaml
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: pyyaml is required. Run: uv sync", file=sys.stderr)
    sys.exit(1)

_REPO_ROOT = Path(__file__).resolve().parent.parent

_COMPONENT_REQUIRED = {"name", "kind", "type", "lifecycle", "spec", "behavior_map"}
_RESOURCE_REQUIRED = {"name", "kind", "type"}
_EXTERNAL_SERVICE_REQUIRED = {"name", "type", "used_by"}


def _load(catalog_path: Path) -> dict:
    """Load and parse catalog.yaml."""
    with catalog_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError("catalog.yaml must be a YAML mapping at the top level")
    return data


def _check_top_level(data: dict, errors: list[str]) -> None:
    """Verify required top-level sections exist."""
    for section in ("system", "components", "resources", "external_services"):
        if section not in data:
            errors.append(f"Missing top-level section: '{section}'")


def _check_components(
    data: dict,
    errors: list[str],
    repo_root: Path,
) -> set[str]:
    """Validate each component entry; return set of component names."""
    names: set[str] = set()
    for i, comp in enumerate(data.get("components") or []):
        label = comp.get("name", f"components[{i}]")
        names.add(comp.get("name", ""))
        for field in _COMPONENT_REQUIRED:
            if not comp.get(field):
                errors.append(f"Component '{label}': missing required field '{field}'")
        for path_field in ("spec", "behavior_map"):
            path_val = comp.get(path_field)
            if path_val and not (repo_root / path_val).exists():
                errors.append(
                    f"Component '{label}': {path_field} path not found: '{path_val}'"
                )
    return names


def _check_resources(data: dict, errors: list[str]) -> set[str]:
    """Validate each resource entry; return set of resource names."""
    names: set[str] = set()
    for i, res in enumerate(data.get("resources") or []):
        label = res.get("name", f"resources[{i}]")
        names.add(res.get("name", ""))
        for field in _RESOURCE_REQUIRED:
            if not res.get(field):
                errors.append(f"Resource '{label}': missing required field '{field}'")
    return names


def _check_external_services(data: dict, errors: list[str]) -> set[str]:
    """Validate each external_service entry; return set of service names."""
    names: set[str] = set()
    for i, svc in enumerate(data.get("external_services") or []):
        label = svc.get("name", f"external_services[{i}]")
        names.add(svc.get("name", ""))
        for field in _EXTERNAL_SERVICE_REQUIRED:
            if not svc.get(field):
                errors.append(f"External service '{label}': missing required field '{field}'")
    return names


def _check_depends_on(
    data: dict,
    resource_names: set[str],
    service_names: set[str],
    errors: list[str],
) -> None:
    """Verify all depends_on references resolve."""
    known = resource_names | service_names
    for comp in data.get("components") or []:
        label = comp.get("name", "?")
        for dep in comp.get("depends_on") or []:
            if dep not in known:
                errors.append(
                    f"Component '{label}': depends_on '{dep}' not found in "
                    "resources or external_services"
                )


def _check_used_by(
    data: dict,
    component_names: set[str],
    errors: list[str],
) -> None:
    """Verify all used_by references resolve to a known component."""
    for svc in data.get("external_services") or []:
        label = svc.get("name", "?")
        for user in svc.get("used_by") or []:
            if user not in component_names:
                errors.append(
                    f"External service '{label}': used_by '{user}' not found in components"
                )
    for res in data.get("resources") or []:
        label = res.get("name", "?")
        for user in res.get("used_by") or []:
            if user not in component_names:
                errors.append(
                    f"Resource '{label}': used_by '{user}' not found in components"
                )


def validate(catalog_path: Path, repo_root: Path) -> list[str]:
    """Run all checks on catalog_path; return list of error strings (empty = valid)."""
    errors: list[str] = []
    try:
        data = _load(catalog_path)
    except (yaml.YAMLError, ValueError) as exc:
        return [f"Failed to parse catalog.yaml: {exc}"]

    _check_top_level(data, errors)
    if errors:
        # Can't check sub-sections without top-level structure
        return errors

    component_names = _check_components(data, errors, repo_root)
    resource_names = _check_resources(data, errors)
    service_names = _check_external_services(data, errors)
    _check_depends_on(data, resource_names, service_names, errors)
    _check_used_by(data, component_names, errors)

    return errors


def main() -> None:
    """Run catalog validation and exit non-zero on errors."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--catalog",
        default=str(_REPO_ROOT / "catalog.yaml"),
        help="Path to catalog.yaml (default: repo root)",
    )
    args = parser.parse_args()

    catalog_path = Path(args.catalog).resolve()
    if not catalog_path.exists():
        print(f"ERROR: catalog not found: {catalog_path}", file=sys.stderr)
        sys.exit(1)

    errors = validate(catalog_path, repo_root=_REPO_ROOT)
    if errors:
        print(f"catalog.yaml validation FAILED ({len(errors)} error(s)):")
        for err in errors:
            print(f"  - {err}")
        sys.exit(1)

    print(f"catalog.yaml OK ({catalog_path})")


if __name__ == "__main__":
    main()
