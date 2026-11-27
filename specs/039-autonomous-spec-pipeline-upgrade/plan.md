# Combined Plan - 039-autonomous-spec-pipeline-upgrade

_Feature: `039-autonomous-spec-pipeline-upgrade`_
_Source Spec: `spec.md`_
_Artifact: `plan.md`_

[This template documents every section the combined `speckit.plan` step may keep. `scripts/speckit_plan_step.py` prunes unused sections after triage so the emitted `plan.md` contains only the sections required by strategy.]

## Triage

- duplicate: false
- t_shirt_size: xl
- risk_level: high
- reason: Feature 023 is a prerequisite and baseline, not a duplicate; this feature upgrades the engine and makes autonomous pre-implementation continuation, pause, resume, and implementation-ready handoff executable.

## Strategy Contract

```json
{
  "domains": {
    "reasoning": {
      "build pipeline": "The feature changes command orchestration, manifest ownership, generated artifacts, and the pre-implementation handoff route.",
      "code patterns": "The workflow must preserve Python-owned adapters, bounded command contracts, and existing repo helper patterns rather than embedding behavior in ad hoc prompts.",
      "environment": "Pinned Spec Kit CLI, project scaffolding, Codex integration paths, and clean-checkout reproduction depend on explicit environment and install contracts.",
      "observability": "Status, diagnostics, rehydration envelopes, stderr/stdout contracts, and artifact pointers are core behavior rather than optional logging.",
      "ops governance": "Ledger authority, human pause policy, approval boundaries, branch/cwd inference, and implementation handoff are governance-owned decisions.",
      "resilience": "Crash recovery, idempotent replay, loop exhaustion, leases, rollback, and resume compatibility determine whether the workflow is safe to run unattended.",
      "security": "Upstream shell runs without a capability sandbox, so allowlisting, input validation, redaction, permission classes, and protected-effect boundaries are first-class.",
      "testing": "The feature requires live engine verification, fault injection, clean-checkout rehearsal, contract tests, and clear separation between fake-only and live tests."
    },
    "relevant": [
      "build pipeline",
      "code patterns",
      "environment",
      "observability",
      "ops governance",
      "resilience",
      "security",
      "testing"
    ]
  },
  "risk": {
    "external_dependency_uncertainty": "high",
    "human_operator_dependency": "medium",
    "overall": "high",
    "repo_uncertainty": "high",
    "requirement_clarity": "medium",
    "runtime_side_effect_risk": "high",
    "state_data_migration_risk": "high"
  },
  "strategy": {
    "architecture_diagram": true,
    "architecture_strategy": true,
    "expanded_design_notes": true,
    "external_research": true,
    "net_new_surface": true,
    "strategy_reason": "The feature adds a net-new operator-facing workflow surface and spans upstream Spec Kit capabilities, repo adapters, ledgers, manifests, leases, human gates, and handoff state. Risk is high because command routing, shell safety, state recovery, upgrade reproduction, and live verification all need explicit ownership before implementation."
  },
  "triage": {
    "duplicate": false,
    "duplicate_matches": [
      "023-deterministic-phase-orchestration"
    ],
    "duplicate_reason": "Feature 023 is a prerequisite and baseline, not a duplicate; this feature upgrades the engine and makes autonomous pre-implementation continuation, pause, resume, and implementation-ready handoff executable.",
    "risk_level": "high",
    "tshirt_size": "xl"
  }
}
```

## Internal Discovery

### Term: specification

- matches: true
- exit_code: 0
- files:
  - `/Users/andreborczuk/app-foundation/scripts/validate_command_script_coverage.py`

stderr:
```text
[11/26/26 21:38:42] INFO     Processing request of type            server.py:727
                             CallToolRequest                                    
                    INFO     Processing request of type            server.py:727
                             ListToolsRequest                                   
                    INFO     Processing request of type            server.py:727
                             CallToolRequest                                    
                    INFO     vector-index: embedding 1 texts in    chroma.py:580
                             batches of 1                                       
                    INFO     vector-index: embedded 1/1 texts in   chroma.py:586
                             0.00s                                              
                    INFO     vector-index: embedding backend       chroma.py:592
                             returned 1 vectors in 0.00s                        
[11/26/26 21:38:43] INFO     Processing request of type            server.py:727
                             CallToolRequest                                    
                    INFO     HTTP Request: HEAD                  _client.py:1025
                             https://huggingface.co/BAAI/bge-rer                
                             anker-v2-m3/resolve/main/config.jso                
                             n "HTTP/1.1 307 Temporary Redirect"                
Warning: You are sending unauthenticated requests to the HF Hub. Please set a HF_TOKEN to enable higher rate limits and faster downloads.
                    WARNING  Warning: You are sending               _http.py:904
                             unauthenticated requests to the HF                 
                             Hub. Please set a HF_TOKEN to enable               
                             higher rate limits and faster                      
                             downloads.                                         
```

### Term: autonomous

- matches: true
- exit_code: 0
- files:
  - `/Users/andreborczuk/app-foundation/tests/unit/test_speckit_end_to_end_doc.py`

stderr:
```text
Building app-foundation @ file:///Users/andreborczuk/app-foundation
      Built app-foundation @ file:///Users/andreborczuk/app-foundation
Uninstalled 1 package in 0.78ms
Installed 1 package in 1ms
[11/26/26 21:38:42] INFO     Processing request of type            server.py:727
                             CallToolRequest                                    
                    INFO     Processing request of type            server.py:727
                             ListToolsRequest                                   
                    INFO     Processing request of type            server.py:727
                             CallToolRequest                                    
                    INFO     vector-index: embedding 1 texts in    chroma.py:580
                             batches of 1                                       
                    INFO     vector-index: embedded 1/1 texts in   chroma.py:586
                             0.01s                                              
                    INFO     vector-index: embedding backend       chroma.py:592
                             returned 1 vectors in 0.01s                        
[11/26/26 21:38:43] INFO     Processing request of type            server.py:727
                             CallToolRequest                                    
                    INFO     HTTP Request: HEAD                  _client.py:1025
                             https://huggingface.co/BAAI/bge-rer                
                             anker-v2-m3/resolve/main/config.jso                
                             n "HTTP/1.1 307 Temporary Redirect"                
Warning: You are sending unauthenticated requests to the HF Hub. Please set a HF_TOKEN to enable higher rate limits and faster downloads.
                    WARNING  Warning: You are sending               _http.py:904
                             unauthenticated requests to the HF                 
                             Hub. Please set
```

### Term: resumable

- matches: true
- exit_code: 0
- files:
  - `/Users/andreborczuk/app-foundation/scripts/speckit_codex_handoff_runner.py`

stderr:
```text
[11/26/26 21:38:42] INFO     Processing request of type            server.py:727
                             CallToolRequest                                    
                    INFO     Processing request of type            server.py:727
                             ListToolsRequest                                   
                    INFO     Processing request of type            server.py:727
                             CallToolRequest                                    
                    INFO     vector-index: embedding 1 texts in    chroma.py:580
                             batches of 1                                       
                    INFO     vector-index: embedded 1/1 texts in   chroma.py:586
                             0.00s                                              
                    INFO     vector-index: embedding backend       chroma.py:592
                             returned 1 vectors in 0.01s                        
[11/26/26 21:38:43] INFO     Processing request of type            server.py:727
                             CallToolRequest                                    
                    INFO     HTTP Request: HEAD                  _client.py:1025
                             https://huggingface.co/BAAI/bge-rer                
                             anker-v2-m3/resolve/main/config.jso                
                             n "HTTP/1.1 307 Temporary Redirect"                
Warning: You are sending unauthenticated requests to the HF Hub. Please set a HF_TOKEN to enable higher rate limits and faster downloads.
                    WARNING  Warning: You are sending               _http.py:904
                             unauthenticated requests to the HF                 
                             Hub. Please set a HF_TOKEN to enable               
                             higher rate limits and faster                      
                             downloads.                                         
```

### Term: spec

- matches: true
- exit_code: 0
- files:
  - `/Users/andreborczuk/app-foundation/tests/unit/test_speckit_plan_gate_routing.py`

stderr:
```text
[11/26/26 21:38:42] INFO     Processing request of type            server.py:727
                             CallToolRequest                                    
                    INFO     Processing request of type            server.py:727
                             ListToolsRequest                                   
                    INFO     Processing request of type            server.py:727
                             CallToolRequest                                    
                    INFO     vector-index: embedding 1 texts in    chroma.py:580
                             batches of 1                                       
                    INFO     vector-index: embedded 1/1 texts in   chroma.py:586
                             0.00s                                              
                    INFO     vector-index: embedding backend       chroma.py:592
                             returned 1 vectors in 0.00s                        
[11/26/26 21:38:43] INFO     Processing request of type            server.py:727
                             CallToolRequest                                    
                    INFO     HTTP Request: HEAD                  _client.py:1025
                             https://huggingface.co/BAAI/bge-rer                
                             anker-v2-m3/resolve/main/config.jso                
                             n "HTTP/1.1 307 Temporary Redirect"                
Warning: You are sending unauthenticated requests to the HF Hub. Please set a HF_TOKEN to enable higher rate limits and faster downloads.
                    WARNING  Warning: You are sending               _http.py:904
                             unauthenticated requests to the HF                 
                             Hub. Please set a HF_TOKEN to enable               
                             higher rate limits and faster                      
                             downloads.                                         
```

### Term: pipeline

- matches: true
- exit_code: 0
- files:
  - `/Users/andreborczuk/app-foundation/scripts/e2e/e2e_002_watchlist_research.sh`

stderr:
```text
[11/26/26 21:38:42] INFO     Processing request of type            server.py:727
                             CallToolRequest                                    
                    INFO     Processing request of type            server.py:727
                             ListToolsRequest                                   
                    INFO     Processing request of type            server.py:727
                             CallToolRequest                                    
                    INFO     vector-index: embedding 1 texts in    chroma.py:580
                             batches of 1                                       
                    INFO     vector-index: embedded 1/1 texts in   chroma.py:586
                             0.00s                                              
                    INFO     vector-index: embedding backend       chroma.py:592
                             returned 1 vectors in 0.00s                        
[11/26/26 21:38:43] INFO     Processing request of type            server.py:727
                             CallToolRequest                                    
                    INFO     HTTP Request: HEAD                  _client.py:1025
                             https://huggingface.co/BAAI/bge-rer                
                             anker-v2-m3/resolve/main/config.jso                
                             n "HTTP/1.1 307 Temporary Redirect"                
                    INFO     HTTP Request: HEAD                  _client.py:1025
                             https://huggingface.co/api/resolve-                
                             cache/models/BAAI/bge-reranker-v2-m                
                             3/953dc6f6f85a1b2dbfca4c34a2796e7dd                
                             e08d41e/config.json "HTTP/1.1 200                  
                             OK"                                                
                    INFO     HTTP Request: HEAD         
```

## Relevant Domains

### build pipeline
- Why it matters: The feature changes command orchestration, manifest ownership, generated artifacts, and the pre-implementation handoff route.
- Required checklist prompts:
  - [ ] Are builds reproducible with pinned dependencies and tool versions?
  - [ ] Are artifacts immutable and traceable to commit SHA + build ID?
  - [ ] Is the same artifact promoted across environments (no env-specific builds)?
  - [ ] Are dependency/vulnerability scans run for release builds (and results reviewed/blocked as needed)?
  - [ ] Is an SBOM/provenance artifact produced for production releases (where applicable)?
  - [ ] Are deploy permissions/approvals defined for production-impacting releases, and is the deploy actor attributable?
  - [ ] Are infrastructure/deployment config changes versioned and reviewed as code (where applicable)?
  - [ ] Is rollback documented and tested?
  - [ ] Are schema migrations safe with rollout sequencing (old+new compatibility / expand-contract) or explicitly coordinated?
  - [ ] Is there a post-deploy verification step (smoke/health checks)?
  - [ ] If E2E verification exists for critical flows, is it automated and executed as a release gate (not manual-only)?
  - [ ] Are rollback triggers defined (what signals cause rollback)?
  - [ ] Is a monitoring window defined (what signals, how long) before declaring success?
  - [ ] If change is high-risk, is progressive delivery used (canary/gradual rollout) or explicitly justified if not?

### code patterns
- Why it matters: The workflow must preserve Python-owned adapters, bounded command contracts, and existing repo helper patterns rather than embedding behavior in ad hoc prompts.
- Required checklist prompts:
  - [ ] Does every new public symbol have its signature (not just a comment) defined in the sketch before the task is implemented?
  - [ ] Are all new modules placed in the correct layer (domain, service, or adapter)? No cross-layer placement?
  - [ ] Does any single function in the sketch exceed 40 lines? If yes, split into smaller sub-tasks first.
  - [ ] Are there any circular imports introduced by this sketch?
  - [ ] Is any business logic (conditionals, decision-making) present in an adapter or file-IO layer? (prohibited)
  - [ ] Is any external IO (database, API, file system) called from domain or service layers? (prohibited)
  - [ ] Do all public functions have complete type hints (parameters and return type)?
  - [ ] Do all service-layer functions return typed objects, not raw dicts or tuples?
  - [ ] Are state transitions explicit and confined to named operations?
  - [ ] Are side effects isolated from decision logic?
  - [ ] Are public failure modes represented with meaningful typed errors/results?
  - [ ] Are public symbols documented (docstrings with inputs/outputs/errors and examples where non-trivial)?
  - [ ] Is formatting/lint enforcement configured as a gate (not advisory)?
  - [ ] Are error-handling conventions consistent within a module boundary (or explicitly documented if mixed)?

### environment
- Why it matters: Pinned Spec Kit CLI, project scaffolding, Codex integration paths, and clean-checkout reproduction depend on explicit environment and install contracts.
- Required checklist prompts:
  - [ ] Are all secrets loaded from the environment (not files)?
  - [ ] Are setting defaults safe for local-only development?
  - [ ] Is `config.yaml` or equivalent versioned without secrets?
  - [ ] Does startup fail on missing/invalid required configuration?
  - [ ] Is config precedence documented and deterministic?
  - [ ] Are secrets sourced from environment variables (or secret provider) and never logged?
  - [ ] Are defaults safe and environment-appropriate?
  - [ ] Do feature flags have an owner and expiry?
  - [ ] Is production behavior controlled via explicit config (not hardcoded forks)?
  - [ ] Do critical secrets/tokens have an owner and rotation expectations (cadence/trigger)?
  - [ ] Is there a safe, non-secret config fingerprint/version visible at runtime for drift detection?
  - [ ] Are old/rotated secrets revoked or invalidated where applicable?

### observability
- Why it matters: Status, diagnostics, rehydration envelopes, stderr/stdout contracts, and artifact pointers are core behavior rather than optional logging.
- Required checklist prompts:
  - [ ] Does the application emit its `run_id` on startup?
  - [ ] Is logging structured (JSON/JSONL)?
  - [ ] Do logs include enough context to diagnose a silent failure?
  - [ ] Do logs include run_id/request_id/operation_id for correlation?
  - [ ] Are key business events emitted as structured events (where applicable)?
  - [ ] Are alerts actionable and linked to a runbook/response?
  - [ ] Can stalls/missing signals be detected?
  - [ ] Do long-running build/index/embed/write paths emit stage markers, batch counts, and completion timing?
  - [ ] Are default success logs concise, with full command/path detail emitted only in explicit verbose mode?
  - [ ] Are secrets and sensitive values redacted?
  - [ ] Can critical flows be reconstructed from logs/metrics?
  - [ ] Do critical paths emit latency + error rate + throughput metrics?
  - [ ] Are saturation signals emitted for constrained resources (queues, DB locks, worker pools) where applicable?
  - [ ] Are log/metric retention windows explicit and access controlled?

### ops governance
- Why it matters: Ledger authority, human pause policy, approval boundaries, branch/cwd inference, and implementation handoff are governance-owned decisions.
- Required checklist prompts:
  - [ ] Does a complete specification (WHAT) exist before implementation?
  - [ ] Has a reuse-first approach been seriously evaluated?
  - [ ] Is versioned documentation included with the feature?
  - [ ] Is there an Architecture Flow diagram for the change?
  - [ ] Is component ownership clear?
  - [ ] Are runbooks present/updated for critical operations?
  - [ ] Is incident response/on-call responsibility defined for critical systems?
  - [ ] Are escalation and communication paths defined (where applicable)?
  - [ ] Is there an ADR (or equivalent) for major architectural decisions?
  - [ ] Are learnings fed back into specs/tests/checklists?
  - [ ] Are any rule exceptions documented with rationale and expiry?

### resilience
- Why it matters: Crash recovery, idempotent replay, loop exhaustion, leases, rollback, and resume compatibility determine whether the workflow is safe to run unattended.
- Required checklist prompts:
  - [ ] Does the system fail gracefully?
  - [ ] Is there clear observability for failure points?
  - [ ] Are retry mechanisms in place for non-critical transient errors?
  - [ ] Does ambiguous state block side effects?
  - [ ] Are degraded modes explicitly defined?
  - [ ] Are dependency exhaustion scenarios handled (timeouts, rate limits, saturation)?
  - [ ] Are retry storms prevented (bounded retries, backoff, circuit breaker)?
  - [ ] Are recovery steps documented and testable?
  - [ ] Are partial-write scenarios prevented (transactions/idempotency) during failure?
  - [ ] Is there a safe manual intervention/runbook path for stuck states?
  - [ ] Are RTO/RPO expectations stated for critical flows/state?
  - [ ] For each critical dependency, is fallback behavior explicitly defined (fail closed/open/degraded/block)?
  - [ ] Are recovery steps validated in a deterministic test or procedural drill?

### security
- Why it matters: Upstream shell runs without a capability sandbox, so allowlisting, input validation, redaction, permission classes, and protected-effect boundaries are first-class.
- Required checklist prompts:
  - [ ] Does this pull a secret/token from an environment variable (not code, logs, or committed files)?
  - [ ] Is input validation applied to all untrusted data?
  - [ ] Do all inbound webhook endpoints require authentication (no unauthenticated triggers), and are required secrets/tokens sourced from environment variables (not code or logs)?
  - [ ] Does the error message hide internal system secrets and internals?
  - [ ] Are token scopes/IAM permissions explicitly justified (least privilege)?
  - [ ] Are dependencies scanned for known vulnerabilities where applicable?
  - [ ] For new trust boundaries/integrations/privileged capabilities, was a threat model performed and documented?
  - [ ] Are threat mitigations reflected in tests/checklists (not only in prose)?

### testing
- Why it matters: The feature requires live engine verification, fault injection, clean-checkout rehearsal, contract tests, and clear separation between fake-only and live tests.
- Required checklist prompts:
  - [ ] Does a deterministic pass/fail oracle exist for this?
  - [ ] If yes, is it implemented as an automated gate (not manual confirmation)?
  - [ ] Are E2E tests run on real infrastructure where critical paths require it (not mocks)?
  - [ ] Is TDD methodology used (test written first) or explicitly justified if not?
  - [ ] Are tests deterministic (no timing races / hidden randomness / external nondeterminism)?
  - [ ] Are flaky tests tracked with an owner and expiry if temporarily quarantined?
  - [ ] Does every bug fix include a regression test targeting the bug class?
  - [ ] Are state transitions (including retries/duplicates/out-of-order) tested where applicable?
  - [ ] Is there at least one reality-check integration test for critical paths?
  - [ ] Are any gate waivers documented with rationale and expiry?
  - [ ] If E2E gates exist, is the E2E environment production-like or are differences explicitly documented?
  - [ ] Are fixtures/test accounts representative of real edge cases and permission models?

## Summary

Upgrade the repository from one-phase driver dispatch to a durable Spec Kit `v1.4.5` workflow cursor while preserving repository-owned templates, commands, validation gates, ledgers, and implementation boundaries. Keep the existing pipeline driver as the phase adapter and event bridge, add safe workflow and command adapters around it, and finish with a reconciled implementation-ready handoff rather than starting implementation automatically.

## Internal Research

- Feature 023 already defines deterministic phase routing, validate-before-emit behavior, feature locking helpers, and idempotent pipeline event append; feature 039 is a completion and migration layer, not a second orchestrator.
- The current driver selects and executes one ledger-authoritative phase per process. Its Specify route invokes the adapter as an executable, while the tracked file is not executable and its entrypoint still requires a new description instead of honoring the existing-feature arguments.
- Plan, Solution, and phase-gate helpers already provide useful deterministic artifact contracts, but their direct workflow composition and result/event correlation are incomplete.
- The two command-manifest copies describe route ownership but have divergent outer and inner version metadata and do not yet model one complete durable multi-step workflow.
- Pipeline and task ledgers remain the completion authority. Upstream workflow status and logs are cursor and telemetry evidence, not substitutes for repository validation or lifecycle events.
- Existing Codex skills, Claude commands, Specify templates, and repository scripts are custom assets that must move through supported package or overlay seams and survive upgrade rehearsal byte-for-byte or through an explicitly reviewed render transformation.
- The generic handoff runner has implementation-oriented side effects, so pre-implementation orchestration must explicitly prohibit staging, committing, pushing, publishing, deploying, or beginning implementation.

## External Research

- Pin the upgrade target to the immutable Spec Kit `v1.4.5` release verified in the specification; do not float to `main` or `latest` without a reviewed specification amendment.
- Use upstream command, prompt, shell, gate, conditional, loop, fan-out/fan-in, and nested-workflow steps only through repository-owned adapters and policies.
- Wrap effective shell work in fixed executable and argv contracts because upstream shell execution runs with user privileges and no capability sandbox.
- Treat upstream status and resume as the durable workflow cursor while retaining pipeline and task ledgers as the only phase and task completion authority.
- Make every replayable effect idempotent: completed occurrences are retained, but interrupted effects before their completion checkpoint can repeat.
- Require deterministic post-loop assertions because reaching a maximum iteration count does not prove convergence or failure.
- Use the machine-readable version-and-features command as the capability preflight and explicit project and feature targeting instead of unattended branch or cwd inference.
- Package repository customizations through supported presets, extensions, overlays, custom step packages, and bundles so a clean install can restore existing templates and workflow steps.

## Architecture Strategy

Use a layered orchestration model with one upstream workflow cursor and narrow repository adapters:

- Upstream Spec Kit owns run identity, the durable execution tree, step cursor, structured control flow, status, and resume.
- The repository workflow adapter translates upstream step results into the existing phase contract.
- Repository phase adapters own artifact generation, deterministic validation, bounded diagnostics, result shaping, and event requests.
- The ledger bridge owns idempotent append and reconciliation through the existing pipeline and task ledger interfaces only.
- The command adapter owns safe execution using fixed Python executable and argv contracts, validated inputs, root-bounded cwd, timeouts, output caps, redaction, and permission classes.
- Human policy owns reason-code classification, pause-before-effect rules, authority requirements, and typed resume input validation.
- Lease handling owns renewable single-flight feature execution across start, continuation, pause, resume, expiry, and crash recovery.
- The handoff adapter produces one compact implementation-ready envelope with pointers to full artifacts and diagnostics for the separate implementation workflow.

Migrate route-by-route. A route becomes active only when its manifest ownership, workflow step, adapter, validator, event, runtime result, replay behavior, and live verification agree.

## Architecture Diagram

Prompt or existing feature
→ canonical speckit.run trigger
→ Spec Kit v1.4.5 durable workflow cursor
→ repository workflow adapter
→ phase adapter plus custom template
→ generation or deterministic action
→ phase-specific validator
→ pass: idempotent ledger bridge and state reconciliation
→ recoverable: bounded repair loop back to generation
→ human required: durable pause envelope
→ terminal failure: bounded failure envelope
→ solution complete: implementation-ready handoff
→ separate implement workflow

## Expanded Design Notes

The design must enforce these rules:

- Capability and migration preflight happens before mutation and records installed versions, workflow features, project integration, customization inventory, and the pinned target.
- Repository-owned templates, commands, skills, scripts, overlays, and workflow definitions must survive clean-install rehearsal or an explicitly reviewed transformation.
- Every effectful step declares identity, inputs, outputs, validator, effect scope, timeout, permission class, idempotency key, and redaction behavior.
- Repair loops consume the latest persisted validator result and terminate in a deterministic success, retry, human-pause, or terminal-failure assertion.
- One status operation returns run identity, phase and attempt, last validated event, pending reason, permitted action, version compatibility, lease state, and artifact pointers without depending on chat history.
- Reconciliation compares workflow state, ledgers, planning evidence, runtime results, manifest route, versions, artifacts, and lease before any new effect. Drift blocks execution and returns one non-mutating next action.
- Human pauses occur before the protected effect. Resume input is typed, correlated, authorized, fresh, narrowly scoped, and secret-safe.
- Installation and rollback are rehearsed in isolation and in a clean checkout. Rollback does not rewrite ledger history or feature artifacts.
- The terminal output is an implementation-ready envelope and cannot execute tasks, stage or commit implementation work, push, publish, deploy, merge, or contact external systems as implementation side effects.

## Design Slices

### Slice PL-01 - Pin and Rehearse the Spec Kit Upgrade
- Estimate: high
- Implementation Directive: Build the non-mutating capability and migration preflight for pinned Spec Kit `v1.4.5`, including current CLI, project, and customization inventory; isolated install rehearsal; clean-checkout reproduction proof; feature validation; and rollback that preserves artifacts and ledger history.

### Slice PL-02 - Define Workflow Ownership and Manifest Routing
- Estimate: high
- Implementation Directive: Make one validated manifest contract authoritative for workflow ownership, route status, step mapping, adapter, timeout, permission class, artifact, validator, event, version, and provenance while retaining supported Codex and Claude entry surfaces.

### Slice PL-03 - Build the Safe Command Adapter
- Estimate: high
- Implementation Directive: Implement a repository-owned adapter behind upstream shell steps using fixed executable and argv contracts, validated structured inputs, root-bounded cwd, timeouts, output caps, redaction, structured results, permission classes, and rejection of unreviewed effective commands.

### Slice PL-04 - Wire Pre-Implementation Phase Adapters
- Estimate: high
- Implementation Directive: Connect Specify, Plan, and Solution so each phase declares its custom template or scaffold, generation action, output, mutation scope, validator, diagnostics, success event, and side-effect contract; scaffold-only or failed artifacts never emit success.

### Slice PL-05 - Add Outcome, Loop, and Human-Pause Policy
- Estimate: high
- Implementation Directive: Add structured outcome classification, bounded repair and convergence loops, post-loop assertions, human reason codes, pause-before-effect behavior, and typed resume input validation for every protected decision.

### Slice PL-06 - Add Resume, Reconciliation, Lease, and Handoff State
- Estimate: high
- Implementation Directive: Correlate workflow cursor, ledgers, runtime results, artifacts, manifest, versions, attempts, actor, and renewable feature lease; enforce idempotent replay and drift blocking; and emit one compact implementation-ready handoff envelope.

### Slice PL-07 - Prove Live Prompt-to-Handoff Safety
- Estimate: high
- Implementation Directive: Add unit and contract coverage plus live pinned-engine verification, fault injection, security fixtures, clean-install rehearsal, rollback proof, and explicit fake-only test labeling so the prompt-to-handoff path is proven without starting implementation.

## Plan Completion Summary

The full XL and high-risk plan path is required because the feature adds an operator-facing workflow surface and crosses an upstream engine, local customization packaging, command safety, ledger authority, leases, replay, and live verification. The seven slices define ownership and tasking-ready implementation boundaries while retaining the terminal boundary at an implementation-ready handoff. The Solution phase should convert these slices into ordered, independently verifiable tasks and stop before executing any implementation task.
