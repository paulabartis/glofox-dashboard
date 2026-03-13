# Tasks — Execution List

Work through these one at a time. Do not start the next task until the current one is verified working.

**Status key:** `[ ]` = not started · `[~]` = in progress · `[x]` = done · `[!]` = blocked

---

## Active Sprint

### Task: Optimizations Tab
Add a third tab to the dashboard showing data-driven campaign optimization recommendations.

**Sub-tasks:**
- [x] Add `make_display_name()` to `generate_dashboard.py`
- [ ] Add `compute_optimizations()` to `generate_dashboard.py`
- [ ] Add `"optimizations"` key to dashboard JSON payload in `main()`
- [ ] Add Optimizations tab button + div to `dashboard/template.html`
- [ ] Add CSS for opt cards (severity colour coding, metrics strip, issue bullets)
- [ ] Add `renderOptimizationsTab()` JS function
- [ ] Update tab switching to handle `opts` tab
- [ ] Regenerate `index.html` and verify all campaigns show issues
- [ ] Commit and push

**How to test:**
1. Run `python3 scripts/generate_dashboard.py` — should print "X campaign optimizations computed"
2. Open `index.html` in browser
3. Click "Optimizations" tab — should see one card per campaign
4. Check: campaigns with 0 MQLs should have a red (high severity) card
5. Check: a campaign with good metrics should show green ("No issues")
6. Check: period label on cards matches last 3 months of data

---

## Backlog

### Task: Weekly sync automation
Schedule `sync_gads_to_sheet.py` + `generate_dashboard.py` to run automatically each Monday.

**Sub-tasks:**
- [ ] Decide: cron job vs. GitHub Actions vs. Claude scheduled task
- [ ] Write the automation script/config
- [ ] Test a full automated run end-to-end
- [ ] Add success/failure notification (Slack webhook or email)

**How to test:**
- Trigger manually and confirm sheet is updated + dashboard regenerated without any manual steps

---

### Task: Trend charts
Add monthly trend line charts to the Overview tab.

**Sub-tasks:**
- [ ] Spend over time by campaign type (stacked area or line)
- [ ] MQL + SQL trend (dual line)
- [ ] Cost/MQL trend (line with target reference line)
- [ ] Hook up to period filter (chart range = selected period)

**How to test:**
- Switch period from 3M to 6M — charts should extend
- Hover over chart points — tooltips should show exact values

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

### Task: Search terms / negative keywords view
Surface the most wasteful search terms and recommend negatives.

**Sub-tasks:**
- [ ] Add `fetch_search_terms_monthly()` to `sync_gads_to_sheet.py`
- [ ] Write to `SearchTermsData` tab: Campaign | Search Term | Match Type | Impressions | Clicks | Cost | Conversions
- [ ] Add `load_search_terms_data()` to `generate_dashboard.py`
- [ ] Add "Search Terms" tab to dashboard: table sorted by cost, with "0 conversions" flag
- [ ] Add negative keyword suggestions column (based on spend > $X and conversions = 0)

**How to test:**
- Search Terms tab shows top queries by spend
- Filter to "0 conversions" rows — should be obvious waste candidates
- Spot-check a few against what's visible in Google Ads UI

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
