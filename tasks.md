# Tasks — Execution List

Work through these one at a time. Do not start the next task until the current one is verified working.

**Status key:** `[ ]` = not started · `[~]` = in progress · `[x]` = done · `[!]` = blocked

---

## Active Sprint

### Task: Bing Ads integration — connect BingData to generate_dashboard.py
`sync_bing_to_sheet.py` writes a `BingData` tab (same schema as `GadsData`).
`generate_dashboard.py` does not yet load or use it. The Bing platform filter
button exists in the Campaign Overview tab but shows nothing without data.

**Sub-tasks:**
- [x] `sync_bing_to_sheet.py` written and ready
- [x] `detect_platform()` in `generate_dashboard.py` already handles Bing
- [x] Bing platform filter toggle exists in `dashboard/template.html`
- [x] Add `load_bing_data()` to `generate_dashboard.py` (mirror of `load_gads_data()`, returns `[]` gracefully if tab missing)
- [x] Update `build_campaign_rows()` to accept `bing_data` and add Bing aggregate rows (`__bing_*`, `platform='Bing'`)
- [x] Update JS platform filter: `r._is_gads_agg ? p === 'Google'` → `(r.platform || 'Other') === p`
- [x] Pass `bing_data` from `main()` to `build_campaign_rows()`
- [ ] Regenerate + verify (requires BingData tab to be populated by running sync_bing_to_sheet.py)

**How to test:**
- Run `generate_dashboard.py` — if BingData tab is populated, spend totals in Campaign Overview increase
- Switch platform filter to "Bing" — only Bing rows visible
- Switch to "Google" — Google-only rows

---

## Completed

### Task: Fix GadsData → CampaignsData campaign name join ✅
- [x] Add `parse_adgroup_campaign_name()` call in `build_campaign_rows()` for GadsData rows
- [x] Change join key to `(campaign_type, region, year, month)`
- [x] Verified Overview tab and Optimizations tab

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
- [x] GitHub Actions workflow: `.github/workflows/weekly-refresh.yml`
- [x] Runs every Monday 11am PST; manual trigger via `workflow_dispatch`
- [x] Syncs GadsData then regenerates + pushes `index.html`
- Note: Slack notification not added (low priority, workflow logs suffice)

---

### Task: Trend charts ✅
- [x] Monthly Spend Trend (stacked bar, by campaign type)
- [x] Monthly MQL & SQL Trend (dual line)
- [x] Cost/MQL Trend (line chart — `chart-costmql-trend`)
- [x] All fixed to last 6 months window (not period-filter dependent, by design)

---

### Task: Bing Ads integration — connect BingData to generate_dashboard.py
_(Moved to Active Sprint above)_

---

### Task: Search terms / negative keywords view ✅
- [x] `load_search_terms()` in `generate_dashboard.py`
- [x] Search Terms tab with filter buttons, search box, negative keyword suggestions
- [x] `renderSearchTermsTab()` JS function

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

### Task: Optimizations tab UX — severity filter + collapsible OK cards ✅
- [x] Severity filter bar with High/Medium/Low/OK/All buttons
- [x] Default: OK cards hidden; "Show N passing campaigns" toggle
- [x] `_optFilter`, `_optShowOk`, `applyOptFilter()`, `setOptFilter()` in JS
- [x] Sort by cost descending within severity groups

---

### Task: Ad Group Optimizations tab ✅
- [x] `compute_adgroup_optimizations()` in `generate_dashboard.py`
- [x] `ag_optimizations` key in payload
- [x] "Ad Group Issues" tab (`tab-agissues`) in `template.html`
- [x] `renderAdGroupIssuesTab()` JS function

---

### Task: Rename tab + flag MQL→SQL < 25% ✅
- [x] Tab button and section title both read "Campaign Optimizations"
- [x] Thresholds: < 15% → high, 15–24% → medium, ≥ 25% → passes

---

### Task: Overview — MQL→SQL conversion graph with 25% goal + drill-through ✅
- [x] `renderMqlSqlChart()` in Campaign Overview tab
- [x] 25% goal line; bars coloured by threshold
- [x] Clickable bars drill through to Campaign Optimizations via `drillToOpts()`
- [x] Opt-cards have stable `id` attrs; `scrollIntoView()` + 2s highlight

---

### Task: Consolidate Global → EMEA (3-region model: NAM / EMEA / APAC) ✅
- [x] `parse_campaign_meta()` and `parse_adgroup_campaign_name()` both map WW/Global → EMEA
- [x] `REGION_ORDER` in `template.html` is `['NAM', 'EMEA', 'APAC']` (no Global)

---

### Task: Search Impression Share + Lost IS (Rank) weekly charts ✅
- [x] `ImpShareWeekly` tab loaded by `load_imp_share_data()` in `generate_dashboard.py`
- [x] IS weekly chart (`chart-is-weekly`) in Overview tab with 2 lines + goal line
- [x] Campaign-level toggle filter (`is-filter-bar`, `_isFilter`) in JS
- [x] "All" mode = impression-weighted average; per-campaign toggle filters `D.is_weekly`

---

### Task: Weekly account changes tab ✅
- [x] `load_change_events()` in `generate_dashboard.py` reads `ChangeEvents` tab
- [x] "Account Changes" tab (`tab-changes`) with `renderChangesTab()` and `buildChangesNarrative()`
- [x] Narrative paragraphs by theme; "Show full change log" expand toggle
- [x] Also surfaced in Weekly Summary tab

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
- [x] "Weekly Summary" tab (`tab-summary`) in `template.html`
- [x] `renderWeeklySummaryTab()`, MoM KPI comparison, top opt issues, delta detector, actuals/projected toggle

---

### Task: Weekly Summary — current month projection ✅
- [x] `_summaryMode` ('projected'|'actuals') toggle
- [x] `daysElapsed`, `projFactor`, `isProjecting` logic
- [x] "~Mar (projected)" label; "Projected based on X/Y days elapsed" footnote

---

### Task: Account Changes — narrative summary ✅
- [x] `buildChangesNarrative(events)` groups events by theme → plain-English paragraphs
- [x] "Show full change log" expand toggle in Account Changes tab and Weekly Summary

---

### Task: Campaign Optimization insights — worst-3 ad groups + Google Ads deep links ✅
- [x] Worst-3 ad groups by cost shown per opt card (`.opt-ag-row` rows, from `D.adgroups`)
- [x] Google Ads deep link per card (`opt-gads-link`) if campaign_ids present
- [x] P1/P2 issue text uses numbered steps and includes opportunity sizing (missed SQLs)

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
