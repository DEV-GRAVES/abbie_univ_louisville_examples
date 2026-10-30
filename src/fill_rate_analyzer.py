#!/usr/bin/env python3
# =============================================================================
#  FILE:        src/fill_rate_analyzer.py
#  PROJECT:     abbie_univ_louisville_examples
#  PURPOSE:     Example supply-chain analytics script. Reads warehouse order
#               lines, calculates fill-rate / on-time KPIs by site and SKU
#               family, and renders a self-contained interactive HTML report
#               that also shows the project change log and team messages.
#
#  AUTHOR:      Chris Graves  (Continuous Improvement)
#  CREATED:     2026-09-02
#  LAST EDIT:   2026-10-30
#  VERSION:     2.1.0     <-- keep in sync with __version__ below + CHANGELOG.md
#
#  LICENSE:     CC0 1.0 Universal (see LICENSE)
#
# -----------------------------------------------------------------------------
#  HOW TO READ THE CHANGE TAGS IN THIS FILE
# -----------------------------------------------------------------------------
#  Every meaningful edit is tagged inline with a bracketed marker so a reviewer
#  can trace *why* a line exists without opening git blame:
#
#     [v1.0.0]  original implementation
#     [v1.1.0]  feature added in a minor release
#     [v1.1.1]  bug fix (patch release)
#     [CHG-###] change-request ticket number from the team tracker
#
#  Rule of thumb used by the team:
#     - MAJOR (x.0.0)  -> output format or CLI changes that break callers
#     - MINOR (0.x.0)  -> new, backwards-compatible features
#     - PATCH (0.0.x)  -> bug fixes only
#
# -----------------------------------------------------------------------------
#  VERSION HISTORY (summary - full detail lives in CHANGELOG.md)
# -----------------------------------------------------------------------------
#  2.1.0  2026-10-30  CG  [CHG-118] Change log + team comms panels in report.
#  2.0.0  2026-10-14  AM  [CHG-104] BREAKING: report is now HTML (was CSV).
#                                   CLI flag --out now expects a .html path.
#  1.2.0  2026-09-30  JT  [CHG-097] Added on-time-ship KPI alongside fill rate.
#  1.1.1  2026-09-18  CG  [CHG-091] Fixed divide-by-zero when a site had no
#                                   ordered units for a day.
#  1.1.0  2026-09-12  AM  [CHG-088] Added SKU-family grouping.
#  1.0.0  2026-09-02  CG            Initial release: fill rate by site.
#
# -----------------------------------------------------------------------------
#  USAGE
# -----------------------------------------------------------------------------
#     python src/fill_rate_analyzer.py --generate-sample          # make data
#     python src/fill_rate_analyzer.py                            # build report
#     python src/fill_rate_analyzer.py --in data/x.csv --out reports/x.html
#
#  Dependencies: Python 3.9+ standard library ONLY (no pip install needed).
#  The HTML report pulls Chart.js from cdnjs at view time.
# =============================================================================

from __future__ import annotations  # [v2.0.0] allows `list[str]` hints on 3.9

import argparse          # [v1.0.0] command-line flags
import csv               # [v1.0.0] read/write order lines
import html              # [v2.1.0] [CHG-118] escape team-message text safely
import json              # [v2.0.0] embed data into the HTML report
import random            # [v1.0.0] sample-data generator only
from collections import defaultdict  # [v1.0.0] grouping accumulators
from dataclasses import dataclass, field  # [v1.1.0] cleaner record types
from datetime import date, datetime, timedelta
from pathlib import Path

# -----------------------------------------------------------------------------
#  MODULE CONSTANTS
# -----------------------------------------------------------------------------
__version__ = "2.1.0"  # Single source of truth for the version string.
                       # The HTML footer reads this value, so bump it here
                       # FIRST, then update CHANGELOG.md.

# Paths are resolved relative to the repo root so the script works no matter
# which folder you launch it from.                               [v1.1.1]
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = REPO_ROOT / "data" / "sample_orders.csv"
DEFAULT_OUTPUT = REPO_ROOT / "reports" / "fill_rate_report.html"   # [v2.0.0] was .csv
CHANGELOG_PATH = REPO_ROOT / "CHANGELOG.md"                         # [v2.1.0]
TEAM_COMMS_PATH = REPO_ROOT / "docs" / "team_communication.json"   # [v2.1.0]

# Business thresholds agreed with operations on 2026-09-02.  Changing these
# changes the RAG (red/amber/green) colouring in the report.
FILL_RATE_TARGET = 0.98   # 98% of ordered units must ship complete
FILL_RATE_WARN = 0.95     # below this the site shows RED
ON_TIME_TARGET = 0.95     # [v1.2.0] [CHG-097] on-time ship target

SITES = ["Louisville KY", "Memphis TN", "Indianapolis IN"]
SKU_FAMILIES = ["Electronics", "Fixtures", "Accessories", "Spare Parts"]  # [v1.1.0]


# -----------------------------------------------------------------------------
#  DATA MODEL
# -----------------------------------------------------------------------------
@dataclass
class OrderLine:
    """One row of the input CSV.

    Fields
    ------
    order_date   : date the customer order was received
    site         : fulfilment warehouse
    sku_family   : product grouping           [v1.1.0] [CHG-088]
    ordered_qty  : units requested
    shipped_qty  : units actually shipped (<= ordered_qty)
    shipped_on_time : True if shipped by promised date  [v1.2.0] [CHG-097]
    """
    order_date: date
    site: str
    sku_family: str
    ordered_qty: int
    shipped_qty: int
    shipped_on_time: bool


@dataclass
class KpiBucket:
    """Running totals for one grouping (a site, a family, or a day).

    We store raw sums rather than percentages so buckets can be combined
    later without the 'average of averages' error.
    """
    ordered: int = 0
    shipped: int = 0
    lines: int = 0
    on_time_lines: int = 0  # [v1.2.0]

    def add(self, line: OrderLine) -> None:
        self.ordered += line.ordered_qty
        self.shipped += line.shipped_qty
        self.lines += 1
        self.on_time_lines += int(line.shipped_on_time)

    # --- derived metrics -----------------------------------------------------
    @property
    def fill_rate(self) -> float:
        # [v1.1.1] [CHG-091] BUG FIX: guard against zero ordered units.
        # Before 1.1.1 this raised ZeroDivisionError for empty days.
        # OLD:  return self.shipped / self.ordered
        return self.shipped / self.ordered if self.ordered else 0.0

    @property
    def on_time_rate(self) -> float:
        # [v1.2.0] same zero-guard pattern applied from day one.
        return self.on_time_lines / self.lines if self.lines else 0.0


# -----------------------------------------------------------------------------
#  1. SAMPLE DATA  (only used for demos / class exercises)
# -----------------------------------------------------------------------------
def generate_sample_data(path: Path, days: int = 30, seed: int = 42) -> int:
    """Write a realistic-looking order-line CSV and return the row count.

    A fixed `seed` keeps the output identical on every run so screenshots
    and grading rubrics stay reproducible.                      [v1.0.0]
    """
    rng = random.Random(seed)
    start = date(2026, 9, 28)
    # Each site gets a slightly different performance profile so the report
    # has something interesting to show.
    site_quality = {"Louisville KY": 0.99, "Memphis TN": 0.94, "Indianapolis IN": 0.965}

    rows = 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["order_date", "site", "sku_family", "ordered_qty",
                    "shipped_qty", "shipped_on_time"])
        for d in range(days):
            day = start + timedelta(days=d)
            for site in SITES:
                for _ in range(rng.randint(18, 30)):
                    fam = rng.choice(SKU_FAMILIES)
                    ordered = rng.randint(5, 120)
                    # Spare Parts are deliberately harder to fill completely.
                    q = site_quality[site] - (0.05 if fam == "Spare Parts" else 0)
                    # A short line ships at most half the units, so shortages show up clearly.
                    shipped = ordered if rng.random() < q else rng.randint(0, ordered // 2)
                    on_time = rng.random() < (q - 0.01)
                    w.writerow([day.isoformat(), site, fam, ordered, shipped, int(on_time)])
                    rows += 1
    return rows


# -----------------------------------------------------------------------------
#  2. LOAD + VALIDATE
# -----------------------------------------------------------------------------
def load_orders(path: Path) -> list[OrderLine]:
    """Parse the CSV into OrderLine objects, skipping bad rows.

    Validation rules (added in [v1.1.1] after the Memphis data issue):
      - shipped_qty may never exceed ordered_qty  -> row is clamped
      - negative quantities are rejected          -> row is skipped
    """
    lines: list[OrderLine] = []
    skipped = 0
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            try:
                ordered = int(row["ordered_qty"])
                shipped = int(row["shipped_qty"])
                if ordered < 0 or shipped < 0:
                    skipped += 1
                    continue
                lines.append(OrderLine(
                    order_date=datetime.strptime(row["order_date"], "%Y-%m-%d").date(),
                    site=row["site"].strip(),
                    # [v1.1.0] default keeps v1.0 files (no family column) loadable
                    sku_family=row.get("sku_family", "Unassigned").strip() or "Unassigned",
                    ordered_qty=ordered,
                    shipped_qty=min(shipped, ordered),     # [v1.1.1] clamp
                    shipped_on_time=row.get("shipped_on_time", "1") == "1",  # [v1.2.0]
                ))
            except (KeyError, ValueError):
                skipped += 1
    if skipped:
        print(f"  ! skipped {skipped} invalid row(s)")
    return lines


# -----------------------------------------------------------------------------
#  3. CALCULATE KPIs
# -----------------------------------------------------------------------------
def summarise(lines: list[OrderLine]) -> dict:
    """Group order lines three ways and return a JSON-ready dict."""
    by_site: dict[str, KpiBucket] = defaultdict(KpiBucket)
    by_family: dict[str, KpiBucket] = defaultdict(KpiBucket)       # [v1.1.0]
    by_day_site: dict[tuple, KpiBucket] = defaultdict(KpiBucket)   # [v2.0.0] for trend chart
    total = KpiBucket()

    for ln in lines:
        by_site[ln.site].add(ln)
        by_family[ln.sku_family].add(ln)
        by_day_site[(ln.order_date.isoformat(), ln.site)].add(ln)
        total.add(ln)

    days = sorted({d for d, _ in by_day_site})

    def pack(b: KpiBucket) -> dict:
        return {"ordered": b.ordered, "shipped": b.shipped, "lines": b.lines,
                "fill_rate": round(b.fill_rate, 4),
                "on_time_rate": round(b.on_time_rate, 4)}

    return {
        "total": pack(total),
        "sites": {s: pack(b) for s, b in sorted(by_site.items())},
        "families": {f: pack(b) for f, b in sorted(by_family.items())},
        "days": days,
        "trend": {s: [round(by_day_site[(d, s)].fill_rate, 4) for d in days]
                  for s in sorted(by_site)},
        "targets": {"fill": FILL_RATE_TARGET, "warn": FILL_RATE_WARN,
                    "on_time": ON_TIME_TARGET},
    }


# -----------------------------------------------------------------------------
#  4. CHANGE LOG + TEAM COMMS  (new in v2.1.0, [CHG-118])
# -----------------------------------------------------------------------------
def parse_changelog(path: Path) -> list[dict]:
    """Turn CHANGELOG.md (Keep-a-Changelog style) into a list of releases.

    Expected heading format:   ## [2.1.0] - 2026-10-30
    Section headings:          ### Added / ### Fixed / ### Changed
    Bullets:                   - text
    """
    releases: list[dict] = []
    current = None
    section = None
    if not path.exists():
        return releases
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("## ["):
            ver = line[4:line.index("]")]
            dt = line.split("-", 1)[1].strip() if " - " in line else ""
            current = {"version": ver, "date": dt, "items": []}
            releases.append(current)
        elif line.startswith("### ") and current is not None:
            section = line[4:].strip()
        elif line.startswith("- ") and current is not None:
            current["items"].append({"type": section or "Changed", "text": line[2:]})
    return releases


def load_team_comms(path: Path) -> list[dict]:
    """Load the team message thread. Text is HTML-escaped here so the
    report can never execute markup typed into a message.        [v2.1.0]
    """
    if not path.exists():
        return []
    msgs = json.loads(path.read_text(encoding="utf-8"))
    for m in msgs:
        m["text"] = html.escape(m.get("text", ""))
    return msgs


# -----------------------------------------------------------------------------
#  5. RENDER HTML
# -----------------------------------------------------------------------------
def render_report(summary: dict, changelog: list[dict], comms: list[dict], out: Path) -> None:
    """Inject all data into the HTML template as one JSON blob.

    [v2.0.0] [CHG-104] Replaced the old CSV writer. Keeping the template
    in this file means the repo has zero build steps.
    """
    payload = {
        "summary": summary,
        "changelog": changelog,
        "comms": comms,
        "meta": {"version": __version__,
                 "generated": datetime.now().strftime("%Y-%m-%d %H:%M")},
    }
    # `</` is escaped so a value can never close the <script> tag early.
    blob = json.dumps(payload).replace("</", "<\\/")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(HTML_TEMPLATE.replace("__PAYLOAD__", blob), encoding="utf-8")


# -----------------------------------------------------------------------------
#  HTML TEMPLATE  ([v2.0.0] created, [v2.1.0] tabs for change log + comms)
# -----------------------------------------------------------------------------
HTML_TEMPLATE = r"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Fill Rate Report</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
:root{--bg:#f6f7f9;--card:#fff;--ink:#1b1f24;--muted:#5d6670;--line:#e3e6ea;
--accent:#1f5fbf;--good:#1e8e4e;--warn:#c98a00;--bad:#c23b3b;}
@media (prefers-color-scheme:dark){:root{--bg:#121417;--card:#1b1e22;--ink:#e8eaed;
--muted:#9aa3ad;--line:#2c3036;--accent:#6ea3ff;}}
*{box-sizing:border-box}body{margin:0;font:15px/1.5 system-ui,-apple-system,Segoe UI,sans-serif;
background:var(--bg);color:var(--ink)}
header{padding:24px 16px 8px;max-width:1100px;margin:auto}
h1{margin:0;font-size:22px}header p{margin:4px 0 0;color:var(--muted)}
main{max-width:1100px;margin:auto;padding:0 16px 40px}
nav{display:flex;gap:6px;margin:16px 0;border-bottom:1px solid var(--line);overflow-x:auto}
nav button{background:none;border:0;padding:10px 14px;font:inherit;color:var(--muted);
cursor:pointer;border-bottom:2px solid transparent;white-space:nowrap}
nav button.on{color:var(--accent);border-color:var(--accent);font-weight:600}
.tab{display:none}.tab.on{display:block}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px}
.kpi .v{font-size:28px;font-weight:700}.kpi .l{color:var(--muted);font-size:13px}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:12px;margin-top:12px}
table{width:100%;border-collapse:collapse;font-size:14px}
th,td{text-align:left;padding:8px;border-bottom:1px solid var(--line)}
th{color:var(--muted);font-weight:600;cursor:pointer}
.pill{display:inline-block;padding:1px 8px;border-radius:999px;font-size:12px;color:#fff}
.g{background:var(--good)}.a{background:var(--warn)}.r{background:var(--bad)}
select{font:inherit;padding:6px;border-radius:6px;border:1px solid var(--line);
background:var(--card);color:var(--ink)}
.rel{border-left:3px solid var(--accent);padding:4px 0 4px 14px;margin:0 0 20px}
.rel h3{margin:0;font-size:16px}.rel small{color:var(--muted)}
.rel ul{margin:6px 0 0;padding-left:18px}.tag{font-size:11px;font-weight:700;
text-transform:uppercase;margin-right:6px;color:var(--accent)}
.msg{display:flex;gap:10px;margin-bottom:14px}
.av{flex:0 0 36px;height:36px;border-radius:50%;display:grid;place-items:center;
color:#fff;font-weight:700;font-size:13px}
.bubble{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 12px;flex:1}
.bubble .who{font-weight:600}.bubble .meta{color:var(--muted);font-size:12px}
.ref{font-size:12px;background:var(--bg);border:1px solid var(--line);border-radius:4px;padding:0 5px}
footer{color:var(--muted);font-size:12px;text-align:center;margin-top:30px}
</style></head><body>
<header><h1>Warehouse Fill Rate Report</h1>
<p id="sub"></p></header>
<main>
<nav>
 <button class="on" data-t="kpi">KPIs</button>
 <button data-t="trend">Trend</button>
 <button data-t="log">Change log</button>
 <button data-t="team">Team communication</button>
</nav>

<section id="kpi" class="tab on">
 <div class="kpis" id="kpis"></div>
 <div class="grid2">
  <div class="card"><h3 style="margin-top:0">Fill rate by site</h3><canvas id="siteChart"></canvas></div>
  <div class="card"><h3 style="margin-top:0">Fill rate by SKU family</h3><canvas id="famChart"></canvas></div>
 </div>
 <div class="card" style="margin-top:12px"><h3 style="margin-top:0">Site detail <small style="color:var(--muted);font-weight:400">(click a header to sort)</small></h3>
  <table id="siteTbl"><thead><tr>
   <th data-k="name">Site</th><th data-k="lines">Lines</th><th data-k="ordered">Ordered</th>
   <th data-k="shipped">Shipped</th><th data-k="fill_rate">Fill rate</th><th data-k="on_time_rate">On time</th>
  </tr></thead><tbody></tbody></table></div>
</section>

<section id="trend" class="tab">
 <div class="card"><label>Site: <select id="siteSel"></select></label>
 <canvas id="trendChart" style="margin-top:12px"></canvas></div>
</section>

<section id="log" class="tab"><div class="card">
 <label>Show: <select id="logFilter"><option>All</option><option>Added</option>
 <option>Changed</option><option>Fixed</option></select></label>
 <div id="logList" style="margin-top:16px"></div></div></section>

<section id="team" class="tab"><div class="card" id="teamList"></div></section>

<footer id="foot"></footer>
</main>
<script>
const D = __PAYLOAD__;
const S = D.summary, pct = v => (v*100).toFixed(1)+'%';
const rag = v => v>=S.targets.fill?'g':v>=S.targets.warn?'a':'r';
document.getElementById('sub').textContent =
  `${S.days[0]} to ${S.days[S.days.length-1]} · ${S.total.lines.toLocaleString()} order lines · target ${pct(S.targets.fill)}`;
document.getElementById('foot').textContent =
  `Generated ${D.meta.generated} by fill_rate_analyzer.py v${D.meta.version}`;

// tabs
document.querySelectorAll('nav button').forEach(b=>b.onclick=()=>{
  document.querySelectorAll('nav button,.tab').forEach(e=>e.classList.remove('on'));
  b.classList.add('on'); document.getElementById(b.dataset.t).classList.add('on');});

// KPI tiles
const k=[['Overall fill rate',pct(S.total.fill_rate)],['On-time ship',pct(S.total.on_time_rate)],
 ['Units ordered',S.total.ordered.toLocaleString()],['Units short',(S.total.ordered-S.total.shipped).toLocaleString()]];
document.getElementById('kpis').innerHTML=k.map(([l,v])=>`<div class="card kpi"><div class="l">${l}</div><div class="v">${v}</div></div>`).join('');

// charts
const css=getComputedStyle(document.documentElement), ink=css.getPropertyValue('--muted');
Chart.defaults.color=ink;
const colorFor=v=>v>=S.targets.fill?'#1e8e4e':v>=S.targets.warn?'#c98a00':'#c23b3b';
function bar(id,obj){const ks=Object.keys(obj),vs=ks.map(x=>obj[x].fill_rate);
 new Chart(document.getElementById(id),{type:'bar',data:{labels:ks,datasets:[{data:vs.map(v=>v*100),
 backgroundColor:vs.map(colorFor)}]},options:{plugins:{legend:{display:false},
 tooltip:{callbacks:{label:c=>c.raw.toFixed(2)+'%'}}},scales:{y:{min:85,max:100,ticks:{callback:v=>v+'%'}}}}});}
bar('siteChart',S.sites); bar('famChart',S.families);

// sortable table
let rows=Object.entries(S.sites).map(([name,v])=>({name,...v})), dir=1, key='fill_rate';
function drawTbl(){rows.sort((a,b)=>(a[key]>b[key]?1:-1)*dir);
 document.querySelector('#siteTbl tbody').innerHTML=rows.map(r=>`<tr><td>${r.name}</td><td>${r.lines}</td>
 <td>${r.ordered.toLocaleString()}</td><td>${r.shipped.toLocaleString()}</td>
 <td><span class="pill ${rag(r.fill_rate)}">${pct(r.fill_rate)}</span></td><td>${pct(r.on_time_rate)}</td></tr>`).join('');}
document.querySelectorAll('#siteTbl th').forEach(th=>th.onclick=()=>{dir=key===th.dataset.k?-dir:1;key=th.dataset.k;drawTbl();});
drawTbl();

// trend
const sel=document.getElementById('siteSel');
sel.innerHTML='<option>All sites</option>'+Object.keys(S.trend).map(s=>`<option>${s}</option>`).join('');
const pal=['#1f5fbf','#c98a00','#7b3fbf'];
const tc=new Chart(document.getElementById('trendChart'),{type:'line',data:{labels:S.days,datasets:[]},
 options:{interaction:{mode:'index',intersect:false},animation:false,scales:{y:{min:80,max:100,ticks:{callback:v=>v+'%'}}}}});
function drawTrend(){const pick=sel.value;
 tc.data.datasets=Object.keys(S.trend).filter(s=>pick==='All sites'||s===pick).map((s,i)=>({label:s,
 data:S.trend[s].map(v=>+(v*100).toFixed(2)),borderColor:pal[Object.keys(S.trend).indexOf(s)],tension:0,pointRadius:2}));
 tc.data.datasets.push({label:'Target',data:S.days.map(()=>S.targets.fill*100),borderColor:'#1e8e4e',borderDash:[6,4],pointRadius:0});
 tc.update();}
sel.onchange=drawTrend; drawTrend();

// change log
function drawLog(){const f=document.getElementById('logFilter').value;
 document.getElementById('logList').innerHTML=D.changelog.map(r=>{
  const it=r.items.filter(i=>f==='All'||i.type===f); if(!it.length)return '';
  return `<div class="rel"><h3>v${r.version}</h3><small>${r.date}</small><ul>${
   it.map(i=>`<li><span class="tag">${i.type}</span>${i.text.replace(/</g,'&lt;')}</li>`).join('')}</ul></div>`;}).join('');}
document.getElementById('logFilter').onchange=drawLog; drawLog();

// team comms (text already escaped in Python)
const avc={CG:'#1f5fbf',AM:'#7b3fbf',JT:'#1e8e4e',PO:'#c98a00'};
document.getElementById('teamList').innerHTML=D.comms.map(m=>`<div class="msg">
 <div class="av" style="background:${avc[m.initials]||'#555'}">${m.initials}</div>
 <div class="bubble"><span class="who">${m.author}</span> <span class="meta">· ${m.role} · ${m.timestamp}</span>
 ${m.ref?` <span class="ref">${m.ref}</span>`:''}<div>${m.text}</div></div></div>`).join('');
</script></body></html>"""


# -----------------------------------------------------------------------------
#  CLI ENTRY POINT
# -----------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description=f"Fill rate analyzer v{__version__}")
    ap.add_argument("--in", dest="inp", type=Path, default=DEFAULT_INPUT)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)  # [v2.0.0] now .html
    ap.add_argument("--generate-sample", action="store_true",
                    help="write sample data to --in, then build the report")
    ap.add_argument("--version", action="version", version=__version__)
    args = ap.parse_args()

    if args.generate_sample or not args.inp.exists():
        n = generate_sample_data(args.inp)
        print(f"  + generated {n} sample rows -> {args.inp}")

    lines = load_orders(args.inp)
    summary = summarise(lines)
    render_report(summary, parse_changelog(CHANGELOG_PATH),
                  load_team_comms(TEAM_COMMS_PATH), args.out)
    print(f"  + report written -> {args.out}  "
          f"(overall fill rate {summary['total']['fill_rate']:.2%})")


if __name__ == "__main__":
    main()
