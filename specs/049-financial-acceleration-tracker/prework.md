# Financial Acceleration Tracker

A filing-driven analytics product that tracks quarterly GAAP metrics, identifies improving or accelerating trends, and exports results through watchlists, APIs, Excel, and Google Sheets.

## Revised Reuse-First Sizing

## Sizing

| Size | Meaning |
| --- | --- |
| XS | Small isolated function |
| S | One bounded module or integration |
| M | Several connected components or meaningful edge cases |
| L | Complete product spanning backend, frontend, jobs and integrations |
| XL | Novel foundational technology or substantial unresolved research |

## Overall system: **L**

The financial-calculation core is **S**. The total becomes **L** because the product includes ingestion, storage, API, watchlists, visualization, authentication and two export integrations.

---

# Component sizing and reuse

| Section | What it is | Existing code | What already exists | Custom work remaining | Size | License / gap |
| --- | --- | --- | --- | --- | --- | --- |
| SEC company and filing access | Looks up companies and retrieves their SEC filing history | `dgunning/edgartools` | Company lookup, CIK/ticker resolution, filing search, filing retrieval and local caching | Configure SEC identity, select forms and persist filing metadata | **S** | MIT; retain license notice. Actively supports SEC filings and XBRL financials. |
| New-filing detection | Detects newly published filings and starts processing | EdgarTools or Arelle RSS watcher | Filing retrieval primitives; Arelle supports monitoring SEC XBRL RSS feeds | Polling job, deduplication and enqueueing | **S** | EdgarTools MIT; Arelle Apache-2.0. |
| Raw filing storage | Preserves original SEC documents for reprocessing and auditing | Standard object storage SDK | Uploading, checksums and immutable object keys are routine infrastructure | Define accession-based storage paths and metadata | **S** | Cloud-provider terms apply; no specialist financial library needed |
| Financial statements | Extracts structured GAAP statements and facts from filings | `dgunning/edgartools` | Structured income statements, balance sheets and XBRL financial facts | Select the required statement rows and save them | **S** | MIT. Do not build a general mapping engine first. |
| XBRL validation fallback | Validates or diagnoses filings that fail normal extraction | `Arelle/Arelle` | Validating XBRL processor, Inline XBRL, SEC filing validation, CLI and Python APIs | Run only on filings that fail normal extraction or require diagnosis | **S** | Apache-2.0; retain notices. |
| Revenue selection | Selects the reported GAAP revenue value for each period | EdgarTools standardized statements | Reported GAAP income-statement values | Define preferred revenue row and limited fallback list | **S** | Custom fallback rules remain proprietary |
| Operating-income selection | Selects the reported GAAP operating-income value for each period | EdgarTools standardized statements | Reported GAAP operating-income values | Define preferred operating-income row and limited fallback list | **S** | Some issuers may not present this subtotal; return unavailable rather than build speculative mappings |
| Fiscal-quarter handling | Ensures values represent comparable standalone fiscal quarters | EdgarTools plus custom rules | Filing periods and financial-statement periods | Verify standalone-quarter versus cumulative period and derive Q4 where required | **M** | Main financial-data edge case |
| Operating margin | Calculates operating income as a percentage of revenue | Custom formula | Inputs already supplied by filing layer | `operating_income / revenue` | **XS** | No library or licensing gap |
| Improvement streak | Counts consecutive quarters in which a metric improved | Custom formula | None needed | Compare each quarter with the prior quarter | **XS** | No gap |
| Acceleration | Measures whether the rate of improvement is increasing | Custom formula | None needed | Calculate first and second differences with a materiality threshold | **XS** | No gap |
| Metric registry | Defines supported metrics, formulas, formats and inputs | Custom configuration | Generic configuration patterns | Metric metadata, formulas, display format and required inputs | **S** | Keep simple; no dependency engine needed initially |
| Amendments/restatements | Updates historical values when later filings revise them | Filing accession history plus EdgarTools | Access to later filings and filing dates | Select latest accepted filing per period and retain prior value | **M** | Versioning logic remains custom |
| Processing jobs | Runs filing ingestion and calculation tasks asynchronously | Existing stock-screener Celery/Redis implementation | Background workers, queues, locks and refresh states | Replace its fundamentals job with the SEC ingestion job | **S** | Stock-screener is Apache-2.0. |
| Backend/API shell | Provides the server, database patterns and application endpoints | `xang1234/stock-screener` or FastAPI full-stack template | FastAPI, database patterns, Docker and frontend integration | Define company, metric, history and watchlist endpoints | **M** | Stock-screener Apache-2.0; FastAPI template MIT. |
| Authentication | Manages user accounts, sessions and protected access | FastAPI full-stack template | Users, JWT authentication, password recovery and tests | Adapt user model and remove unused template features | **S** | MIT. |
| Watchlists | Stores and displays user-selected groups of companies | `xang1234/stock-screener` | Watchlists, folders, ordering and interactive workflows | Change displayed fields from price metrics to filing metrics | **M** | Apache-2.0. Preserve notices. |
| Table and filtering | Lets users sort and screen companies by financial metrics | Existing stock-screener implementation / TanStack Table | Sorting, filtering and headless table behavior | Define metric columns and filters | **S** | TanStack Table MIT. |
| Sparklines | Shows compact quarterly metric trends inside watchlists | Existing stock-screener implementation / Recharts | React charts and sparklines | Feed quarterly operating-margin history and warning markers | **S** | Recharts MIT. |
| Company detail page | Shows one company’s metrics, trends, filings and sources | Existing stock detail route | Page structure, charts and fundamentals sections | Replace existing panels with filing-derived metric history and sources | **M** | Covered by stock-screener Apache license |
| User-facing errors | Converts processing failures into understandable interface messages | Custom | Existing UI notification patterns can be reused | Map processing states into approximately 8–10 plain-language messages | **S** | No external gap |
| Excel export | Generates downloadable workbooks containing metrics and sources | `XlsxWriter` | XLSX files, formatting, formulas, hyperlinks, charts and conditional formatting | Define workbook tabs and columns | **S** | BSD-2-Clause; retain copyright and license notice. |
| Google Sheets export | Sends watchlist data into new or existing Google spreadsheets | `gspread` | Google Sheets creation, reading and writing | OAuth setup, destination selection and update behavior | **M** | Library is MIT; Google API credentials, quotas and platform terms still apply. |
| Testing | Verifies extraction, calculations, APIs and interface behavior | Existing app tests plus filing fixtures | Backend/frontend testing scaffolding | Add representative filing fixtures and formula tests | **M** | No license gap |
| Deployment | Packages and runs the application in production infrastructure | Existing stock-screener Docker stack or FastAPI template | Docker, PostgreSQL, reverse proxy and deployment configuration | Environment setup and production secrets | **S** | Permissive licenses |

---

# Sparkline requirements

1. **Quarter alignment**
   - Ensure each point represents a true standalone quarter.
   - Mixing cumulative year-to-date values with standalone quarters would make the sparkline misleading.

2. **Missing data**
   - Show gaps rather than fabricate continuity.

3. **Restatements**
   - Update the series when prior quarters are restated.
   - Mark restated points visually.

4. **Scale distortion**
   - Operating margin can swing from negative to positive.
   - Define consistent fixed or dynamic scaling rules.

5. **Outliers**
   - One extreme quarter can flatten the rest of the line.
   - Support clipping or visible outlier indicators.

6. **Data quality**
   - Derived or uncertain values should use distinct markers or line treatments.

7. **Consistency across companies**
   - Per-company scales improve readability but hinder direct comparison.
   - Shared scales improve comparison but may flatten individual trends.

8. **Performance**
   - Large watchlists may require memoization, virtualization or precomputed series.

---

# Category sizes

| Category | Size |
| --- | --- |
| Source acquisition | **S** |
| Raw storage | **S** |
| XBRL parsing | **S** |
| Concept mapping | **Removed as a standalone subsystem** |
| Fiscal-period handling | **M** |
| Restatements | **M** |
| Metric framework | **S** |
| Operating-margin logic | **XS** |
| Acceleration logic | **XS** |
| Data-quality system | **S** |
| API | **M** |
| Watchlist interface | **M** |
| Sparklines and tables | **S** |
| Excel export | **S** |
| Google Sheets export | **M** |
| Operations/admin console | **S or omit** |
| Entire system | **L** |

---

# What should not be built

- A universal XBRL taxonomy-mapping platform.
- A numeric confidence-scoring model.
- A general-purpose metric dependency engine.
- A manual mapping-review console before real failures justify it.
- A separate data-lineage platform.
- Arelle-based parsing for every normal filing.
- Cross-company accounting-policy normalization.
- Price-data ingestion.
- Options-data ingestion or licensing.
- A custom spreadsheet writer.
- A custom charting library.
- A custom authentication system.

---

# Actual custom product logic

1. Select revenue and operating income from the standardized income statement.
2. Confirm that both values cover the same fiscal period.
3. Derive standalone quarters when the source contains cumulative values.
4. Calculate operating margin.
5. Calculate consecutive improvement.
6. Calculate acceleration.
7. Save the result with the filing accession and source values.
8. Update watchlists when a new filing is processed.
9. Display unavailable or failed extraction states without inventing values.
10. Export the same stored metrics.

---

# License gaps and constraints

| Item | Status |
| --- | --- |
| EdgarTools | **Usable:** MIT |
| Arelle | **Usable:** Apache-2.0 |
| Stock-screener application | **Usable:** Apache-2.0 |
| FastAPI full-stack template | **Usable:** MIT |
| TanStack Table | **Usable:** MIT |
| Recharts | **Usable:** MIT |
| XlsxWriter | **Usable:** BSD-2-Clause |
| gspread | **Usable:** MIT |
| SEC filing data | No separate commercial market-data license is needed for the filing-derived GAAP inputs |
| Google Sheets | API usage requires Google authorization and compliance with Google API terms |
| Stock-price sparklines | Not covered by this stack; requires a lawful price-data source |
| Options data | Not covered and generally requires appropriate market-data licensing |
| Existing stock-screener data providers | Remove or isolate yfinance and other third-party market-data dependencies if their data is not licensed for the intended commercial use |
| Copyleft repositories | Avoid AGPL/GPL components unless the intended source-disclosure obligations are acceptable |

---

# Recommended composition

```text
xang1234/stock-screener
├── existing React watchlists, tables and sparklines
├── existing FastAPI/PostgreSQL/Celery/Redis shell
│
├── replace fundamentals ingestion with dgunning/edgartools
├── add Arelle only as validation/failure fallback
├── add custom quarterly-period checks
├── add operating-margin and acceleration formulas
├── add XlsxWriter export
└── add gspread Google Sheets integration
```

This is an integration product with a small calculation layer—not an original financial-data infrastructure project.

---

# Appendix A: Open-source library research

## Coverage matrix

✅ = directly reusable for the section.  
❌ = not meaningfully covered.

### Data and processing libraries

| Library or repository | Company and filing access | Raw retrieval | XBRL parsing | Standardized statements | Fiscal-period support | Restatements | DataFrame output | Validation or lineage |
| --- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| [`dgunning/edgartools`](https://github.com/dgunning/edgartools) | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ | ❌ |
| [`Arelle/Arelle`](https://github.com/Arelle/Arelle) | ❌ | ❌ | ✅ | ✅ | ❌ | ❌ | ❌ | ✅ |
| [`Arelle/EDGAR`](https://github.com/Arelle/EDGAR) | ❌ | ❌ | ✅ | ✅ | ❌ | ❌ | ❌ | ✅ |
| [`jadchaar/sec-edgar-downloader`](https://github.com/jadchaar/sec-edgar-downloader) | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| [`sec-edgar/sec-edgar`](https://github.com/sec-edgar/sec-edgar) | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| [`alphanome-ai/sec-parser`](https://github.com/alphanome-ai/sec-parser) | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ |
| [`clojure-finance/edgarjure`](https://github.com/clojure-finance/edgarjure) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| [`xang1234/stock-screener`](https://github.com/xang1234/stock-screener) | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ |
| [`OpenBB-finance/OpenBB`](https://github.com/OpenBB-finance/OpenBB) | ✅ | ❌ | ❌ | ❌ | ✅ | ❌ | ✅ | ❌ |
| [`dagster-io/dagster`](https://github.com/dagster-io/dagster) | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| [`great-expectations/great_expectations`](https://github.com/great-expectations/great_expectations) | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| [`OpenLineage/OpenLineage`](https://github.com/OpenLineage/OpenLineage) | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |

### Product and interface libraries

| Library or repository | API and auth shell | Watchlists | Tables and filters | Sparklines and charts | Background processing | Excel export | Google Sheets |
| --- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| [`xang1234/stock-screener`](https://github.com/xang1234/stock-screener) | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ |
| [`fastapi/full-stack-fastapi-template`](https://github.com/fastapi/full-stack-fastapi-template) | ✅ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ |
| [`ghostfolio/ghostfolio`](https://github.com/ghostfolio/ghostfolio) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| [`OpenBB-finance/OpenBB`](https://github.com/OpenBB-finance/OpenBB) | ✅ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ |
| [`TanStack/table`](https://github.com/TanStack/table) | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ |
| [`recharts/recharts`](https://github.com/recharts/recharts) | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ |
| [`jmcnamara/XlsxWriter`](https://github.com/jmcnamara/XlsxWriter) | ❌ | ❌ | ❌ | ✅ | ❌ | ✅ | ❌ |
| [`burnash/gspread`](https://github.com/burnash/gspread) | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |

## Recommended library roles

| Role | Recommended repository | Reason |
| --- | --- | --- |
| Application foundation | `xang1234/stock-screener` | Already includes FastAPI, React, PostgreSQL, Redis, Celery, watchlists, filters and sparklines |
| Primary SEC library | `dgunning/edgartools` | Covers company lookup, filings, XBRL facts, statements, periods and source retrieval |
| XBRL validation fallback | `Arelle/Arelle` and `Arelle/EDGAR` | Mature XBRL validation and SEC-specific filing diagnostics |
| Restatement and period reference | `clojure-finance/edgarjure` | Useful reference implementation for YTD derivation, amendments and point-in-time values |
| Authentication alternative | `fastapi/full-stack-fastapi-template` | Provides reusable user, JWT, password recovery and testing infrastructure |
| Watchlist tables | Existing stock-screener implementation or TanStack Table | Sorting, filtering and configurable table behavior already exist |
| Sparklines | Existing stock-screener implementation or Recharts | Suitable for compact quarterly trend displays |
| Background jobs | Existing Celery and Redis implementation | Avoids adding another orchestration platform |
| Excel exports | XlsxWriter | Supports formatted workbooks, formulas, charts and hyperlinks |
| Google Sheets exports | gspread | Supports sheet creation, writing, formatting and batch updates |
| Optional validation | Great Expectations | Useful for structural and range checks, but not required for product-specific financial rules |
| Optional lineage | Dagster or OpenLineage | Only useful if operational lineage becomes complex enough to justify it |

## Repository findings

### `dgunning/edgartools`

Useful for:

- Company and CIK lookup.
- Filing discovery and retrieval.
- Filing metadata.
- XBRL facts.
- Structured income statements and balance sheets.
- Fiscal-period handling.
- DataFrame output.
- Local caching.
- Source-document access.

Recommended role:

- Primary SEC and financial-statement abstraction.

License:

- MIT.

Gap:

- Product-specific margin, streak and acceleration logic remains custom.

### `Arelle/Arelle` and `Arelle/EDGAR`

Useful for:

- XBRL and Inline XBRL validation.
- SEC filing validation.
- Taxonomy relationships.
- Calculation-link validation.
- Diagnosing difficult filings.

Recommended role:

- Validation and fallback rather than the primary application interface.

License:

- Apache-2.0.

Gap:

- Does not provide the complete product workflow, watchlists or application layer.

### `xang1234/stock-screener`

Useful for:

- FastAPI backend.
- React frontend.
- PostgreSQL.
- Redis.
- Celery workers.
- Watchlists and folders.
- Screening and filtering.
- TanStack tables.
- Recharts sparklines.
- Docker deployment.
- Existing background refresh states.

Recommended role:

- Application shell to fork and adapt.

License:

- Apache-2.0.

Gap:

- Existing fundamentals and market-data sources must be replaced or reviewed for commercial licensing.

### `clojure-finance/edgarjure`

Useful for:

- Canonical financial-statement values.
- Restatement deduplication.
- Point-in-time queries.
- Standalone-quarter derivation from YTD facts.
- Amendment handling.
- Structured processing results.

Recommended role:

- Design and test reference, or separate service if using Clojure is acceptable.

License:

- EPL-2.0.

Gap:

- Different language stack from the proposed Python application.

### `fastapi/full-stack-fastapi-template`

Useful for:

- Authentication.
- User management.
- JWT sessions.
- Password recovery.
- Backend and frontend structure.
- Docker-based deployment.
- Testing patterns.

Recommended role:

- Authentication reference or alternative foundation if the stock-screener shell is unsuitable.

License:

- MIT.

### `TanStack/table`

Useful for:

- Sorting.
- Filtering.
- Pagination.
- Column configuration.
- Table state management.

Recommended role:

- Watchlist and screener table implementation.

License:

- MIT.

### `recharts/recharts`

Useful for:

- Sparklines.
- Metric history charts.
- Tooltips.
- Responsive React visualizations.

Recommended role:

- Watchlist sparklines and company detail charts.

License:

- MIT.

### `jmcnamara/XlsxWriter`

Useful for:

- XLSX generation.
- Percentage and date formatting.
- Hyperlinks.
- Conditional formatting.
- Charts.
- Multiple worksheet exports.

Recommended role:

- Excel export implementation.

License:

- BSD-2-Clause.

### `burnash/gspread`

Useful for:

- Google Sheets creation.
- Reading and writing ranges.
- Batch updates.
- Worksheet management.
- Formatting and permissions.

Recommended role:

- Google Sheets integration.

License:

- MIT.

## Libraries not recommended as the product foundation

| Repository | Reason |
| --- | --- |
| `OpenBB-finance/OpenBB` | Broad financial platform but AGPLv3 licensing may not fit a proprietary hosted product |
| `ghostfolio/ghostfolio` | Strong interface reference, but AGPLv3 creates similar source-disclosure considerations |
| `lefterisloukas/edgar-crawler` | GPLv3 code should not be incorporated unless GPL obligations are acceptable |
| `ranaroussi/yfinance` | Library code is permissive, but Yahoo data usage is not appropriate as an assumed commercial resale source |
| Dagster | Useful but duplicates the existing Celery/Redis job infrastructure for the current scope |
| OpenLineage | Adds operational complexity before lineage needs justify it |
| Great Expectations | Helpful for generic validation, but cannot replace custom fiscal-period and metric checks |

## Reuse conclusion

The proposed product does not need to be built from scratch.

The reusable stack covers:

- SEC access.
- Filing retrieval.
- XBRL parsing.
- Standardized financial statements.
- XBRL validation.
- Background jobs.
- API and authentication scaffolding.
- Watchlists.
- Tables and filters.
- Sparklines.
- Excel output.
- Google Sheets output.
- Containerized deployment.

The remaining custom work is primarily:

- Selecting the required GAAP inputs.
- Matching fiscal periods.
- Deriving standalone quarters where necessary.
- Calculating margin, streak and acceleration.
- Preserving filing provenance.
- Updating the interface and exports with those results.
