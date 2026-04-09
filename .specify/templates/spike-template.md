# Feasibility Spike: [FEATURE NAME]

**Date**: [DATE] | **Outcome**: CONFIRMED / FAILED / INCONCLUSIVE
**Feature**: `[###-feature-name]` | **Run by**: `/speckit.feasibilityspike`

## Summary

[One paragraph: which questions were probed, what was confirmed or failed, and whether the architecture can proceed as planned. If any question failed, name the architecture revision required.]

---

## Questions Probed

<!--
  One section per FQ-NNN from plan.md ## Open Feasibility Questions.
  Copy the question text verbatim.
-->

### FQ-001: [Question text from plan.md]

**Probe type**: [code experiment / API call / subprocess test / library import test / service availability check]

**Probe**:
```
[exact command or minimal code snippet that was run]
```

**Result**: CONFIRMED / FAILED / INCONCLUSIVE

**Evidence**:
```
[stdout/stderr output, max ~20 lines]
```

**Architecture implication**: [CONFIRMED: "proceed as planned" | FAILED: "architecture must be revised — see Failed Questions below" | INCONCLUSIVE: "human confirmation required"]

---

## Technology Selection

<!--
  Filled only when ALL questions are CONFIRMED or N/A.
  Left blank/TBD if any question is FAILED or INCONCLUSIVE.
  This table is copied into plan.md ## Technology Selection by /speckit.feasibilityspike.
-->

| Category | Selection | Version | Confirmed by |
|----------|-----------|---------|--------------|
| [e.g., async IBKR connectivity] | [e.g., ib-async] | [e.g., 2.1.0] | FQ-001 |

---

## Failed Questions — Architecture Revision Required

<!--
  Only fill this section if any FQ result is FAILED.
  Leave empty (and remove this section) if all questions confirmed.
-->

| FQ | What the probe showed | Recommended alternative |
|----|-----------------------|------------------------|
| FQ-001 | [failure evidence summary] | [alternative architecture to evaluate] |

**Next step**: Re-run `/speckit.plan` with the failure evidence above. Revise architecture to avoid the failing assumption. Then re-run `/speckit.feasibilityspike`.
