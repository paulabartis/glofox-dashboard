# Implementation Plan — Sequencing & Architecture

## Core Principle

**Do one layer at a time.** Data first, then metrics, then reporting. Never try to build the UI before the data is solid, and never add new data sources while the reporting layer is broken.

---

## Layer 1 — Data Infrastructure ✅ (Complete)

Get clean, reliable data into Google Sheets so the dashboard has a stable source of truth.

### 1a. Google Ads API connection
- Script: `scripts/sync_gads_to_sheet.py`
- Writes to `GadsData` tab: Campaign | Year | Month | Impressions | Clicks | Cost
- Writes to `AdGroupData` tab: Campaign | Ad Group | Year | Month | Impressions | Clicks | Cost
- Auth: OAuth 2.0 with refresh token stored in `~/.zshrc`
- Run manually or on a weekly schedule

### 1b. Looker/Salesforce Google Sheet
- Sheet ID: `1-M1R5RfWkQiQKvVnclI4d0KpSC1Ww042iCUv6IFe6mc`
- Tabs used: `CampaignsData` (MQL/SQL by campaign), `MonthlySummary` (aggregate KPIs)
- Access: Service account `glofox-mcp@glofoxmcp.iam.gserviceaccount.com`
- Updated by Looker export — not owned by this system

### 1c. Data quality rules
- Campaign names follow Looker convention: `SMB_Inbound_{Provider}_PPC_{Channel}_{Type}_{Region}_{Date}`
- Google Ads API returns human-readable names — handled by `parse_adgroup_campaign_name()`
- Month stored as `YYYY-MM-01` date string in API output — handled by `parse_month_from_date()`
- Only include `_PPC_` campaigns; exclude `TZ_` and `MML_` prefixes

---

## Layer 2 — Metrics & Classification ✅ (Complete)

Transform raw data into the metrics and groupings used in the dashboard.

### Campaign classification
- **Campaign type**: GymManagement, Modality, Branded, Competitor, Demand Gen, Other
- **Region**: NAM, EMEA, APAC, Global
- **Channel**: Paid Search (SEM), Paid Other (DG/DIS/SM)
- Logic in `parse_campaign_meta()` for Looker names; `parse_adgroup_campaign_name()` for Google Ads names

### Core metrics computed at generation time
| Metric | Formula | Used In |
|--------|---------|---------|
| CTR | clicks / impressions | Overview, Optimizations |
| CPC | cost / clicks | Ad Groups, Optimizations |
| Cost/MQL | cost / MQL | KPI bar, Optimizations |
| Cost/SQL | cost / SQL | KPI bar |
| MQL→SQL% | SQL / MQL | All tables |
| Severity | Rules engine (see Optimizations tab) | Optimizations tab |

### Demand Gen bucketing
DG/DIS campaigns are shown as a "Demand Gen" row in campaign type and region tables (previously excluded as "Other"). Logic: `channel == "Paid Other"` → `campaign_type = "Demand Gen"`.

---

## Layer 3 — Reporting Layer ✅ (Complete for v1)

Generate the dashboard HTML from the processed data.

### Dashboard structure
- **Script**: `scripts/generate_dashboard.py`
- **Template**: `dashboard/template.html`
- **Output**: `index.html` (root of repo, served by GitHub Pages)
- **Hosting**: `https://paulabartis.github.io/glofox-dashboard/`

### Tab structure
| Tab | Contents | Filter |
|-----|----------|--------|
| Overview | KPI bar, funnel by type, funnel by region, region×type table, Paid Search vs Other comparison | Period selector |
| Ad Groups | Ad group performance table with search box | Period selector |
| Optimizations | Campaign cards with data-driven issue list (up to 10 per campaign) | Static — always last 3 months |

---

## Layer 4 — Next Priorities (Not Yet Started)

Work through these in order. Do not start a new item until the previous one is verified working end-to-end.

### 4a. Optimizations tab — finish and test
- [ ] Add `compute_optimizations()` to `generate_dashboard.py`
- [ ] Add Optimizations tab to `dashboard/template.html`
- [ ] Regenerate and verify all campaigns show correct issues
- [ ] Verify severity color coding matches data

### 4b. Weekly sync automation
- [ ] Set up cron or scheduled task to run `sync_gads_to_sheet.py` + `generate_dashboard.py` weekly
- [ ] Add Slack or email notification when complete

### 4c. Trend charts
- [ ] Monthly spend trend line chart (cost over time by campaign type)
- [ ] MQL/SQL trend — spot seasonality and step-changes
- [ ] Cost/MQL trend — are we getting more or less efficient?

### 4d. Bing Ads integration
- [ ] Research Bing Ads API access (Microsoft Advertising API)
- [ ] Write `scripts/sync_bing_to_sheet.py`
- [ ] Add `BingData` tab to sheet with same schema as `GadsData`
- [ ] Merge into `build_campaign_rows()` alongside Google data

### 4e. Search terms / negative keywords view
- [ ] Pull `search_term_view` from Google Ads API
- [ ] Surface top wasted spend queries
- [ ] Add to a new "Search Terms" tab with negative keyword recommendations

---

## Weekly Run Procedure

Until automation is set up, run manually each Monday:

```bash
# 1. Sync Google Ads data to sheet
source ~/.zshrc
python3 scripts/sync_gads_to_sheet.py

# 2. Regenerate dashboard
python3 scripts/generate_dashboard.py

# 3. Push to GitHub Pages
git add index.html
git commit -m "chore: weekly dashboard refresh $(date +%Y-%m-%d)"
git push
```
