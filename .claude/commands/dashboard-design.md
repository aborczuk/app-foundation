---
description: Apply dashboard design conventions for the CSP Trader web dashboard. Use when implementing or reviewing any file under src/csp_trader/dashboard/templates/ or src/csp_trader/dashboard/static/.
---

## Purpose

Codify the visual conventions, component mappings, layout rules, and JS polling pattern for the CSP Trader running visibility dashboard (feature `001-watchlist-trade-dashboard`). Apply these rules consistently across all template and static file work.

---

## Technology Stack

| Layer | Choice |
|-------|--------|
| Server rendering | FastAPI + Jinja2 (`jinja2` package) |
| CSS framework | DaisyUI + Tailwind CSS — loaded from CDN, no build step |
| JS | Vanilla JS only — no framework, no bundler |
| Icons | None (text labels and DaisyUI badges are sufficient) |
| Charts | None in iteration 1 |

CDN snippet (place in `base.html` `<head>`):
```html
<link href="https://cdn.jsdelivr.net/npm/daisyui@5/themes.css" rel="stylesheet" />
<script src="https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4"></script>
```

DaisyUI theme: `data-theme="night"` on `<html>` — dark background appropriate for trading supervision.

---

## Layout Structure

```
<html data-theme="night">
  <head>  [title, CDN links, meta refresh disabled — JS handles refresh]  </head>
  <body class="min-h-screen bg-base-100 p-4">
    <header>   [page title + snapshot freshness banner]   </header>
    <main class="grid grid-cols-1 gap-4">
      [Source Health Bar]
      [Watchlist Section]
      [Active Orders Section]
      [Open Positions Section]
      [Reconciliation Alerts Section]
      [Lifecycle Event Timeline Section]
    </main>
    <footer>   [last refresh timestamp + session info]   </footer>
  </body>
</html>
```

Sections render in the order above. Do not reorder without explicit user instruction.

---

## State → DaisyUI Component Mappings

### Source / Record Health

| State | DaisyUI class | When used |
|-------|---------------|-----------|
| `healthy` | `badge badge-success` | Record or source is aligned |
| `degraded` | `badge badge-warning` | Drift detected or source partially failing |
| `unavailable` | `badge badge-error` | Source unreachable (3+ consecutive failures) |
| `stale` | `badge badge-warning` | Snapshot age > 10s but < 86400s |

### Lifecycle States (orders / positions)

| State | DaisyUI class | Notes |
|-------|---------------|-------|
| `open` | `badge badge-success` | Active open position |
| `closing` | `badge badge-warning` | BTC order submitted |
| `closed` | `badge badge-ghost` | Terminal state |
| `pending` | `badge badge-info` | Order submitted, not yet filled |
| `failed` | `badge badge-error` | Terminal failure state |
| Unknown/other | `badge badge-ghost` | Fallback for unrecognised states |

### Snapshot Freshness Banner

Render as a `DaisyUI alert` pinned below the header:

| Condition | Alert class | Message |
|-----------|-------------|---------|
| Fresh (age ≤ 10s) | `alert alert-success` | "Live — last updated Xs ago" |
| Stale (10s < age ≤ 86400s) | `alert alert-warning` | "Stale snapshot — last updated Xs ago" |
| Expired (age > 86400s) or no snapshot | `alert alert-error` | "Runtime unavailable — no recent snapshot" |

---

## Section Templates

### Source Health Bar

```html
<div class="flex gap-2 items-center">
  <span class="font-semibold text-sm">Sources:</span>
  <span class="badge badge-{runtime_status}">Runtime: {runtime_status}</span>
  <span class="badge badge-{broker_status}">Broker: {broker_status}</span>
  <span class="text-xs text-base-content/50">
    Last live sync: {last_successful_live_sync_at or "—"}
  </span>
</div>
```

### Watchlist Table

Use `table table-zebra table-sm w-full` with columns: **Ticker | Status | Themes | Last Updated**.

### Orders Table

Use `table table-zebra table-sm w-full` with columns: **Order ID | Ticker | Type | State | Last Transition | Reason**.

### Positions Table

Use `table table-zebra table-sm w-full` with columns: **Position ID | Ticker | State | Ann. Return | Last Transition | Reason**.

### Reconciliation Alerts

Render only degraded records. Each degraded record → one `alert alert-warning` block:
```html
<div class="alert alert-warning">
  <span>{record_type} {record_id}: {reason}</span>
</div>
```
If no degraded records: render `<p class="text-success text-sm">All records healthy.</p>`.

### Lifecycle Event Timeline

Render as a DaisyUI `timeline` or fallback to a `table table-zebra table-sm` with columns:
**Time | Entity | Event Type | Outcome | Reason**.

Failed outcomes (`outcome_status` = failed/error): render `outcome` cell as `badge badge-error`.
Successful outcomes: render as `badge badge-success`.

---

## JS Polling Pattern

One `<script>` block at the bottom of `base.html`. No external JS files for the polling logic.

```javascript
(function () {
  const REFRESH_MS = 5000;

  async function refresh() {
    try {
      const res = await fetch('/dashboard/runtime-snapshot');
      if (!res.ok) { applyError(await res.json()); return; }
      applySnapshot(await res.json());
    } catch (e) {
      applyUnavailable();
    }
  }

  function applySnapshot(data) {
    // Update DOM sections by ID: #watchlist, #orders, #positions,
    // #reconciliation, #source-health, #freshness-banner, #footer-ts
    // Re-render inner HTML from data fields.
    // Never use innerHTML with unsanitised user content —
    // all values must be text-set via textContent or server-rendered.
  }

  function applyError(err) {
    // Update #freshness-banner with alert-error + err.error_message
  }

  function applyUnavailable() {
    // Update #freshness-banner with alert-error "Runtime unavailable"
  }

  refresh();
  setInterval(refresh, REFRESH_MS);
})();
```

**Rules**:
- Never use `innerHTML` with values sourced from API responses — use `textContent` or server-rendered templates.
- All initial HTML is server-rendered by Jinja2 on first load; JS only updates existing DOM nodes on refresh.
- JS polling runs at 5-second intervals matching the server-side refresh worker cadence.
- On fetch error or non-2xx response: update freshness banner to error state; do not clear existing section content.

---

## Jinja2 Template Rules

- `base.html`: page shell, CDN links, freshness banner placeholder, JS polling block.
- `snapshot.html`: extends `base.html`; renders all sections from `RuntimeSnapshot` context variable.
- `events.html`: extends `base.html`; renders event timeline table with pagination controls.
- Pass only typed, validated Pydantic response models into templates — never raw dicts from DB queries.
- Use Jinja2 `{{ value | e }}` (auto-escape) for all user-facing string values.
- Boolean/status fields rendered via Jinja2 macros defined in `_macros.html` to keep badge logic DRY.

---
## Design Principles
**Token Architecture**
Every color in your interface should trace back to a small set of primitives: foreground (text hierarchy), background (surface elevation), border (separation hierarchy), brand, and semantic (destructive, warning, success). No random hex values — everything maps to primitives.

**Text Hierarchy**
Don't just have "text" and "gray text." Build four levels — primary, secondary, tertiary, muted. Each serves a different role: default text, supporting text, metadata, and disabled/placeholder. Use all four consistently. If you're only using two, your hierarchy is too flat.

**Border Progression**
Borders aren't binary. Build a scale that matches intensity to importance — standard separation, softer separation, emphasis, maximum emphasis. Not every boundary deserves the same weight.

**Control Tokens**
Form controls have specific needs. Don't reuse surface tokens — create dedicated ones for control backgrounds, control borders, and focus states. This lets you tune interactive elements independently from layout surfaces.

**Spacing**
Pick a base unit and stick to multiples. Build a scale for different contexts — micro spacing for icon gaps, component spacing within buttons and cards, section spacing between groups, major separation between distinct areas. Random values signal no system.

**Padding**
Keep it symmetrical. If one side has a value, others should match unless content naturally requires asymmetry.

**Depth**
Choose ONE approach and commit:

Borders-only — Clean, technical. For dense tools.
Subtle shadows — Soft lift. For approachable products.
Layered shadows — Premium, dimensional. For cards that need presence.
Surface color shifts — Background tints establish hierarchy without shadows.
Don't mix approaches.

**Border Radius**
Sharper feels technical. Rounder feels friendly. Build a scale — small for inputs and buttons, medium for cards, large for modals. Don't mix sharp and soft randomly.

**Typography**
Build distinct levels distinguishable at a glance. Headlines need weight and tight tracking for presence. Body needs comfortable weight for readability. Labels need medium weight that works at smaller sizes. Data needs monospace with tabular number spacing for alignment. Don't rely on size alone — combine size, weight, and letter-spacing.

**Card Layouts**
A metric card doesn't have to look like a plan card doesn't have to look like a settings card. Design each card's internal structure for its specific content — but keep the surface treatment consistent: same border weight, shadow depth, corner radius, padding scale.

**Controls**
Native <select> and <input type="date"> render OS-native elements that cannot be styled. Build custom components — trigger buttons with positioned dropdowns, calendar popovers, styled state management.

**Iconography**
Icons clarify, not decorate — if removing an icon loses no meaning, remove it. Choose one icon set and stick with it. Give standalone icons presence with subtle background containers.

**Animation**
Fast micro-interactions, smooth easing. Larger transitions can be slightly longer. Use deceleration easing. Avoid spring/bounce in professional interfaces.

**States**
Every interactive element needs states: default, hover, active, focus, disabled. Data needs states too: loading, empty, error. Missing states feel broken.

**Navigation Context**
Screens need grounding. A data table floating in space feels like a component demo, not a product. Include navigation showing where you are in the app, location indicators, and user context. When building sidebars, consider same background as main content with border separation rather than different colors.

**Dark Mode**
Dark interfaces have different needs. Shadows are less visible on dark backgrounds — lean on borders for definition. Semantic colors (success, warning, error) often need slight desaturation. The hierarchy system still applies, just with inverted values.

**Avoid**
- Harsh borders — if borders are the first thing you see, they're too strong
- Dramatic surface jumps — elevation changes should be whisper-quiet
- Inconsistent spacing — the clearest sign of no system
- Mixed depth strategies — pick one approach and commit
- Missing interaction states — hover, focus, disabled, loading, error
- Dramatic drop shadows — shadows should be subtle, not attention-grabbing
- Large radius on small elements
- Pure white cards on colored backgrounds
- Thick decorative borders
- Gradients and color for decoration — color should mean something
- Multiple accent colors — dilutes focus
- Different hues for different surfaces — keep the same hue, shift only lightness
---

## Color / Semantic Consistency Rules

1. **Green = healthy/success/open** — never use green for a warning or intermediate state.
2. **Yellow/warning = degraded/stale/closing** — operator attention needed but not a hard failure.
3. **Red/error = unavailable/failed/expired** — action required or data cannot be trusted.
4. **Ghost/neutral = terminal/inactive** — closed, cancelled, or no-data states.
5. Colour assignments MUST match the existing terminal dashboard (`monitoring/terminal.py`) semantics.

---

## What This Skill Does NOT Define

- API response shape (defined in `contracts/runtime-dashboard-api.md`).
- Refresh worker logic (defined in plan.md Async Process Model).
- Authentication (localhost-only binding; no auth UI elements in iteration 1).
- Any charting or graphing components (out of scope for iteration 1).
