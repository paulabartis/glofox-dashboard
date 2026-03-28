"""
LinkedIn Ads → Google Sheet Sync (Glofox account)

Pulls LinkedIn Sponsored campaign data monthly and writes to the ChannelSummary tab.
Uses LinkedIn Marketing API v2 (Analytics API).

Setup:
    1. Create a LinkedIn App at https://developer.linkedin.com and request
       r_ads and r_ads_reporting permissions.
    2. Obtain an OAuth 2.0 access token with those scopes.
    3. Add to ~/.zshrc:
       export LINKEDIN_ACCESS_TOKEN="AQX..."
       export LINKEDIN_GF_ACCOUNT_ID="XXXXXXXX"  # numeric account ID (no urn: prefix)

    2. Run: python scripts/sync_linkedin_to_sheet.py
            python scripts/sync_linkedin_to_sheet.py --months 3

Required packages: requests, google-auth, google-api-python-client

Author: Claude Code
Created: 2026-03-27
"""

import argparse
import base64
import json
import os
from calendar import monthrange
from datetime import date

import requests
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

# ── Constants ─────────────────────────────────────────────────────────────────

SHEET_ID = "1-M1R5RfWkQiQKvVnclI4d0KpSC1Ww042iCUv6IFe6mc"
CHANNEL_SUMMARY_TAB = "ChannelSummary"
SHEETS_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
LI_API_BASE = "https://api.linkedin.com/v2"
SOURCE_KEY = "linkedin"
CHANNEL_LABEL = "LinkedIn Sponsored"
CHANNEL_TYPE = "sql"

CHANNEL_SUMMARY_HEADERS = [
    "Month", "Channel", "ChannelType", "Source", "Budget", "Spend",
    "Impressions", "CPM", "Clicks", "CTR", "CPC", "Reach", "Freq", "VCR",
    "Leads", "CPL", "BrandLift", "AssistedConv",
]


# ── Auth helpers ──────────────────────────────────────────────────────────────

def get_sheets_service():
    creds_path = os.path.expanduser("~/.config/glofox-mcp-credentials.json")
    if os.path.exists(creds_path):
        creds = Credentials.from_service_account_file(creds_path, scopes=SHEETS_SCOPES)
    else:
        sa_key_b64 = os.environ.get("GLOFOX_SHEETS_SA_KEY")
        if not sa_key_b64:
            raise FileNotFoundError(
                f"Credentials not found at {creds_path} and GLOFOX_SHEETS_SA_KEY not set."
            )
        sa_key_data = json.loads(base64.b64decode(sa_key_b64).decode())
        creds = Credentials.from_service_account_info(sa_key_data, scopes=SHEETS_SCOPES)
    return build("sheets", "v4", credentials=creds)


def li_get(path: str, token: str, params: dict = None) -> dict:
    """GET request to LinkedIn API."""
    url = f"{LI_API_BASE}/{path.lstrip('/')}"
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Restli-Protocol-Version": "2.0.0",
    }
    resp = requests.get(url, headers=headers, params=params or {}, timeout=30)
    resp.raise_for_status()
    return resp.json()


# ── LinkedIn data fetch ────────────────────────────────────────────────────────

def fetch_linkedin_monthly(account_id: str, token: str, months: int) -> list[dict]:
    """
    Pull monthly LinkedIn Ads analytics at the account level.

    LinkedIn Analytics API endpoint: /adAnalytics
    Pivot: ACCOUNT
    Fields: dateRange, costInUsd, impressions, clicks, leadGenerationMailContactInfoShares,
            videoViews, approximateUniqueImpressions
    """
    today = date.today()
    results = []

    account_urn = f"urn:li:sponsoredAccount:{account_id}"

    for i in range(months - 1, -1, -1):
        total = today.year * 12 + (today.month - 1) - i
        year, month_idx = divmod(total, 12)
        month = month_idx + 1
        month_key = f"{year}-{month:02d}"
        _, last_day = monthrange(year, month)

        params = {
            "q": "analytics",
            "pivot": "ACCOUNT",
            "dateRange.start.year":  year,
            "dateRange.start.month": month,
            "dateRange.start.day":   1,
            "dateRange.end.year":    year,
            "dateRange.end.month":   month,
            "dateRange.end.day":     last_day,
            "accounts[0]":           account_urn,
            "fields": (
                "dateRange,costInUsd,impressions,clicks,"
                "leadGenerationMailContactInfoShares,"
                "videoViews,approximateUniqueImpressions,costInLocalCurrency"
            ),
            "timeGranularity": "ALL",
        }

        try:
            data = li_get("adAnalytics", token, params)
        except Exception as e:
            print(f"  WARNING: Could not fetch LinkedIn data for {month_key}: {e}")
            continue

        elements = data.get("elements", [])
        if not elements:
            continue

        # Sum across all elements (there may be one per account per month)
        spend       = sum(float(el.get("costInUsd", 0) or 0) for el in elements)
        impressions = sum(int(el.get("impressions", 0) or 0)  for el in elements)
        clicks      = sum(int(el.get("clicks", 0) or 0)       for el in elements)
        leads       = sum(
            int(el.get("leadGenerationMailContactInfoShares", 0) or 0)
            for el in elements
        )
        reach = sum(
            int(el.get("approximateUniqueImpressions", 0) or 0) for el in elements
        )

        cpm = round(spend / impressions * 1000, 2) if impressions > 0 else ""
        ctr = round(clicks / impressions, 4)        if impressions > 0 else ""
        cpc = round(spend / clicks, 2)              if clicks > 0 else ""
        cpl = round(spend / leads, 2)               if leads > 0 else ""

        results.append({
            "month":        month_key,
            "spend":        round(spend, 2),
            "impressions":  impressions,
            "cpm":          cpm,
            "clicks":       clicks,
            "ctr":          ctr,
            "cpc":          cpc,
            "reach":        reach if reach > 0 else "",
            "freq":         round(impressions / reach, 2) if reach > 0 else "",
            "vcr":          "",
            "leads":        leads,
            "cpl":          cpl,
            "brand_lift":   "",
            "assisted_conv": "",
        })

    return results


# ── Sheet write ────────────────────────────────────────────────────────────────

def upsert_channel_summary(service, new_rows: list[dict], source: str) -> None:
    """Upsert rows into ChannelSummary tab for the given source, preserving other sources."""
    meta = service.spreadsheets().get(spreadsheetId=SHEET_ID).execute()
    existing_tabs = [s["properties"]["title"] for s in meta.get("sheets", [])]
    if CHANNEL_SUMMARY_TAB not in existing_tabs:
        service.spreadsheets().batchUpdate(
            spreadsheetId=SHEET_ID,
            body={"requests": [{"addSheet": {"properties": {"title": CHANNEL_SUMMARY_TAB}}}]},
        ).execute()

    try:
        existing = service.spreadsheets().values().get(
            spreadsheetId=SHEET_ID,
            range=f"{CHANNEL_SUMMARY_TAB}!A:R",
        ).execute().get("values", [])
    except Exception:
        existing = []

    preserved = [
        row for row in existing[1:]
        if (row[3].strip().lower() if len(row) > 3 else "") != source.lower()
    ]

    def row_to_list(r: dict) -> list:
        return [
            r["month"], CHANNEL_LABEL, CHANNEL_TYPE, source,
            "",               # budget — filled manually
            r["spend"],
            r["impressions"],
            r.get("cpm", ""),
            r["clicks"],
            r.get("ctr", ""),
            r.get("cpc", ""),
            r.get("reach", ""),
            r.get("freq", ""),
            r.get("vcr", ""),
            r.get("leads", ""),
            r.get("cpl", ""),
            r.get("brand_lift", ""),
            r.get("assisted_conv", ""),
        ]

    new_lists = [row_to_list(r) for r in new_rows]
    all_rows = sorted(preserved + new_lists, key=lambda r: (r[0], r[1]))

    service.spreadsheets().values().clear(
        spreadsheetId=SHEET_ID, range=f"{CHANNEL_SUMMARY_TAB}!A:R"
    ).execute()
    service.spreadsheets().values().update(
        spreadsheetId=SHEET_ID,
        range=f"{CHANNEL_SUMMARY_TAB}!A1",
        valueInputOption="RAW",
        body={"values": [CHANNEL_SUMMARY_HEADERS] + all_rows},
    ).execute()
    print(f"  ChannelSummary: wrote {len(new_lists)} LinkedIn rows "
          f"({len(preserved)} other-source rows preserved).")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Sync LinkedIn Ads data to ChannelSummary tab"
    )
    parser.add_argument("--months", type=int, default=3,
                        help="Months of history to pull (default: 3)")
    args = parser.parse_args()

    token      = os.environ.get("LINKEDIN_ACCESS_TOKEN")
    account_id = os.environ.get("LINKEDIN_GF_ACCOUNT_ID")
    if not token or not account_id:
        raise EnvironmentError(
            "Missing required env vars: LINKEDIN_ACCESS_TOKEN, LINKEDIN_GF_ACCOUNT_ID\n"
            "Add to ~/.zshrc:  export LINKEDIN_ACCESS_TOKEN='AQX...'\n"
            "                  export LINKEDIN_GF_ACCOUNT_ID='XXXXXXXX'"
        )

    print(f"[1/3] Fetching last {args.months} months of LinkedIn Ads data...")
    rows = fetch_linkedin_monthly(account_id, token, args.months)
    print(f"  Retrieved {len(rows)} monthly rows.")

    if not rows:
        print("  No data returned — check account ID, token, and date range.")
        return

    print("[2/3] Connecting to Google Sheets...")
    service = get_sheets_service()

    print("[3/3] Writing to ChannelSummary tab...")
    upsert_channel_summary(service, rows, SOURCE_KEY)

    print("\nDone! LinkedIn Sponsored rows updated in ChannelSummary.")
    print("NOTE: MQL/SQL attribution comes from Salesforce/CampaignsData, not this script.")


if __name__ == "__main__":
    main()
