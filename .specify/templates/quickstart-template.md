# Quickstart: [FEATURE NAME]

Get the feature running locally in [X minutes].

---

## Prerequisites

- [Requirement 1]: [how to check/install]
- [Requirement 2]: [how to check/install]
- [External service]: [how to set up or verify it's running]

---

## Installation

### 1. Clone and set up environment

```bash
git clone <repo-url>
cd <repo>
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env with your settings
```

### 3. Run migrations / setup (if needed)

```bash
[Command to set up databases, fixtures, etc.]
```

---

## Run the Feature

```bash
# [Describe how to start/run the feature]
[command to run]

# Output should look like:
# [Example output]
```

---

## Smoke Test

Verify the feature is working:

```bash
# [Test command 1]
[command]
# Expected: [output]

# [Test command 2]
[command]
# Expected: [output]
```

---

## Common Issues

| Issue | Symptom | Fix |
|-------|---------|-----|
| [Issue 1] | [What you see] | [How to resolve] |
| [Issue 2] | [What you see] | [How to resolve] |

---

## Next Steps

- Read [Feature Name] specification: [link to spec.md]
- Run the full E2E test: `scripts/e2e_<slug>.sh full <config>`
- Browse the implementation: [key files to understand]
