# Tasks — Execution List

Work through these one at a time. Do not start the next task until the current one is verified working.

**Status key:** `[ ]` = not started · `[~]` = in progress · `[x]` = done · `[!]` = blocked

---

## Active Sprint

*(No active task — pick next from backlog)*

---

## Follow-Up Items (from session Mar 19, 2026)

- [ ] **LP GA4 check (Friday Mar 27)** — re-pull GA4 for `/lp/gym-management-software-revenue/` and `/lp/fitness-management-software-revenue/` after 7 days live. Compare CVR and bounce rate vs old pages (old baselines: Gym 3.74% CVR / 55.6% bounce; Fitness 2.79% CVR / 51.1% bounce).
- [ ] **Confirm ad group routing** — ask Aman: have all 131 active ad groups been re-pointed to new `/lp/` URLs? If some still hit old `/gym-management-software-revenue/` URLs you're running split traffic unintentionally.
- [ ] **Page speed check** — run PageSpeed Insights on both new `/lp/` pages. Bounce rate jumped ~19 pts (Gym) and ~16 pts (Fitness) vs old pages — slow mobile load is a likely cause.
- [ ] **Momence switch offer** — Mindbody offer confirmed (Pay 3mo get 2 free on Google). Confirm if Momence gets same offer or different terms before dedicated Momence campaign launches.
- [ ] **Salesforce promo tracking** — confirm "Switch From Mindbody 2026" promo code is being captured in Salesforce so Mindbody campaign SQLs can be attributed correctly.
- [ ] **Pause legacy competitor ad groups** — once dedicated Mindbody + Momence campaigns are live, pause existing Mindbody/Momence ad groups in the general Competitor campaigns to avoid audience overlap.
- [ ] **Switch-to LP design** — was due Mar 19, still in progress as of session end. Chase status — this is the primary LP dependency for the Mindbody campaign now live on Google.

---

## Completed

### Task: Fix GadsData → CampaignsData campaign name join ✅
Re-keyed join from `(name, year, month)` to `(campaign_type, region, year, month)`. GadsData aggregated per type+region as synthetic rows; `compute_optimizations()` groups by (campaign_type, region) to combine real cost with real MQL/SQL. Commit 0c44b1a.

---

### Task: Optimizations Tab ✅
- [x] Add `make_display_name()` to `generate_dashboard.py`
- [x] Add `compute_optimizations()` to `generate_dashboard.py`
- [x] Add `"optimizations"` key to dashboard JSON payload in `main()`
- [x] Add Optimizations tab button + div to `dashboard/template.html`
- [x] Add CSS for opt cards (severity colour coding, metrics strip, issue bullets)
- [x] Add `renderOptimizationsTab()` JS function
- [x] Update tab switching to handle `opts` tab
- [x] Regenerate and verify — 57 campaigns, 13 medium (MQL→SQL < 10%)
- [x] Commit and push

**Note:** Cost/CTR/CPC rules are now live. The fix separated the two data sources
rather than forcing a lossy name join: GadsData is aggregated per (campaign_type,
region, year, month) and added as synthetic rows; compute_optimizations() groups
by (campaign_type, region) to combine real cost with real MQL/SQL.

---

## Backlog

### Task: Weekly sync automation ✅
GitHub Actions workflow (`.github/workflows/weekly-refresh.yml`) — runs every Monday 6AM UTC. All 6 secrets set. Manual test run succeeded 2026-03-19: `github-actions[bot]` committed `chore: refresh dashboard 2026-03-19`.

---

### Task: Trend charts ✅

**Sub-tasks:**
- [x] Spend over time by campaign type (stacked bar)
- [x] MQL + SQL trend (dual line)
- [x] Cost/MQL trend (line chart — target reference line deferred to "Cost/MQL target line" task)
- [x] Hook up to period filter — `renderTrendCharts(fromYM, toYM)` filters months to selected range

---

### Task: Bing Ads integration
Pull Bing search campaign data into the same pipeline.

**Sub-tasks:**
- [ ] Get Microsoft Advertising API credentials
- [ ] Write `scripts/sync_bing_to_sheet.py`
- [ ] Add `BingData` tab to sheet (same schema as `GadsData`)
- [ ] Update `build_campaign_rows()` to merge Bing data
- [ ] Update `is_paid_ppc()` / `parse_campaign_meta()` for Bing campaign naming convention if different

**How to test:**
- After sync, `BingData` tab should have rows
- Overview tab spend totals should increase (Bing campaigns were previously MQL-only via CampaignsData)

---

### Task: Search terms / negative keywords view ✅
`SearchTermsData` sheet tab (5,000 rows, 3 months). Dashboard "Search Terms" tab with All / Zero conversions / Suggested negatives ($5+ spend, 0 conv) filters + search box + summary line.

---

### Task: Cost/MQL target line
Show a reference line on the Cost/MQL KPI card indicating the team's target.

**Sub-tasks:**
- [ ] Add `target_cp_mql` to `CLAUDE.md` account context section (user fills in)
- [ ] Pass target into dashboard payload
- [ ] Show as sub-text on KPI card: "Target: $XXX" with green/red colour vs actual

**How to test:**
- Set a test target value, regenerate, confirm the KPI card shows target and colours correctly

---

### Task: Add Cost/SQL trend chart
Add Cost/SQL as a second line on the existing Cost per MQL trend chart (or as a separate chart section), so spend efficiency per closed opportunity is visible alongside Cost/MQL.

**Options:**
- A. Add Cost/SQL as a second line on `chart-costmql-trend` (dual-axis or same axis if scales are similar)
- B. Add a separate `chart-costsql-trend` canvas below the Cost/MQL chart

**Recommended: Option A** — keep efficiency metrics together for easy comparison; use same Y axis if Cost/SQL is in a similar range, otherwise add a second Y axis.

**Sub-tasks:**
- [ ] Compute `costByMonth / sqlByMonth` per month in `renderTrendCharts()`
- [ ] Add Cost/SQL dataset to `chart-costmql-trend` (amber/orange line — `#D97706`)
- [ ] Update chart title and tooltip to reflect both metrics
- [ ] Verify months with no SQL data show `null` (bridged by `spanGaps`)

**How to test:**
- Cost/MQL trend chart shows two lines (purple = Cost/MQL, amber = Cost/SQL)
- Tooltips show both values for each month
- Changing period selector updates both lines

---

### Task: Optimizations tab UX — severity filter + collapsible OK cards ✅

**Sub-tasks:**
- [x] Severity summary bar (counts + clickable filter) above the opt-grid in `template.html`
- [x] Default state: hide OK cards, show "Show N passing campaigns" expand link
- [x] JS filter logic — toggle active severity, re-render grid
- [x] Sort cards by severity (high→medium→low→ok) then cost descending within each group
- [x] Severity group headings replace type headings (type still shown as badge on each card)

---

### Task: Ad Group Optimizations tab ✅

**Sub-tasks:**
- [x] Add `compute_adgroup_optimizations()` to `generate_dashboard.py`
- [x] Add `"adgroup_optimizations"` key to dashboard JSON payload
- [x] Add "Ad Group Issues" tab button + div to `template.html`
- [x] Add CSS for ad group issue cards (reuse opt-card styles, add campaign group header)
- [x] Add `renderAdGroupOptimizationsTab()` JS function
- [x] Update tab switching to handle the new tab
- [x] Regenerate and verify

---

### Task: Rename tab + flag MQL→SQL < 25% as medium/red in Campaign Optimizations ✅

**Sub-tasks:**
- [x] Update nav button text and section title in `template.html`
- [x] Update MQL→SQL thresholds in `compute_optimizations()` (`generate_dashboard.py`)
- [x] Regenerate + verify — expect more medium/high cards since 25% is a tighter target
- [x] Push

---

### Task: Overview — MQL→SQL conversion graph with 25% goal + drill-through to Optimizations
Show a bar chart of MQL→SQL conversion rate by campaign type+region with a 25% goal line. Any bar below 25% is clickable and jumps to that campaign's card in the Optimizations tab.

**Desired behaviour:**
- Bar chart on the Overview tab: one bar per campaign type (or type×region) showing MQL→SQL %
- Horizontal reference line at 25% (the goal), labelled "Goal: 25%"
- Bars below 25% rendered in red/amber; bars at or above in green
- Clicking an under-performing bar navigates to the Optimizations tab and scrolls/highlights the matching card
- Works with the current period filter (chart updates when period changes)

**Implementation notes:**
- Data already in `D.campaigns` — group by `campaign_type` or `(campaign_type, region)` and compute `sum(sql)/sum(mql)` for the selected period
- Chart: pure SVG or lightweight canvas (no extra library needed — same pattern as the existing Paid Search bar chart)
- Deep-link: switch to Opts tab (`showTab('opts')`) then `scrollIntoView()` the matching `.opt-card` and flash it (CSS keyframe highlight)
- Opt cards need a stable `id` attr like `id="opt-card-GymManagement-NAM"` for the scroll target
- No Python changes needed — all data already in payload

**Sub-tasks:**
- [ ] Add conversion rate bar chart (SVG) to Overview tab below the funnel tables
- [ ] Draw 25% goal line across chart
- [ ] Colour bars: green ≥ 25%, amber 15–24%, red < 15%
- [ ] Add `id` attributes to opt-cards in `renderOptimizationsTab()` for deep-link targets
- [ ] On bar click: switch to Opts tab, scroll to card, briefly highlight it
- [ ] Hook chart to period filter (re-draw on period change)

**How to test:**
- Load Overview — chart appears with correct bars and 25% line
- Click a red bar — Optimizations tab opens, matching card is visible and briefly highlighted
- Change period — chart updates to match new date range

---

### Task: Consolidate Global → EMEA (3-region model: NAM / EMEA / APAC)
Global campaigns (WW targeting) should roll up into EMEA so all reporting uses exactly 3 regions.

**Target region mapping:**
| Current value | New value |
|---------------|-----------|
| `NAM` | `NAM` (unchanged — US + CA) |
| `EMEA` | `EMEA` (unchanged — UK + EU) |
| `APAC` | `APAC` (unchanged — AU) |
| `Global` | `EMEA` (merge into EMEA) |

**Files to change:**
- `scripts/generate_dashboard.py` — `parse_campaign_meta()` and `parse_adgroup_campaign_name()`: anywhere `WW` / `Global` currently maps to `"Global"`, change to `"EMEA"` instead
- `dashboard/template.html` — remove `Global` from `REGION_ORDER` array and any region label/colour references

**Sub-tasks:**
- [ ] Update `parse_campaign_meta()` in `generate_dashboard.py`: `WW` → `"EMEA"`
- [ ] Update `parse_adgroup_campaign_name()` in `generate_dashboard.py`: `WW` → `"EMEA"`
- [ ] Remove `"Global"` from `REGION_ORDER` in `template.html`
- [ ] Verify region labels dict in `template.html` has no orphaned `Global` entry
- [ ] Regenerate + verify funnel-by-region table shows exactly NAM / EMEA / APAC rows
- [ ] Push

**How to test:**
- Funnel by Region table: 3 rows only (NAM, EMEA, APAC) — EMEA spend/MQL/SQL should be visibly higher than before (absorbing ex-Global rows)
- No `Global` row anywhere in Overview or Campaign Optimizations tab
- Campaign Optimizations cards: any previously labelled `Global` now show `EMEA` badge

---

### Task: Search Impression Share + Lost IS (Rank) weekly charts ✅

**Sub-tasks:**
- [x] Add `fetch_impression_share_weekly()` to `sync_gads_to_sheet.py`, write to `ImpShareWeekly` tab
- [x] Add `load_is_weekly()` to `generate_dashboard.py`, include in payload as `is_weekly`
- [x] Add IS chart widget to Overview tab in `template.html` (line chart, 2 series)
- [x] Add goal line at 60% IS
- [x] Run sync + regenerate + verify chart renders with real data
- [x] Push

---

### Task: IS chart — campaign-level toggle filter ✅
Commit e86f479.

**Sub-tasks:**
- [x] Add `campaign_name` column to IS fetch query + sheet write
- [x] Update `load_is_weekly()` in `generate_dashboard.py` to include campaign field
- [x] Add filter toggle bar above `chart-is-weekly` canvas in `template.html`
- [x] JS: build per-campaign aggregates on the fly from `D.is_weekly` when filter changes

---

### Task: Weekly account changes tab ✅
Used Option A (change_event API).

**Sub-tasks:**
- [x] Add `fetch_change_events()` to `sync_gads_to_sheet.py`, write to `ChangeEvents` tab
- [x] Add `load_change_events()` to `generate_dashboard.py`
- [x] Add "Account Changes" tab to `template.html`
- [x] Group by week, highlight this week vs last week

---

### Task: Date range selector — custom week/date picker across all tabs
Allow selecting specific date ranges (e.g. 15 Feb – 28 Feb) and have all charts, tables, KPIs, and insights update accordingly.

**Why:** The current period filter uses month-level presets. Weekly analysis (Sun–Sat) is the primary use pattern but isn't directly supported. A freeform date picker lets you isolate any specific window.

**Desired behaviour:**
- Date picker replaces or extends the current filter bar — two inputs: "From" and "To" (date, not just month)
- Quick presets remain: "Last 7 days", "Last 28 days", "Last 3 months", "This year", custom
- Selecting a range re-renders all Overview charts, KPI bar, funnel tables, Optimizations tab, Ad Group Issues tab
- Week = Sunday–Saturday (highlight weekly boundaries in calendar if possible)
- IS weekly chart is separate (always shows last 16 weeks) — not affected
- Trend charts always show all-time — not affected

**Implementation notes:**
- Current period filter uses `fromYM` / `toYM` (YYYY-MM strings) — upgrade to full date (`fromDate` / `toDate`)
- All `D.campaigns` filtering currently slices by year+month; upgrade to include partial-month day-level filtering if data supports it (it does — GadsData has `date` column)
- Use native HTML `<input type="date">` — no library needed

**Sub-tasks:**
- [ ] Replace month dropdowns with `<input type="date">` pickers in the filter bar
- [ ] Update `filterCampaigns()` JS to filter by date range (not just year/month)
- [ ] Update quick presets to compute exact start/end dates (not month boundaries)
- [ ] Verify all tabs re-render correctly on date change
- [ ] Add "Glofox week" preset: Sun–Sat of the most recent complete week

**How to test:**
- Select 15 Feb – 28 Feb → KPI bar and charts update to that exact window
- Select "Last 7 days" → same as selecting last Sun–Sat
- Select a single week → Optimizations tab updates to that week's data

---

### Task: Adjustable widget sizes (1/3 · 2/3 · 3/3 layout)
Make dashboard sections/charts resizable — each widget can be set to 1/3, 2/3, or 3/3 of the page width, similar to Mixpanel's dashboard layout.

**Why:** Currently every section spans 100% width. Smaller charts like KPI cards or the MQL bar chart don't need full width; stacking them side by side would let more data fit on screen.

**Desired behaviour:**
- Each `<div class="section">` gets a width toggle in its top-right corner: `⅓` `⅔` `3/3`
- Sections in the same "row" flow horizontally (CSS grid or flexbox wrapping)
- Default widths: KPI bar = 3/3, funnel tables = 2/3 + 1/3, charts = 1/2 + 1/2
- Layout persists in `localStorage` per section id so it survives page refresh
- On mobile (< 768px) always render 3/3 (full width) regardless of setting

**Implementation notes:**
- Add a `data-widget-id` attr to each section div
- Toggle buttons inject a CSS class (`w-33`, `w-66`, `w-100`) that maps to grid `grid-column: span N`
- Wrap the Overview tab content in a `<div class="widget-grid">` with `grid-template-columns: repeat(3, 1fr)`
- `localStorage.setItem('widget-sizes', JSON.stringify({...}))` on every toggle

**Sub-tasks:**
- [ ] Wrap Overview sections in a 3-column CSS grid container
- [ ] Add size toggle buttons (⅓/⅔/3/3) to each section header
- [ ] Add CSS for `w-33`, `w-66`, `w-100` classes
- [ ] Add JS to toggle size and persist to localStorage
- [ ] Load saved sizes on init
- [ ] Add responsive override: all sections = full width below 768px

**How to test:**
- Toggle a chart to ⅓ → it shrinks to one column
- Refresh page → size is remembered
- Resize browser to mobile width → all sections go full width

---

### Task: Weekly executive summary tab ✅

**Sub-tasks:**
- [x] Add "Weekly Summary" tab button + div to `template.html`
- [x] Add `renderWeeklySummaryTab()` JS function
- [x] Build week-over-week comparison from `D.campaigns`
- [x] Build "what changed" section from `D.change_events`
- [x] Build "got better / worse" delta detector
- [x] Build "top issues" list from `D.optimizations`

---

### Task: Weekly Summary — current month projection ("on track to land X") ✅
Commit 022bd80.

**Sub-tasks:**
- [x] Detect if `thisMo` is the current calendar month
- [x] Compute `daysElapsed` / `daysInMonth`, scale Spend/MQL/SQL
- [x] Update KPI card labels to show "~Mar (projected)" vs "Feb"
- [x] Add footnote: "Projected based on X/Y days elapsed"

---

### Task: Account Changes — narrative summary ✅
Commit 87498a8.

**Sub-tasks:**
- [x] Write `buildChangesNarrative(events)` JS function
- [x] Replace default view in Account Changes tab with narrative div
- [x] Add "Show full change log" toggle revealing the table

---

### Task: Campaign Optimization insights — make them more actionable
Current optimization cards show vague generic advice. Replace with specific, numbered next actions and opportunity sizing.

**Why:** "Review lead scoring thresholds" is not actionable. "Raise keyword bids in [Ad Group X] — you lost 40% of impressions to rank" is.

**Changes needed:**

**1. Show top 3 worst ad groups within each card**
Currently cards are at campaign_type × region level. Add a "Worst ad groups this period" sub-section to each card using `D.adgroups` — top 3 by cost with the relevant issue metric (CTR, CPC, 0 MQLs).

**2. Rewrite issue text to be specific and numbered**
Replace:
- ❌ "Review lead scoring thresholds"
- ✅ "1. Check if sales are rejecting MQLs from [campaign type] — current accept rate is X%. 2. Lower MQL score threshold by 5 points and monitor SQL volume for 2 weeks."

Replace:
- ❌ "A/B test new RSA headlines"
- ✅ "1. Open Gym Mgmt · NAM in Google Ads → Ads → review asset performance. 2. Pause 'LOW' rated headlines. 3. Add 3 new headlines focused on [top keyword theme]."

**3. Add opportunity sizing to P1/P2 issues**
For each issue, show: "Fixing this to benchmark would save ~$X/mo" or "generate ~N more SQLs/mo."

**4. Add direct Google Ads UI deep links**
Add a "Open in Google Ads →" link that opens the campaign directly in the Google Ads UI (URL: `https://ads.google.com/aw/campaigns?campaignId=XXX`). Needs campaign IDs in the payload (add to sync script).

**Sub-tasks:**
- [ ] Add worst-3 ad groups sub-section to each opt card (JS only — data already in `D.adgroups`)
- [ ] Rewrite P1/P2 issue text in `compute_optimizations()` to be numbered action steps
- [ ] Add opportunity sizing calculation (delta from benchmark × avg period)
- [ ] Add `fetch_campaign_ids()` to `sync_gads_to_sheet.py` — store campaign name → ID mapping
- [ ] Pass campaign IDs through payload → add "Open in Google Ads →" link on each card

**How to test:**
- Each card shows 1–3 worst ad groups with their metric (not just campaign type totals)
- Issue text reads as a numbered to-do list, not a suggestion
- P1 issues show "~$X wasted" or "~N SQLs missed" opportunity size

---

## Completed

- [x] Google Ads API connection (`sync_gads_to_sheet.py`)
- [x] AdGroupData tab + `fetch_adgroup_monthly()`
- [x] Dashboard generator (`generate_dashboard.py`)
- [x] Overview tab — KPI bar, funnel by type, funnel by region, region×type table
- [x] Paid Search vs Paid Other comparison card + chart
- [x] Period filter (quick presets + custom from/to)
- [x] Demand Gen bucketing (DG/DIS campaigns shown as "Demand Gen" row)
- [x] Ad Groups tab with search box
- [x] Fix month parsing bug (`parse_month_from_date` — `YYYY-MM-01` string from Google Ads API)
- [x] GitHub Pages deployment
