# Masterplan — Glofox Paid Media Analytics Tool

## What We're Building

A paid search analytics dashboard and weekly reporting system for the Glofox paid ads team. It connects to Google Ads API and the Looker/Salesforce data export in Google Sheets, surfaces the metrics that matter for decision-making, and tells the team exactly what to action on each week — without having to manually dig through platform UIs or export spreadsheets.

The output is a static HTML dashboard (hosted on GitHub Pages) that is regenerated weekly via a Python script. No login, no backend, no maintenance overhead.

---

## Who It's For

**Primary user:** Paid ads manager / PPC lead at Glofox
**Secondary user:** Marketing leadership (quick read on spend efficiency and pipeline contribution)

The ads team should open this once a week and immediately know:
- How each campaign performed vs. prior period
- Where spend is being wasted or underperforming
- Which campaigns are driving pipeline (MQL → SQL)
- What the top 3–5 actions are for this week

---

## Data Sources

| Source | What It Provides | Access Method |
|--------|-----------------|---------------|
| Google Ads API | Impressions, clicks, cost, CPC, CTR by campaign + ad group | Python (`google-ads` SDK), `scripts/sync_gads_to_sheet.py` |
| Google Sheet (Looker export) | MQL, SQL, cost by campaign (Salesforce-sourced) | Google Sheets API, service account auth |
| Google Sheet (MonthlySummary) | Aggregate KPIs: total spend, MQL, SQL, CW, CAC, Cost/MQL, Cost/SQL | Same sheet as above |
| Bing Ads | (Future) Impressions, clicks, cost | Not yet connected |
| Meta Ads | (Future) For Demand Gen campaigns | Separate MCP server |

---

## What Success Looks Like

**For the weekly user:**
- Open dashboard in < 5 seconds (static HTML, no load time)
- Understand performance in < 2 minutes without digging
- Have a clear list of this week's actions ready without manual analysis

**Measurable outcomes:**
- Weekly reporting time cut from ~2–3 hours to < 30 minutes
- No more "I need to check the platform" for standard questions
- Every week's optimization actions are data-backed and prioritised by spend impact

**Dashboard must answer these questions without any clicks:**
1. How much did we spend, and how many MQLs/SQLs did it generate?
2. Which campaign types and regions are performing vs. underperforming?
3. What's our cost/MQL and cost/SQL trend over time?
4. Which campaigns have issues this week? (high CPC, low CTR, 0 MQLs, etc.)
5. What should we do about it? (actionable, prioritised)

---

## Scope Boundaries

**In scope:**
- Google Ads (Search, Demand Gen, Display) — campaign + ad group level
- Looker/Salesforce MQL + SQL attribution
- Weekly static HTML dashboard
- Optimization recommendations tab (data-driven, up to 10 per campaign)
- GitHub Pages hosting

**Out of scope (for now):**
- Bing Ads integration
- Meta Ads integration in the dashboard (tracked separately)
- Keyword-level analysis
- Automated bid changes or campaign edits
- Real-time data (weekly sync is sufficient)
