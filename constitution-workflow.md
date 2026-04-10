# ib-trading Pipeline Workflow (State Machine)

This is the authoritative, **hard-gated** step order for every new feature. Behavior is physically blocked by artifact existence at each gate.

```mermaid
graph TD
    %% Phase 1: Discovery & Definition
    START((Start)) --> Specify["/speckit.specify<br/>(WHAT)"]
    Specify --> spec_md[spec.md]
    spec_md --> Clarify["/speckit.clarify<br/>(Resolve Ambig.)"]

    %% Phase 2: Architecture & Research (THE HARD GATE)
    spec_md --> Research["/speckit.research<br/>(ZERO-SERVER CHECK)"]
    Research --> research_md[research.md]

    %% Phase 3: Planning
    research_md & spec_md --> Plan["/speckit.plan<br/>(HOW)"]
    Plan --> plan_md[plan.md]
    plan_md --> PlanReview["/speckit.planreview<br/>(Audit Plan)"]

    %% Phase 3b: Feasibility (sub-process of plan — runs after planreview)
    plan_md --> FeasibilitySpike["/speckit.feasibilityspike<br/>(Prove FQs)"]
    FeasibilitySpike --> plan_approved[plan_approved]

    %% Phase 4: Solution (sketch-first)
    plan_approved --> Solution["/speckit.solution<br/>(LLD Phase)"]
    Solution --> Sketch["/speckit.sketch<br/>(Blueprint)"]
    Sketch --> sketch_md[sketch.md]
    sketch_md --> SolReview["/speckit.solutionreview<br/>(Sketch Gate)"]
    SolReview -->|CRITICAL findings| Sketch
    SolReview -->|pass| Tasking["/speckit.tasking<br/>(Task Decomposition)"]

    %% Tasking internal subprocess loop
    Tasking --> Estimate["/speckit.estimate<br/>(Fibonacci)"]
    Estimate -->|8/13 warnings| Breakdown["/speckit.breakdown<br/>(Split > 5pts)"]
    Breakdown --> Tasking

    %% Tasking outputs after stabilization
    Tasking --> tasks_md[tasks.md]
    Tasking --> huds[.speckit/tasks/*.md]
    Tasking --> acceptance[.speckit/acceptance-tests/story-N.py]
    Tasking --> solution_approved[solution_approved]

    %% Phase 5: Post-solution analysis (separate event)
    solution_approved --> Analyze["/speckit.analyze<br/>(Drift: spec→plan→sketch→tasks)"]
    Analyze --> analysis_completed[analysis_completed]

    %% Phase 6: Pre-Flight
    analysis_completed & tasks_md & plan_md --> E2E["/speckit.e2e<br/>(Automation Script)"]
    E2E --> e2e_md[e2e.md]
    E2E --> e2e_script[scripts/e2e_slug.sh]

    %% Phase 7: Implementation
    e2e_script & e2e_md & tasks_md --> Implement["/speckit.implement<br/>(CODE & HUD)"]

    %% Phase 8: Verification
    Implement --> Checkpoint["/speckit.checkpoint<br/>(Phase Test)"]
    Implement --> E2E_Run["/speckit.e2e-run<br/>(Validation)"]
    E2E_Run --> QA_Sentry["scripts/offline_qa.py<br/>(Signature Required)"]
    QA_Sentry --> task_closed[task_closed event]
```

For structured command metadata (input artifacts, output artifacts, audit events), see the **Full Feature Pipeline Matrix** in `constitution.md`.
