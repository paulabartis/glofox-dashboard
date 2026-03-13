# Tasks — Execution List

Work through these one at a time. Do not start the next task until the current one is verified working.

**Status key:** `[ ]` = not started · `[~]` = in progress · `[x]` = done · `[!]` = blocked

---

## Active Sprint

### Task: Fix GadsData → CampaignsData campaign name join
Google Ads API returns human-readable names ("Gym Management USA") but CampaignsData
uses Looker-style names ("SMB_Inbound_Google_PPC_SEM_GymMgmt_USA_010125"). The join
in `build_campaign_rows()` never matches, so all campaign_rows have cost=0. Until this
is fixed, the Optimizations tab can only surface MQL/SQL rules (not cost/CTR/CPC).

**Root cause:** `build_campaign_rows()` joins on `(name, year, month)` — the names
never match so all 361 rows come from the CampaignsData-only secondary path.

**Options:**
- A. Build a lookup table mapping Google Ads readable names → Looker names (manual, brittle)
- B. Re-key the join on `(campaign_type, region, year, month)` so GadsData is aggregated
  by type+region and merged into CampaignsData rows of the same type+region
- C. Add a `campaign_mapping` tab to the Google Sheet (one-time manual exercise, most reliable)

**Recommended: Option B** — use `parse_adgroup_campaign_name()` on GadsData rows to get
campaign_type+region, then aggregate and join on that key.

**Sub-tasks:**
- [x] Add `parse_adgroup_campaign_name()` call in `build_campaign_rows()` for GadsData rows
- [x] Change join key from `(name, year, month)` to `(campaign_type, region, year, month)` for cost/imp/click data
- [x] Verify Overview tab spend totals make sense after the fix — $4.1M total cost now in payload
- [x] Verify Optimizations tab now shows cost/CPC/CTR insights for Search campaigns — 15 type+region cards, all with real spend
- [x] Commit and push (commit 0c44b1a — push pending PAT)

**How to test:**
- Run `generate_dashboard.py` — campaign rows should show cost > 0 for Google Search campaigns
- Overview KPI bar spend total should increase (currently $0 because no rows have cost)
- Optimizations tab: should see HIGH severity cards for campaigns with spend but 0 MQLs

---

## Completed

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

### Task: Optimizations tab UX — severity filter + collapsible OK cards
The Optimizations tab currently shows all 15 cards in a flat grid. Make it easier to triage.

**Desired behaviour:**
- Summary bar at the top: `🔴 0 High  🟡 6 Medium  🟢 9 OK` — clickable to filter
- Default view shows only High + Medium cards; OK cards collapsed into a "9 campaigns with no issues — show all" toggle
- Clicking the toggle expands OK cards inline (no page reload)
- Severity filter buttons: All / High / Medium / Low / OK — deactivates others when clicked
- Sort order within each severity group: by cost descending (highest spend first)

**Sub-tasks:**
- [ ] Add severity summary bar (counts + clickable filter) above the opt-grid in `template.html`
- [ ] Default state: hide OK cards, show "Show N passing campaigns" expand link
- [ ] Add JS filter logic — toggle active severity, re-render grid
- [ ] Sort within groups by descending cost
- [ ] No Python changes needed — data is already in the payload

**How to test:**
- Load Optimizations tab — only Medium cards visible by default
- Click "Show 9 passing" → OK cards appear below
- Click "High" filter button → only High cards remain (or "None for this period")
- Click "All" → full grid restored

---

### Task: Ad Group Optimizations tab
A fourth tab showing ad-group-level issues — mirrors the Optimizations tab but uses AdGroupData (which has real impressions/clicks/cost per ad group from GadsData).

**Why:** Campaign-level cards tell you *which campaign type* has a problem. Ad group cards tell you *exactly which ad group* to fix.

**Flagged issues per ad group (in priority order):**
- P1: Cost > $200 in window, 0 clicks (budget burning with no traffic — bid too low, Quality Score, or targeting issue)
- P1: Cost > $200 in window, CTR < 0.2% (severely under-performing on Search)
- P2: CPC > 2× campaign-type average (overpaying relative to peers)
- P2: Impressions > 5k but CTR < 0.5% on Search (messaging/relevance issue)
- P3: 0 impressions in window despite being an active ad group in prior months (may have gone dormant)

**Implementation notes:**
- Data already in payload: `D.adgroups` (campaign, adgroup, campaign_type, region, impressions, clicks, cost)
- Aggregate AdGroupData over the last 3 months (same window as Optimizations)
- Group by (campaign, adgroup) — each card is one ad group
- Group cards by campaign name in the UI (same pattern as the Ad Groups tab)
- No new Python data loading needed; new `compute_adgroup_optimizations()` function reads existing `adgroup_data`

**Sub-tasks:**
- [ ] Add `compute_adgroup_optimizations()` to `generate_dashboard.py`
- [ ] Add `"adgroup_optimizations"` key to dashboard JSON payload
- [ ] Add "Ad Group Issues" tab button + div to `template.html`
- [ ] Add CSS for ad group issue cards (reuse opt-card styles, add campaign group header)
- [ ] Add `renderAdGroupOptimizationsTab()` JS function
- [ ] Update tab switching to handle the new tab
- [ ] Regenerate and verify — check that flagged ad groups match what you'd expect from the Ad Groups tab

**How to test:**
- Switch to Ad Group Issues tab — cards appear grouped by campaign name
- Find an ad group with high cost and low CTR in the Ad Groups tab — confirm it's flagged here
- An ad group with healthy CTR and CPC should show as OK (or not appear if filtering to issues-only)

---

### Task: Rename tab + flag MQL→SQL < 25% as medium/red in Campaign Optimizations
Two small changes to the Optimizations tab and its Python data.

**Changes:**
1. **Rename tab label** "Optimizations" → "Campaign Optimizations" (nav button + section title in `template.html`)
2. **Lower MQL→SQL threshold from 10% → 25%** in `compute_optimizations()` in `generate_dashboard.py`:
   - MQL→SQL < 15% → `high` (red)
   - MQL→SQL 15–24% → `medium` (amber)
   - MQL→SQL ≥ 25% → no issue on this rule (passes)
   - Only applies when MQL > 0 (skip if no lead data)

**Sub-tasks:**
- [ ] Update nav button text and section title in `template.html`
- [ ] Update MQL→SQL thresholds in `compute_optimizations()` (`generate_dashboard.py`)
- [ ] Regenerate + verify — expect more medium/high cards since 25% is a tighter target
- [ ] Push

**How to test:**
- Tab label reads "Campaign Optimizations"
- A campaign type+region with, say, 20% MQL→SQL shows as medium (amber)
- One with 10% shows as high (red)
- One with 30% no longer has an MQL→SQL issue flagged

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

### Task: Weekly account changes tab
Show what changed in the Google Ads account week-over-week — new/paused campaigns, significant budget or spend shifts, new ad groups.

**Why:** Currently you have to log into Google Ads UI to see what changed. This surfaces the most operationally relevant changes directly in the dashboard.

**Data source options (pick one):**
- A. Google Ads `change_event` resource — logs every manual change (campaign status, budget edits, bid changes, ad approvals). Requires adding a new GAQL query in `sync_gads_to_sheet.py` and a new `ChangeEvents` sheet tab.
- B. Computed diff — compare this week's GadsData snapshot with last week's (requires storing two snapshots). Simpler but only catches spend/impression shifts, not structural changes.

**Recommended: Option A** — richer and more actionable (shows who made what change and when).

**GAQL query needed:**
```sql
SELECT
    change_event.change_date_time,
    change_event.user_email,
    change_event.change_resource_type,
    change_event.resource_change_operation,
    change_event.changed_fields,
    campaign.name
FROM change_event
WHERE change_event.change_date_time DURING LAST_14_DAYS
ORDER BY change_event.change_date_time DESC
LIMIT 200
```

**Sub-tasks:**
- [ ] Decide: Option A (change_event API) vs Option B (computed diff)
- [ ] If Option A: add `fetch_change_events()` to `sync_gads_to_sheet.py`, write to `ChangeEvents` tab
- [ ] Add `load_change_events()` to `generate_dashboard.py`
- [ ] Add "Changes" tab to `template.html` — table: Date | Who | Resource | Change | Campaign
- [ ] Group by week, highlight this week vs last week
- [ ] Filter out noise (minor automated bid adjustments)

**How to test:**
- Make a test change in Google Ads (e.g., pause/unpause a campaign), run sync, confirm it appears in the Changes tab

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
