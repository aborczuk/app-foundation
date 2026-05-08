from __future__ import annotations

import json
from pathlib import Path

import scripts.speckit_plan_step as plan_step


def _write_plan_template(repo_root: Path) -> None:
    """Create the documented superset plan template used by the scaffold helper."""
    template_file = repo_root / ".specify" / "templates" / "plan-template.md"
    template_file.parent.mkdir(parents=True, exist_ok=True)
    template_file.write_text(
        "\n".join(
            [
                "# Combined Plan - [FEATURE_NAME]",
                "",
                "_Feature: `[FEATURE_ID]`_",
                "_Source Spec: `[SPEC_FILE_NAME]`_",
                "_Artifact: `plan.md`_",
                "",
                "## Triage",
                "",
                "- duplicate: [true/false]",
                "",
                "## Strategy Contract",
                "",
                "```json",
                "{}",
                "```",
                "",
                "## Internal Discovery",
                "",
                "[internal discovery]",
                "",
                "## Relevant Domains",
                "",
                "[relevant domains]",
                "",
                "## Summary",
                "",
                "[summary]",
                "",
                "## Internal Research",
                "",
                "[internal research]",
                "",
                "## External Research",
                "",
                "[external research]",
                "",
                "## Architecture Strategy",
                "",
                "[architecture strategy]",
                "",
                "## Architecture Diagram",
                "",
                "[architecture diagram]",
                "",
                "## Expanded Design Notes",
                "",
                "[expanded design notes]",
                "",
                "## Design Slices",
                "",
                "[design slices]",
                "",
                "## Plan Completion Summary",
                "",
                "[completion summary]",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _write_feature(tmp_path: Path) -> tuple[Path, Path]:
    """Create a minimal feature directory and return the feature and plan paths."""
    feature_dir = tmp_path / "specs" / "123-test-feature"
    feature_dir.mkdir(parents=True)
    (feature_dir / "spec.md").write_text(
        "# Feature\n\nBuild a playable Tetris game in the app.\n",
        encoding="utf-8",
    )
    return feature_dir, feature_dir / "plan.md"


def _write_contract(
    plan_file: Path,
    *,
    duplicate: bool,
    relevant_domains: list[str] | None = None,
    architecture_strategy: bool = False,
    external_research: bool = False,
    net_new_surface: bool = False,
    architecture_diagram: bool = False,
    expanded_design_notes: bool = False,
    risk_level: str = "low",
) -> None:
    """Write a combined strategy contract into plan.md."""
    domains = list(relevant_domains or [])
    plan_file.write_text(
        "\n".join(
            [
                "# Combined Plan",
                "",
                "## Triage",
                "",
                f"- duplicate: {str(duplicate).lower()}",
                "",
                "## Strategy Contract",
                "",
                "```json",
                json.dumps(
                    {
                        "domains": {
                            "relevant": domains,
                            "reasoning": {
                                domain: f"{domain} requires explicit planning treatment."
                                for domain in domains
                            },
                        },
                        "triage": {
                            "duplicate": duplicate,
                            "duplicate_reason": "Existing feature covers this." if duplicate else "",
                            "duplicate_matches": ["specs/001-existing/spec.md"] if duplicate else [],
                            "risk_level": risk_level,
                            "tshirt_size": "xs" if duplicate else "s",
                        },
                        "strategy": {
                            "architecture_diagram": architecture_diagram,
                            "architecture_strategy": architecture_strategy,
                            "expanded_design_notes": expanded_design_notes,
                            "external_research": external_research,
                            "net_new_surface": net_new_surface,
                            "strategy_reason": "Plan only the sections justified by domains, size, and risk.",
                        },
                        "risk": {
                            "overall": risk_level,
                            "requirement_clarity": "low",
                            "repo_uncertainty": "low",
                            "external_dependency_uncertainty": "low",
                            "state_data_migration_risk": "low",
                            "runtime_side_effect_risk": "low",
                            "human_operator_dependency": "low",
                        },
                    },
                    sort_keys=True,
                ),
                "```",
                "",
                "## Internal Discovery",
                "",
                "### Term: tetris",
                "",
                "- matches: true",
                "- exit_code: 0",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def test_extract_terms_filters_generic_words() -> None:
    """Discovery terms should keep signal and skip generic filler words."""
    assert plan_step._extract_terms("Build a playable Tetris game in the app.") == ["tetris"]


def test_run_discovery_uses_semantic_context_lookup(monkeypatch) -> None:
    """Discovery should call the semantic read helper, not a structural content search."""
    calls: list[tuple[tuple[str, ...], dict[str, str]]] = []

    def fake_run_uv_command(args: list[str], *, env: dict[str, str], **_: object):
        calls.append((tuple(args), env))

        class Result:
            returncode = 0
            stdout = "file_path: /repo/src/example.py"
            stderr = ""

        return Result()

    monkeypatch.setattr(plan_step, "_run_uv_command", fake_run_uv_command)

    results = plan_step._run_discovery(["tetris"], {"TEST_ENV": "1"})

    assert results[0]["has_matches"] is True
    assert calls == [
        (
            ("uv", "run", "python", "scripts/read_code.py", "context", "tetris"),
            {"TEST_ENV": "1"},
        )
    ]


def test_prepare_triage_scaffolds_only_minimal_sections(monkeypatch, tmp_path: Path) -> None:
    """Triage preparation should write only the triage-first scaffold."""
    feature_dir, plan_file = _write_feature(tmp_path)
    _write_plan_template(tmp_path)

    monkeypatch.setattr(plan_step, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(plan_step, "bootstrap_session", lambda _: {"bootstrap_ok": True})
    monkeypatch.setattr(
        plan_step,
        "_resolve_feature_paths",
        lambda feature_id: (feature_dir, feature_dir / "spec.md", plan_file),
    )
    monkeypatch.setattr(plan_step, "_build_uv_env", lambda: {"TEST_ENV": "1"})
    monkeypatch.setattr(
        plan_step,
        "_run_discovery",
        lambda terms, env: [
            {
                "term": terms[0],
                "exit_code": 0,
                "stdout": "file_path: /repo/src/example.py",
                "stderr": "",
                "has_matches": True,
            }
        ],
    )
    monkeypatch.setattr(plan_step, "_scaffold_manifest_plan", lambda _: None)

    result = plan_step.prepare_triage("123")

    text = plan_file.read_text(encoding="utf-8")
    assert result["command"] == "prepare-triage"
    assert "## Triage" in text
    assert "## Strategy Contract" in text
    assert "## Internal Discovery" in text
    assert "## Relevant Domains" not in text
    assert "## Summary" not in text
    assert "## Design Slices" not in text


def test_apply_strategy_rewrites_only_selected_sections(monkeypatch, tmp_path: Path) -> None:
    """Strategy rewrite should add only the sections justified by triage."""
    feature_dir, plan_file = _write_feature(tmp_path)
    _write_plan_template(tmp_path)
    monkeypatch.setattr(plan_step, "REPO_ROOT", tmp_path)
    _write_contract(
        plan_file,
        duplicate=False,
        relevant_domains=["api integration", "storage"],
        architecture_strategy=True,
        external_research=True,
        architecture_diagram=True,
        expanded_design_notes=True,
        risk_level="high",
    )
    monkeypatch.setattr(
        plan_step,
        "_resolve_feature_paths",
        lambda feature_id: (feature_dir, feature_dir / "spec.md", plan_file),
    )

    result = plan_step.apply_strategy("123")

    text = plan_file.read_text(encoding="utf-8")
    assert result["rewritten"] is True
    assert result["selected_sections"] == [
        "Summary",
        "Relevant Domains",
        "Internal Research",
        "External Research",
        "Architecture Strategy",
        "Architecture Diagram",
        "Expanded Design Notes",
        "Design Slices",
        "Plan Completion Summary",
    ]
    assert "## Relevant Domains" in text
    assert "## External Research" in text
    assert "## Architecture Diagram" in text
    assert "## Expanded Design Notes" in text
    assert "## Plan Completion Summary" in text


def test_normalize_contract_forces_external_research_for_net_new_surface() -> None:
    """Net-new features or surfaces must force external research on in strategy."""
    contract = plan_step._normalize_contract(
        {
            "triage": {"duplicate": False, "risk_level": "medium", "tshirt_size": "m"},
            "domains": {"relevant": ["observability"], "reasoning": {"observability": "new surface"}},
            "strategy": {
                "external_research": False,
                "net_new_surface": True,
                "architecture_strategy": False,
                "architecture_diagram": False,
                "expanded_design_notes": False,
                "strategy_reason": "Net new surface requires outside precedent research.",
            },
            "risk": {"overall": "medium"},
        }
    )

    assert contract["strategy"]["net_new_surface"] is True
    assert contract["strategy"]["external_research"] is True


def test_finalize_duplicate_requests_duplicate_marked(monkeypatch, tmp_path: Path) -> None:
    """Duplicate finalization should emit one duplicate-marked driver request."""
    feature_dir, plan_file = _write_feature(tmp_path)
    _write_contract(plan_file, duplicate=True)
    plan_file.write_text(
        plan_file.read_text(encoding="utf-8") + "## Plan Completion Summary\n\nDuplicate.\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(plan_step, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        plan_step,
        "_resolve_feature_paths",
        lambda feature_id: (feature_dir, feature_dir / "spec.md", plan_file),
    )

    result = plan_step.finalize_plan("123", "run-123:plan")

    assert result["next_phase"] == "closed"
    assert result["pipeline_event_request"]["event"] == "duplicate_marked"
    assert result["feature_dir"] == str(feature_dir)
    assert result["plan_artifact"] == str(plan_file)
    assert result["spec_artifact"] == str(feature_dir / "spec.json")
    assert (feature_dir / "spec.json").is_file()


def test_finalize_nonduplicate_requires_design_slice_and_requests_plan_approved(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Non-duplicate finalization should require one tasking-ready design slice."""
    feature_dir, plan_file = _write_feature(tmp_path)
    _write_contract(plan_file, duplicate=False)
    plan_file.write_text(
        plan_file.read_text(encoding="utf-8")
        + "\n".join(
            [
                "## Design Slices",
                "",
                "### Slice PL-01 - Initial gameplay loop",
                "",
                "- LOE: low",
                "- Goal: Implement the smallest playable loop.",
                "- Files / seams: `src/app.py`",
                "- Implementation Directive: Build the first end-to-end slice before adding polish.",
                "",
                "## Plan Completion Summary",
                "",
                "One low-estimated slice is enough for tasking.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(plan_step, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        plan_step,
        "_resolve_feature_paths",
        lambda feature_id: (feature_dir, feature_dir / "spec.md", plan_file),
    )

    result = plan_step.finalize_plan("123", "run-123:plan")

    assert result["next_phase"] == "solution"
    assert result["pipeline_event_request"]["event"] == "plan_approved"
    assert result["pipeline_event_request"]["fields"]["routing"]["plan_level"] == "simple"
    assert result["pipeline_event_request"]["fields"]["triage"]["tshirt_size"] == "s"
    assert result["pipeline_event_request"]["fields"]["design_slices"][0]["slice_id"] == "PL-01"
    routing_payload = json.loads((feature_dir / "spec.json").read_text(encoding="utf-8"))
    assert routing_payload["design_slices"][0]["slice_id"] == "PL-01"
    assert routing_payload["tasking"]["mode"] == "generative"
