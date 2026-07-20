# Research: Financial Acceleration Tracker

Investigation of prior art, integration patterns, and reusable code/packages that can reduce scope.

This artifact adapts the user-supplied research into the repo research format. Package names, repository fit, and licenses are research-derived and should be live-verified during planning before implementation.

---

## Zero-Custom-Server Assessment

No zero-custom-server option covers the core filing-driven product because the feature requires scheduled filing detection, quarter normalization, restatement handling, user-specific watchlists or portfolios, authorization, API access, and export state.

| Option | FRs covered | How it works | Gap (uncovered FRs) |
|--------|-------------|--------------|---------------------|
| Spreadsheet-only workbook | FR-009, FR-010, FR-011, FR-018 partially | Analysts manually paste filing data and formulas calculate margin, streak, and acceleration. | Does not cover SEC discovery, provenance, restatements, user authorization, background refresh, API output, or Google Sheets sync. |
| SEC website plus manual review | FR-002, FR-004 partially | Analysts manually search filings and read statements. | Does not cover automated metric extraction, quarter derivation, watchlist refresh, charts, APIs, or exports. |
| Google Sheets script-only flow | FR-015, FR-019 partially | A spreadsheet script pulls or transforms a small company set. | Does not cover reliable filing ingestion, XBRL validation, access control, portfolio/watchlist app workflows, or auditable restatement history. |

---

## Repo Assembly Map

Assemble the product from focused open-source components and keep the custom code in a small domain layer for fiscal-period correctness, metric selection, and scoring.

| Source (owner/repo) | File(s) to copy/adapt | FRs covered | Notes |
|---------------------|----------------------|-------------|-------|
| `xang1234/stock-screener` | API, job, watchlist, table, chart, and deployment patterns after repository verification. | FR-001, FR-013, FR-015, FR-016, FR-020 | Recommended as the app shell pattern for FastAPI, React, PostgreSQL, Redis, Celery, watchlists, tables, sparklines, and Dockerized deployment. Existing market-data assumptions must be removed or reviewed for licensing. |
| `dgunning/edgartools` | Package integration rather than copied source. | FR-002, FR-003, FR-004, FR-005, FR-006 | Primary SEC company, filing, XBRL fact, standardized statement, fiscal-period, and tabular extraction path. Supplied research reports MIT license. |
| `Arelle/Arelle` and `Arelle/EDGAR` | Validation and diagnosis adapter only. | FR-005, FR-012, FR-021 | Use as fallback when primary extraction fails or when filing validation details are needed. Supplied research reports Apache-2.0 license. |
| `fastapi/full-stack-fastapi-template` | Auth and API patterns only if the existing shell lacks them. | FR-017, FR-020, FR-021 | Reuse authentication, user management, API, Docker, and test structure where it fits the selected app shell. Supplied research reports MIT license. |
| `TanStack/table` | Table state and UI integration patterns. | FR-015 | Use for sorting, filtering, pagination, and column control in the dashboard. Supplied research reports MIT license. |
| `recharts/recharts` | Chart and sparkline integration patterns. | FR-016, FR-018, FR-019 | Use for sparklines, metric history charts, tooltips, and responsive visualizations. Supplied research reports MIT license. |
| `jmcnamara/XlsxWriter` | Package integration rather than copied source. | FR-018 | Use for workbook generation, date and percent formatting, hyperlinks, conditional formatting, charts, and multi-sheet exports. Supplied research reports BSD-2-Clause license. |
| `burnash/gspread` | Package integration rather than copied source. | FR-019 | Use for Google Sheets creation, range writes, batch updates, worksheet management, formatting, and permissions. Supplied research reports MIT license. |
| `clojure-finance/edgarjure` | Reference behavior only, not copied source. | FR-006, FR-007, FR-014 | Useful reference for standalone quarter derivation, restatement dedupe, and point-in-time thinking; language and EPL license make it a reference rather than a product dependency. |

**After assembly**: which FRs remain uncovered and require net-new code?
- **FR-006**: The product needs custom fiscal-period classification to prevent cumulative values from being compared as standalone quarters.
- **FR-007**: QTD and Q4 derivation rules require custom evidence checks and unavailable-state handling.
- **FR-008**: Revenue and operating-income selector priority must be product-specific and testable against GAAP concept variation.
- **FR-009**: Operating margin must be computed only from same-period valid numerator and denominator values.
- **FR-010**: Improvement streaks need custom quarter-aligned history handling.
- **FR-011**: Acceleration scoring needs first-difference, second-difference, and materiality-threshold logic.
- **FR-012**: The bounded data-quality taxonomy must map filing, parser, selector, fiscal-period, and export failures to user-facing categories.
- **FR-014**: Amendment and restatement behavior needs product-specific rules for current value selection and retained prior provenance.
- **FR-021**: Plain-language operational failure states need product-specific mapping across SEC retrieval, XBRL parsing, validation, export, and authorization failures.

---

## Package Adoption Options

No live package installability checks were run during this adaptation pass. The following candidates come from the supplied research and must be verified with package registry, repository, and license checks during the plan phase before implementation.

| Package | Version | FRs covered | Integration effort | Installability check |
|---------|---------|-------------|-------------------|---------------------|
| `edgartools` | Pending verification | FR-002, FR-003, FR-004, FR-005, FR-006 | 3 | Pending plan-phase live check. |
| `arelle-release` or selected Arelle package | Pending verification | FR-005, FR-012, FR-021 | 4 | Pending plan-phase live check; confirm package name and EDGAR plugin path. |
| `XlsxWriter` | Pending verification | FR-018 | 2 | Pending plan-phase live check. |
| `gspread` | Pending verification | FR-019 | 3 | Pending plan-phase live check, including OAuth flow fit. |
| `@tanstack/react-table` | Pending verification | FR-015 | 2 | Pending plan-phase live check. |
| `recharts` | Pending verification | FR-016, FR-018, FR-019 | 2 | Pending plan-phase live check. |

---

## Conceptual Patterns

- **Filing provenance first** - Every displayed, exported, or API-returned metric should remain tied to accession, acceptance timestamp, fiscal period, and amendment status. Covers FR-004, FR-014, FR-021. Requires custom server: yes. Source: supplied research on raw filing storage and restatement handling.
- **True standalone quarters before trend math** - Quarter-to-quarter comparison must only use standalone quarterly values or values derived from supported fiscal-period evidence. Covers FR-006, FR-007, FR-009, FR-010, FR-011. Requires custom server: yes. Source: supplied research on fiscal-quarter handling and Q4 derivation.
- **Small metric registry, not generic metric engine** - Start with revenue, operating income, operating margin, improvement streak, and acceleration rather than building a generic dependency system. Covers FR-008, FR-009, FR-010, FR-011. Requires custom server: yes. Source: supplied research on no-build scope and custom logic.
- **Visual honesty for sparklines** - Missing periods stay as gaps, restatements are visible, outliers are not smoothed away, and data-quality state travels with the chart. Covers FR-012, FR-016, FR-018, FR-019. Requires custom server: yes. Source: supplied research on sparkline correctness.
- **Adopt product plumbing, write correctness core** - Reuse app shell, jobs, tables, charts, and exports while keeping fiscal-period selection, metric calculations, and data-quality mapping in a product-owned core. Covers FR-001 through FR-021. Requires custom server: yes. Source: supplied research conclusion that this is an integration product with a small calculation layer.

---

## Recommended Separation

- **Filing ingestion boundary**: SEC company lookup, new filing detection, immutable accession metadata, accepted-filing selection, and raw retrieval status.
- **Fact extraction boundary**: Standardized statements, facts, units, fiscal periods, validation fallback, and parser failure capture.
- **Metric core boundary**: Metric registry, revenue and operating-income selectors, fiscal-period alignment, standalone-quarter derivation, margin, streak, acceleration, and materiality thresholds.
- **Data-quality boundary**: Bounded plain-language categories for unavailable, ambiguous, invalid, missing, amended, restated, retrieval-failed, parsing-failed, validation-failed, export-failed, and authorization-failed states.
- **Portfolio and watchlist boundary**: User-owned company universes, holdings metadata where available, membership changes, and authorization scope.
- **Job boundary**: Background filing detection, refresh scheduling, retry policy, and refresh status without embedding metric rules in worker orchestration.
- **API boundary**: Caller-authorized company, watchlist, portfolio, metric history, acceleration, export, and job-status surfaces.
- **UI boundary**: Sortable/filterable dashboards, company detail, sparkline history, data-quality indicators, and restatement visibility.
- **Export boundary**: Excel generation and Google Sheets sync with row, value, status, filter, and provenance parity against the dashboard.

---

## Licensing and Data Constraints

- Treat `dgunning/edgartools`, `fastapi/full-stack-fastapi-template`, `TanStack/table`, `recharts/recharts`, and `burnash/gspread` as permissive-license candidates according to supplied research, with live verification required before implementation.
- Treat `Arelle/Arelle` and `Arelle/EDGAR` as Apache-2.0 candidates according to supplied research, with live verification required before implementation.
- Treat `jmcnamara/XlsxWriter` as a BSD-2-Clause candidate according to supplied research, with live verification required before implementation.
- Do not adopt GPL or AGPL repositories such as `OpenBB-finance/OpenBB`, `ghostfolio/ghostfolio`, or `lefterisloukas/edgar-crawler` unless the owner explicitly accepts the license obligations.
- SEC filing data is the intended source for GAAP metrics; price data, options data, real-time performance, and provider-redistributed market data need a separate lawful source before entering scope.
- Do not use `yfinance` or Yahoo-derived data as an assumed commercial product feed.

---

## Search Tools Used

- Code Discovery: Semble search for command manifest, research command, and pipeline event anchors in `/Users/andreborczuk/app-foundation`.
- Local Context Mapping: bounded `scripts/read_code.py window` reads for `command-manifest.yaml`, `.claude/commands/speckit.research.md`, research templates, the scaffolded spec, and the user-supplied attachment.
- Package Discovery: user-supplied prior research only; no live package registry checks were run in this adaptation pass.
- Conceptual Patterns: user-supplied research on filing correctness, sparkline integrity, licensing, recommended composition, and no-build boundaries.

---

## Unanswered Questions

- No product-scope question blocks this spec-to-research conversion.
- During planning, verify current package availability, versions, maintainer activity, and license texts before implementation.
- During planning, decide whether any future price, options, brokerage, or real-time portfolio performance scope is needed; this feature excludes it unless a licensed provider and new acceptance criteria are selected.
