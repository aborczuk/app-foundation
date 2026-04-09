---
feature_id: "[FEATURE_ID]"
task_id: "[TASK_ID]"
is_human_task: true
---

# HUD: [TASK_ID] [H] — [DESCRIPTION]

## Runbook

**System**: [name of external system]  
**Steps**:
1. [Exact step]
2. [Exact step]

**Verification command**: [shell command or automated check confirming completion]

## Functional Goal

**Story Goal**: [from tasks.md phase header]  
**Blocks**: [implementation task IDs that cannot proceed until this is verified]

## Process Checklist

- [ ] human_action_started
- [ ] human_action_verified
- [ ] task_closed
