# PPC Workspace - Claude Code Instructions

## Rules

Read all PRD files before acting. Execute one task at a time from `tasks.md`. When done with a task, tell me what you did and how to test it.

**PRD files to read at the start of every session:**
- `masterplan.md` — What we're building and what success looks like
- `implementation.md` — Architecture, data sources, sequencing
- `design-guidelines.md` — How outputs should look and feel
- `tasks.md` — The active task list; work top to bottom, one task at a time

---

## Overview

This workspace is designed for Google Ads and Meta Ads management and PPC optimization using Claude Code. You have access to the Google Ads API, Meta Marketing API, Python utilities, and specialist agent prompts.

## Google Ads API Access

**Access Level:** Basic (production approved - or pending approval)
**Credentials:** Stored in environment variables
**Authentication:** OAuth 2.0 with refresh token

### Python Usage Pattern

```python
from google.ads.googleads.client import GoogleAdsClient
import os

# Initialize the Google Ads client
client = GoogleAdsClient.load_from_dict({
    "developer_token": os.environ["GOOGLE_ADS_DEVELOPER_TOKEN"],
    "client_id": os.environ["GOOGLE_ADS_CLIENT_ID"],
    "client_secret": os.environ["GOOGLE_ADS_CLIENT_SECRET"],
    "refresh_token": os.environ["GOOGLE_ADS_REFRESH_TOKEN"],
    "login_customer_id": os.environ["GOOGLE_ADS_CUSTOMER_ID"],
    "use_proto_plus": True
})

# Execute queries
ga_service = client.get_service("GoogleAdsService")
customer_id = "YOUR_ACCOUNT_ID"  # No dashes, numbers only

query = """
    SELECT campaign.id, campaign.name, metrics.impressions
    FROM campaign
    WHERE segments.date DURING LAST_30_DAYS
"""
response = ga_service.search(customer_id=customer_id, query=query)
```

### Common GAQL Query Patterns

#### Campaign Performance
```sql
SELECT
    campaign.id,
    campaign.name,
    campaign.status,
    metrics.impressions,
    metrics.clicks,
    metrics.cost_micros,
    metrics.conversions,
    metrics.conversions_value,
    metrics.average_cpc,
    metrics.ctr
FROM campaign
WHERE segments.date DURING LAST_30_DAYS
ORDER BY metrics.cost_micros DESC
```

#### Search Terms Report
```sql
SELECT
    search_term_view.search_term,
    search_term_view.status,
    campaign.name,
    ad_group.name,
    metrics.impressions,
    metrics.clicks,
    metrics.cost_micros,
    metrics.conversions,
    segments.keyword.info.text,
    segments.keyword.info.match_type
FROM search_term_view
WHERE segments.date DURING LAST_30_DAYS
    AND campaign.advertising_channel_type = 'SEARCH'
ORDER BY metrics.cost_micros DESC
LIMIT 1000
```

#### Keyword Performance with Quality Score
```sql
SELECT
    ad_group_criterion.keyword.text,
    ad_group_criterion.keyword.match_type,
    ad_group_criterion.status,
    campaign.name,
    ad_group.name,
    metrics.impressions,
    metrics.clicks,
    metrics.cost_micros,
    metrics.conversions,
    metrics.ctr,
    metrics.average_cpc,
    ad_group_criterion.quality_info.quality_score,
    ad_group_criterion.quality_info.creative_quality_score,
    ad_group_criterion.quality_info.post_click_quality_score,
    ad_group_criterion.quality_info.search_predicted_ctr
FROM keyword_view
WHERE segments.date DURING LAST_30_DAYS
    AND ad_group_criterion.status = 'ENABLED'
    AND campaign.status = 'ENABLED'
ORDER BY metrics.cost_micros DESC
```

#### Responsive Search Ad Performance
```sql
SELECT
    ad_group_ad.ad.id,
    ad_group_ad.ad.responsive_search_ad.headlines,
    ad_group_ad.ad.responsive_search_ad.descriptions,
    ad_group_ad.ad.final_urls,
    ad_group_ad.ad_strength,
    campaign.name,
    ad_group.name,
    metrics.impressions,
    metrics.clicks,
    metrics.conversions,
    metrics.ctr,
    metrics.cost_micros
FROM ad_group_ad
WHERE segments.date DURING LAST_30_DAYS
    AND ad_group_ad.ad.type = 'RESPONSIVE_SEARCH_AD'
    AND ad_group_ad.status = 'ENABLED'
ORDER BY metrics.impressions DESC
```

#### Asset Performance (for RSAs)
```sql
SELECT
    ad_group_ad_asset_view.field_type,
    asset.text_asset.text,
    ad_group_ad_asset_view.performance_label,
    campaign.name,
    ad_group.name,
    metrics.impressions,
    metrics.clicks,
    metrics.ctr
FROM ad_group_ad_asset_view
WHERE segments.date DURING LAST_30_DAYS
    AND ad_group_ad_asset_view.field_type IN ('HEADLINE', 'DESCRIPTION')
ORDER BY metrics.impressions DESC
```

#### Budget and Bidding
```sql
SELECT
    campaign.id,
    campaign.name,
    campaign_budget.amount_micros,
    campaign_budget.explicitly_shared,
    campaign.bidding_strategy_type,
    campaign.target_cpa.target_cpa_micros,
    campaign.target_roas.target_roas,
    metrics.cost_micros,
    metrics.impressions,
    metrics.search_impression_share,
    metrics.search_budget_lost_impression_share,
    metrics.search_rank_lost_impression_share
FROM campaign
WHERE segments.date DURING LAST_30_DAYS
ORDER BY metrics.cost_micros DESC
```

### Cost Conversion Helper

Google Ads API returns costs in micros (millionths of currency):
```python
def micros_to_currency(micros):
    """Convert micros to actual currency amount"""
    return micros / 1_000_000

# Example
cost_micros = 45670000
cost_dollars = micros_to_currency(cost_micros)  # $45.67
```

### Token Refresh

If OAuth token expires, run:
```bash
python scripts/get_google_refresh_token.py
```
Then update `GOOGLE_ADS_REFRESH_TOKEN` in your shell profile (~/.zshrc or ~/.bashrc).

---

## Meta Ads API Access

**SDK:** `facebook-business` (v24+)
**Credentials:** Stored in environment variables
**Authentication:** System User Access Token (never expires)

### Python Usage Pattern

```python
from facebook_business.api import FacebookAdsApi
from facebook_business.adobjects.adaccount import AdAccount
import os

# Initialize the Meta API client
FacebookAdsApi.init(
    app_id=os.environ["META_APP_ID"],
    app_secret=os.environ["META_APP_SECRET"],
    access_token=os.environ["META_ACCESS_TOKEN"]
)

ad_account_id = os.environ["META_AD_ACCOUNT_ID"]  # format: act_XXXXXXXXX
account = AdAccount(ad_account_id)
```

### Common Query Patterns

#### Campaign Performance
```python
insights = account.get_insights(
    fields=["campaign_name", "impressions", "clicks", "spend", "ctr", "cpc", "cpm", "actions", "purchase_roas"],
    params={"level": "campaign", "date_preset": "last_30d", "limit": 500}
)
```

#### Ad Set Performance
```python
insights = account.get_insights(
    fields=["campaign_name", "adset_name", "impressions", "clicks", "spend", "frequency", "actions"],
    params={"level": "adset", "date_preset": "last_30d", "limit": 500}
)
```

#### Ad-Level Performance
```python
insights = account.get_insights(
    fields=["campaign_name", "adset_name", "ad_name", "impressions", "clicks", "spend", "ctr", "frequency", "actions"],
    params={"level": "ad", "date_preset": "last_30d", "limit": 1000}
)
```

#### Custom Date Range
```python
params={"time_range": {"since": "2026-01-01", "until": "2026-01-31"}, "level": "campaign"}
```

### Key Differences vs Google Ads

| | Google Ads | Meta Ads |
|---|---|---|
| Query language | GAQL (SQL-like) | Python fields/params dict |
| Auth | OAuth + refresh token | System User Access Token |
| Costs | `cost_micros` / 1,000,000 | `spend` (direct dollars) |
| Hierarchy | Campaign → Ad Group → Ad | Campaign → Ad Set → Ad |
| Keywords | Yes | No (audience targeting) |

### Helper: Extract Conversion Actions

```python
def get_action_value(actions: list, action_type: str) -> float:
    """Extract a specific conversion value from the actions array."""
    if not actions:
        return 0.0
    for action in actions:
        if action.get("action_type") == action_type:
            return float(action.get("value", 0))
    return 0.0

# Common action types:
# "purchase", "lead", "add_to_cart", "initiate_checkout", "complete_registration"
```

### Token Management

System User tokens **never expire**. If you need to regenerate:
1. Business Manager → Users → System Users
2. Click your system user → "Generate New Token"
3. Update `META_ACCESS_TOKEN` in `~/.zshrc` and run `source ~/.zshrc`

### Meta API Rate Limits & Best Practices

- Use `limit` param to cap result size (500 for campaign/adset, 1000 for ads)
- Use `date_preset` for common ranges or `time_range` for custom dates
- Batch requests when pulling multiple levels (campaign + adset + ad)
- Meta API version updates every 6 months — check `facebook-business` SDK version

## Workspace Structure

```
/Users/babypau/Documents/Trainerize/2026/Claude code/
├── CLAUDE.md                    ← You are here - main instructions
├── .gitignore                   ← Protects credentials from git
├── system-prompts/
│   ├── agents/                  ← Specialist agent prompts
│   │   ├── ppc-audit-agent.md           ← Google Ads audit
│   │   ├── meta-audit-agent.md          ← Meta Ads audit
│   │   ├── negative-keyword-agent.md
│   │   ├── ad-copy-agent.md
│   │   └── script-writer-agent.md
│   └── frameworks/              ← PPC knowledge base
│       ├── core-ppc-reasoning.md
│       ├── campaign-structure.md
│       └── quality-score-framework.md
├── google-ads-scripts/          ← Google Ads scripts (JavaScript)
│   └── library/
├── scripts/                     ← Python utilities
│   ├── get_google_refresh_token.py
│   ├── fetch_campaign_data.py       ← Google Ads data fetcher
│   ├── fetch_meta_data.py           ← Meta Ads data fetcher
│   └── search_terms_analyzer.py
└── reports/                     ← Generated audit reports & exports
```

## Agent Prompts

When you need specialist assistance, reference these agent prompts:

### Google Ads Agents
- **Audit Agent** (`system-prompts/agents/ppc-audit-agent.md`) - Comprehensive Google Ads account audits
- **Negative Keyword Agent** (`system-prompts/agents/negative-keyword-agent.md`) - Search term analysis and waste identification
- **Ad Copy Agent** (`system-prompts/agents/ad-copy-agent.md`) - RSA creation and optimization
- **Script Writer Agent** (`system-prompts/agents/script-writer-agent.md`) - Google Ads script development

### Meta Ads Agents
- **Meta Audit Agent** (`system-prompts/agents/meta-audit-agent.md`) - Comprehensive Meta Ads account audits (campaigns, audiences, creatives, pixel tracking)

## PPC Frameworks

Reference these for strategic guidance:

- **Core PPC Reasoning** (`system-prompts/frameworks/core-ppc-reasoning.md`) - Fundamental principles and decision-making
- **Campaign Structure** (`system-prompts/frameworks/campaign-structure.md`) - Best practices for account architecture
- **Quality Score** (`system-prompts/frameworks/quality-score-framework.md`) - QS optimization strategies

## Preferences & Guidelines

### Code Quality
- Write production-ready code with error handling
- Include clear comments and docstrings
- Use type hints in Python when appropriate
- Follow PEP 8 for Python, Google's style guide for JavaScript

### Google Ads Scripts
- Always include a header comment block with:
  - Script purpose and description
  - Setup/installation instructions
  - Configuration variables
  - Author and date
  - Changelog
- Test scripts in preview mode before recommending deployment
- Include logging for debugging
- Use meaningful variable names

### Analysis & Recommendations
- Always base recommendations on actual data, not assumptions
- Include specific examples: campaign names, keyword text, actual metrics
- Prioritize by impact: (spend at risk) × (likelihood of improvement)
- Provide clear, actionable next steps
- Include "what's working well" sections to avoid breaking successful elements
- Consider statistical significance before making recommendations

### Data Presentation
- Format currency values clearly (e.g., $1,234.56)
- Use percentages for rates (CTR, conversion rate, etc.)
- Round to appropriate precision (2 decimal places for money, 1-2 for percentages)
- Sort tables by most impactful metric (usually spend or conversions)
- Highlight outliers and anomalies

### Reporting
- Save audit reports to `reports/` folder with date stamps
- Use markdown for reports (easy to read and version control)
- Include executive summary at the top
- Structure with clear sections and headings
- Use tables for data, lists for recommendations

## Account-Specific Context

**TODO: Add your specific context here:**

- Target CPA: $_____
- Target ROAS: _____
- Brand terms: _____
- Negative keyword themes to always apply: _____
- Industry vertical: _____
- Geographic targets: _____
- Business hours: _____
- Seasonality factors: _____

## Quick Command Examples

### Google Ads
```
"Pull last 30 days campaign performance and identify waste"
"Analyze search terms and build negative keyword list"
"Audit account [CUSTOMER_ID] using the audit agent"
"Write a script to pause keywords with 0 conversions and $100+ spend"
"Generate 15 RSA headlines for [product/service]"
"Compare top 3 campaigns and recommend budget allocation"
```

### Meta Ads
```
"Pull last 30 days Meta campaign performance and identify waste"
"Audit my Meta account using the meta-audit-agent"
"Find ads with high frequency and low CTR — creative fatigue report"
"Compare ad set audiences and identify overlap"
"Find all ads with spend but zero purchases"
"Recommend budget reallocation across Meta campaigns"
"Analyze creative performance and identify top/bottom performers"
```

## API Rate Limits & Best Practices

### Google Ads
- Google Ads API has generous rate limits but batch queries when possible
- Use `LIMIT` clauses to prevent massive data pulls
- Date range should be specific (use `DURING LAST_30_DAYS` or `BETWEEN '2026-01-01' AND '2026-01-31'`)
- Cache results when doing multiple analyses on the same data
- For large accounts, focus queries on specific campaigns or date ranges

### Meta Ads
- Use `limit` param to cap result size (500 for campaign/adset, 1000 for ads)
- Use `date_preset` for common ranges or `time_range` dict for custom dates
- Batch requests when pulling campaign + adset + ad data in one session
- Meta throttles by app — if hitting limits, add delays between calls
- API version updates every 6 months — check `facebook-business` SDK changelog

## Security Notes

- Never commit credentials to git
- All API keys/tokens stored in environment variables
- Use `.gitignore` to prevent accidental credential exposure
- Never log or display full tokens/secrets in output
