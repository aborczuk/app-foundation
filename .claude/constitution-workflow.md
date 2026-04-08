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

    %% Phase 4: Solution (LLD — hard-blocks if Open Feasibility Questions non-empty)
    plan_approved --> Solution["/speckit.solution<br/>(LLD Phase)"]
    Solution --> Tasking["/speckit.tasking<br/>(Task Breakdown)"]
    Solution --> Sketch["/speckit.sketch<br/>(Sketches + Tests)"]
    Solution --> Estimate["/speckit.estimate<br/>(Fibonacci)"]
    Estimate --> Breakdown["/speckit.breakdown<br/>(Split > 5pts)"]
    Solution --> SolReview["/speckit.solutionreview<br/>(Quality Gate)"]
    SolReview --> tasks_md[tasks.md]
    
    %% Phase 5: Pre-Flight (THE CRITICAL GATES)
    tasks_md & plan_md --> Analyze["/speckit.analyze<br/>(Consistency)"]
    tasks_md & plan_md --> E2E["/speckit.e2e<br/>(Automation Script)"]
    E2E --> e2e_md[e2e.md]
    E2E --> e2e_script[scripts/e2e_slug.sh]
    
    %% Phase 6: Implementation
    Analyze & e2e_script & e2e_md & tasks_md --> Implement["/speckit.implement<br/>(CODE & HUD)"]
    
    %% Phase 7: Verification
    Implement --> Checkpoint["/speckit.checkpoint<br/>(Phase Test)"]
    Implement --> E2E_Run["/speckit.e2e-run<br/>(Validation)"]
    E2E_Run --> QA_Sentry["scripts/offline_qa.py<br/>(Signature Required)"]
    QA_Sentry --> task_closed[task_closed event]
```

For structured command metadata (input artifacts, output artifacts, audit events), see the **Full Feature Pipeline Matrix** in `constitution.md`.
