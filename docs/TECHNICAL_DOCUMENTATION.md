# Fill Rate Analyzer — Technical Documentation

| Field | Value |
|---|---|
| Document ID | TD-FRA-001 |
| Component | `src/fill_rate_analyzer.py` |
| Current version | 2.1.0 |
| Owner | Continuous Improvement team |
| Status | Approved |
| Last reviewed | 2026-10-30 |

---

## 1. Purpose

The Fill Rate Analyzer turns a raw warehouse order-line export into an interactive HTML report that operations leaders can open in any browser. It answers three questions:

1. **Are we shipping complete?** Fill rate = units shipped ÷ units ordered.
2. **Are we shipping on time?** On-time rate = lines shipped by promise date ÷ total lines.
3. **Where is the problem?** Breakdowns by site, SKU family, and day.

The report also embeds the project change log and team communication thread, so a reader can see *why* the numbers or the tool changed without leaving the page.

## 2. Scope

**In scope:** order-line CSV input, KPI calculation, HTML report generation, sample data for training.
**Out of scope:** live ERP connections, user authentication, data persistence beyond the input file.

## 3. Architecture

```
 ┌────────────────────┐    ┌──────────────┐    ┌───────────────┐    ┌───────────────────┐
 │ data/*.csv         │ →  │ load_orders  │ →  │ summarise     │ →  │                   │
 │ (order lines)      │    │ validate     │    │ KPI buckets   │    │  render_report    │
 └────────────────────┘    └──────────────┘    └───────────────┘    │  JSON → HTML      │ → reports/*.html
 ┌────────────────────┐    ┌──────────────┐                         │  template         │
 │ CHANGELOG.md       │ →  │ parse_       │ ──────────────────────→ │                   │
 └────────────────────┘    │ changelog    │                         │                   │
 ┌────────────────────┐    ├──────────────┤                         │                   │
 │ team_communication │ →  │ load_team_   │ ──────────────────────→ │                   │
 │ .json              │    │ comms        │                         └───────────────────┘
 └────────────────────┘    └──────────────┘
```

Design decisions:

| Decision | Reason |
|---|---|
| Standard library only | Runs on any locked-down corporate laptop with Python 3.9+; no `pip install`. |
| Raw sums stored in `KpiBucket`, rates derived | Avoids the "average of averages" error when combining groups. |
| HTML template inside the `.py` file | Single file to deploy; no build step. |
| All data injected as one JSON blob | The page works offline after load (except Chart.js from CDN). |
| Change log parsed from `CHANGELOG.md` | One source of truth — the report can never drift from the repo. |

## 4. Input specification

File: `data/sample_orders.csv` (UTF-8, comma-delimited, header row required)

| Column | Type | Required | Since | Notes |
|---|---|---|---|---|
| `order_date` | `YYYY-MM-DD` | Yes | 1.0.0 | |
| `site` | text | Yes | 1.0.0 | Warehouse name |
| `sku_family` | text | No | 1.1.0 | Defaults to `Unassigned` |
| `ordered_qty` | integer ≥ 0 | Yes | 1.0.0 | |
| `shipped_qty` | integer ≥ 0 | Yes | 1.0.0 | Clamped to `ordered_qty` |
| `shipped_on_time` | `0` / `1` | No | 1.2.0 | Defaults to `1` |

### Validation rules

| Rule | Action |
|---|---|
| Missing required column or non-numeric quantity | Row skipped, count printed |
| Negative quantity | Row skipped |
| `shipped_qty` > `ordered_qty` | Clamped (fix CHG-091) |

## 5. KPI definitions

| KPI | Formula | Target | Amber | Red |
|---|---|---|---|---|
| Fill rate | Σ shipped ÷ Σ ordered | ≥ 98% | 95–98% | < 95% |
| On-time rate | on-time lines ÷ total lines | ≥ 95% | — | — |

Empty buckets (zero ordered units) return `0.0` rather than raising an error.

## 6. Function reference

| Function | Input | Output | Introduced |
|---|---|---|---|
| `generate_sample_data(path, days, seed)` | path | row count | 1.0.0 |
| `load_orders(path)` | CSV path | `list[OrderLine]` | 1.0.0 |
| `summarise(lines)` | order lines | KPI dict | 1.0.0, extended 1.1.0 / 1.2.0 / 2.0.0 |
| `parse_changelog(path)` | `CHANGELOG.md` | list of releases | 2.1.0 |
| `load_team_comms(path)` | JSON path | escaped message list | 2.1.0 |
| `render_report(...)` | summary, log, comms | writes HTML | 2.0.0 |

## 7. Running

```bash
# generate seeded sample data and build the report
python src/fill_rate_analyzer.py --generate-sample

# build from your own file
python src/fill_rate_analyzer.py --in data/my_orders.csv --out reports/my_report.html

# run tests
python -m unittest discover tests
```

## 8. Report features

| Tab | Interaction |
|---|---|
| KPIs | Tiles, colour-coded bar charts, sortable site table |
| Trend | Daily fill-rate line chart with site filter and dashed target line |
| Change log | Releases from `CHANGELOG.md`, filter by Added / Changed / Fixed |
| Team communication | Threaded messages with author, role, timestamp and ticket/version reference |

Light and dark mode follow the viewer's system setting.

## 9. Security considerations

- Team message text is HTML-escaped in Python before embedding.
- The JSON payload escapes `</` so data cannot terminate the `<script>` block.
- No credentials, network calls, or file writes outside `--out`.

## 10. Versioning and change control

- Semantic versioning: MAJOR = breaking output/CLI change, MINOR = new feature, PATCH = fix.
- Every code change is tagged inline, e.g. `# [v1.1.1] [CHG-091]`, so the reason for a line is visible without `git blame`.
- Release checklist:
  1. Bump `__version__` in the script.
  2. Add a section to `CHANGELOG.md`.
  3. Post a note in `docs/team_communication.json` with the `ref`.
  4. Run tests, regenerate the report, commit, and tag `vX.Y.Z`.

## 11. Known limitations

- Chart.js loads from cdnjs; fully offline viewing needs the library vendored locally.
- Very large inputs (>1M rows) are held in memory.

## 12. Revision history of this document

| Doc version | Date | Author | Change |
|---|---|---|---|
| 1.0 | 2026-09-02 | C. Graves | Initial document |
| 1.1 | 2026-09-18 | C. Graves | Added validation rules after CHG-091 |
| 2.0 | 2026-10-14 | A. Moreno | Rewritten for HTML report (CHG-104) |
| 2.1 | 2026-10-30 | C. Graves | Added change log and team comms sections (CHG-118) |
