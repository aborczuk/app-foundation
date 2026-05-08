"""Tests for HUD scaffold and validation helpers."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def _load_module():
    """Import the HUD helper as a module."""
    module_path = Path("scripts/speckit_remake_huds.py")
    spec = importlib.util.spec_from_file_location("testable_speckit_remake_huds", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_feature_fixture(feature_dir: Path) -> None:
    """Create a minimal feature fixture for HUD scaffold tests."""
    (feature_dir / "spec.md").write_text(
        """# Spec

## User Scenarios & Testing *(mandatory)*

### User Story 3 - Reach Game Over and Restart (Priority: P3)

A user can recognize a lost game and immediately start a fresh one.

**Independent Test**: Drive the board to a blocked spawn state, confirm game-over behavior freezes mutation, then restart and verify board and score reset.

**Acceptance Scenarios**:

1. **Given** the stack reaches the spawn area, **When** a new piece cannot be placed legally, **Then** the session enters a game-over state.
2. **Given** the session is over, **When** the user views the end state, **Then** the score remains visible and active controls no longer mutate the ended board.
3. **Given** the session is over, **When** the user chooses restart, **Then** a new session begins with reset board state and reset score.

### Edge Cases

- Game over must trigger only when a new piece cannot spawn legally, not during normal stacking.
""",
        encoding="utf-8",
    )
    (feature_dir / "tasks.md").write_text(
        """# Tasks

## Phase 5: User Story 3 - Reach Game Over and Restart (Priority: P3)

### Tests for User Story 3

- [ ] T012 [P] [US3] Add unit coverage for blocked-spawn game over and full-session restart reset in `tests/unit/test_demo.py` — `tests/unit/test_demo.py:test_game_over_and_restart`
- [ ] T013 [P] [US3] Add integration coverage for game-over display and restart flow at the HTTP/runtime seam in `tests/integration/test_demo.py` — `tests/integration/test_demo.py:test_game_over_and_restart_flow`

### Implementation for User Story 3

- [ ] T015 [US3] Implement restart endpoint/state reset and browser restart affordance in `src/demo/router.py`, `src/demo/templates/tetris.html`, and `src/demo/static/tetris.js` — `src/demo/router.py:restart_tetris_session`

## Phase 6: Polish & Cross-Cutting Verification

- [ ] T016 Add plan-to-task trace notes and scenario coverage references in `specs/999-demo/tasks.md` and generated HUDs — `specs/999-demo/tasks.md:traceability`

## Dependency Order

- T010, T011 -> T012, T013, T015
- T012, T013, T015 -> T016
""",
        encoding="utf-8",
    )
    (feature_dir / "spec.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "domains": {
                    "reasoning": {
                        "client/UI": "Restart changes the user-visible control surface and end-state feedback.",
                        "edge delivery": "Restart crosses the route/browser boundary.",
                        "testing": "Game-over and restart require deterministic regressions.",
                        "code patterns": "Restart must route through an authoritative session-state transition.",
                    }
                },
                "design_slices": [
                    {
                        "slice_id": "PL-01",
                        "title": "Tetris Runtime Surface",
                        "estimate": "medium",
                        "why": "Needs an isolated runtime seam.",
                        "file_symbol_seams": ["src/demo/router.py:restart_tetris_session"],
                        "implementation_directive": "Keep the route contract isolated and deterministic.",
                    },
                    {
                        "slice_id": "PL-03",
                        "title": "Playable Browser Shell",
                        "estimate": "high",
                        "why": "Needs browser restart UX.",
                        "file_symbol_seams": ["src/demo/templates/tetris.html", "src/demo/static/tetris.js"],
                        "implementation_directive": "Update the browser shell for restart and game-over display.",
                    },
                ],
                "routing": {"plan_level": "core", "sketch_level": "expanded"},
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    hud_dir = feature_dir / "huds"
    hud_dir.mkdir()
    (hud_dir / "T015.md").write_text(
        """---
feature_id: "999"
task_id: "T015"
---

# HUD: T015 - old

## Working Memory

**Callers**: Resolve during implement discovery via codegraph caller query for this symbol.
""",
        encoding="utf-8",
    )


def test_prepare_scaffolds_huds_from_explicit_task_facts(tmp_path: Path, monkeypatch) -> None:
    """Prepare should scaffold code HUDs without deterministic classification decisions."""
    module = _load_module()
    feature_dir = tmp_path / "999-demo"
    feature_dir.mkdir()
    _write_feature_fixture(feature_dir)
    monkeypatch.chdir(tmp_path)

    exit_code = module.main(["prepare", "--feature-dir", str(feature_dir), "--json"])

    assert exit_code == 0
    content = (feature_dir / "huds/T015.md").read_text(encoding="utf-8")
    assert 'task_id: "T015"' in content
    assert 'story_id: "US3"' in content
    assert 'primary_edit_seam: "src/demo/router.py:restart_tetris_session"' in content
    assert "## Candidate Design Slices" in content
    assert "## Proposed Solution" in content
    assert "## Acceptance Criteria" in content
    assert "[FILL: describe current repo behavior" in content
    assert "[FILL: attach the exact design slice title(s), directive(s), and seam(s) that apply to this task.]" in content
    assert "classification:" not in content
    assert "## Quality Guards" not in content
    assert "Resolve during implement discovery" not in content


def test_prepare_scaffolds_doc_tasks_without_shortcuts(tmp_path: Path, monkeypatch) -> None:
    """Documentation seams should still be emitted as fillable scaffolds."""
    module = _load_module()
    feature_dir = tmp_path / "999-demo"
    feature_dir.mkdir()
    _write_feature_fixture(feature_dir)
    monkeypatch.chdir(tmp_path)

    module.main(["prepare", "--feature-dir", str(feature_dir)])

    content = (feature_dir / "huds/T016.md").read_text(encoding="utf-8")
    assert 'task_id: "T016"' in content
    assert "## Acceptance Criteria" in content
    assert "[FILL:" in content
    assert "classification:" not in content


def test_prepare_keeps_missing_seam_inside_hud(tmp_path: Path, monkeypatch) -> None:
    """A missing task seam should stay unresolved inside the HUD instead of pointing back to tasks.md."""
    module = _load_module()
    feature_dir = tmp_path / "999-demo"
    feature_dir.mkdir()
    _write_feature_fixture(feature_dir)
    monkeypatch.chdir(tmp_path)

    tasks_path = feature_dir / "tasks.md"
    tasks_text = tasks_path.read_text(encoding="utf-8")
    tasks_text = tasks_text.replace(
        "- [ ] T015 [US3] Implement restart endpoint/state reset and browser restart affordance in `src/demo/router.py`, `src/demo/templates/tetris.html`, and `src/demo/static/tetris.js` — `src/demo/router.py:restart_tetris_session`",
        "- [ ] T015 [US3] Implement restart endpoint/state reset and browser restart affordance in `src/demo/router.py`, `src/demo/templates/tetris.html`, and `src/demo/static/tetris.js`",
    )
    tasks_path.write_text(tasks_text, encoding="utf-8")

    module.main(["prepare", "--feature-dir", str(feature_dir)])

    content = (feature_dir / "huds/T015.md").read_text(encoding="utf-8")
    assert "primary_edit_seam: null" in content
    assert "[resolve from tasks.md annotation]" not in content
    assert "**File:Symbol**: [FILL: no explicit file:symbol seam was declared in tasks.md. Set the primary seam here.]" in content
    assert "- [FILL: concrete change required in `src/demo/router.py`.]" in content
    assert "- `src/demo/router.py` - [FILL: specific intended change.]" in content


def test_validate_rejects_unfilled_scaffolds(tmp_path: Path, monkeypatch) -> None:
    """Validation should fail while scaffold placeholders remain."""
    module = _load_module()
    feature_dir = tmp_path / "999-demo"
    feature_dir.mkdir()
    _write_feature_fixture(feature_dir)
    monkeypatch.chdir(tmp_path)

    module.main(["prepare", "--feature-dir", str(feature_dir)])
    exit_code = module.main(["validate", "--feature-dir", str(feature_dir), "--json"])

    assert exit_code == 2
