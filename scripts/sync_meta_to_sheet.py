"""
Meta Ads → Google Sheet Sync (Glofox account)

Pulls Meta Ads awareness campaign data monthly and writes to the ChannelSummary tab.
Uses Meta Marketing API v21.

Setup:
    1. Add to ~/.zshrc:
       export META_GF_ACCOUNT_ID="act_XXXXXXXXX"   # Glofox Meta ad account
       export META_GF_ACCESS_TOKEN="EAA..."         # System user token with Glofox access

    2. Run: python scripts/sync_meta_to_sheet.py
            python scripts/sync_meta_to_sheet.py --months 3

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
META_API_BASE = "https://graph.facebook.com/v21.0"
SOURCE_KEY = "meta"
CHANNEL_LABEL = "Meta awareness"
CHANNEL_TYPE = "awareness"

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


def meta_get(path: str, token: str, params: dict = None) -> dict:
    """GET request to Meta Graph API with error handling."""
    url = f"{META_API_BASE}/{path.lstrip('/')}"
    p = {"access_token": token}
    if params:
        p.update(params)
    resp = requests.get(url, params=p, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise RuntimeError(f"Meta API error: {data['error'].get('message', data['error'])}")
    return data


# ── Meta data fetch ────────────────────────────────────────────────────────────

def fetch_meta_monthly(account_id: str, token: str, months: int) -> list[dict]:
    """
    Pull monthly Meta Ads insights for the account.

    Returns one dict per month with spend, impressions, reach, frequency,
    CPM, clicks, CTR, CPC, leads (actions type=lead), video completion rate,
    and 30-day view-through assisted conversions.
    """
    today = date.today()
    results = []

    for i in range(months - 1, -1, -1):
        # Compute year/month for i months ago
        total = today.year * 12 + (today.month - 1) - i
        year, month_idx = divmod(total, 12)
        month = month_idx + 1
        month_key = f"{year}-{month:02d}"
        _, last_day = monthrange(year, month)
        since = f"{year}-{month:02d}-01"
        until = f"{year}-{month:02d}-{last_day:02d}"

        params = {
            "fields": (
                "spend,impressions,reach,frequency,cpm,clicks,ctr,cpc,"
                "actions,video_avg_percent_watched_actions,video_p100_watched_actions"
            ),
            "time_range": json.dumps({"since": since, "until": until}),
            "level": "account",
        }

        try:
            data = meta_get(f"{account_id}/insights", token, params)
        except Exception as e:
            print(f"  WARNING: Could not fetch Meta data for {month_key}: {e}")
            continue

        insight_rows = data.get("data", [])
        if not insight_rows:
            continue

        row = insight_rows[0]  # account-level gives one row

        # Extract lead actions (Lead Gen Form submissions + website leads)
        actions = row.get("actions", [])
        leads = sum(
            float(a.get("value", 0))
            for a in actions
            if a.get("action_type", "") in ("lead", "onsite_conversion.lead_grouped")
        )

        # Assisted conversions (30-day view-through: offsite_conversion.fb_pixel_purchase etc.)
        # Use "onsite_conversion.total_messaging_connection" or view-through conversions
        assisted = sum(
            float(a.get("value", 0))
            for a in actions
            if "view_through" in a.get("action_type", "")
            or a.get("action_type", "") in ("offsite_conversion.fb_pixel_lead",)
        )

        # Video completion rate (% of video views that watched to 100%)
        vcr = None
        vca_list = row.get("video_p100_watched_actions", [])
        if vca_list:
            vca = float(vca_list[0].get("value", 0))
            imp = float(row.get("impressions", 0) or 0)
            vcr = round(vca / imp, 4) if imp > 0 else None

        spend = float(row.get("spend", 0) or 0)
        impr  = int(row.get("impressions", 0) or 0)
        reach = int(row.get("reach", 0) or 0)
        freq  = round(float(row.get("frequency", 0) or 0), 2)
        cpm   = round(float(row.get("cpm", 0) or 0), 2)
        clk   = int(row.get("clicks", 0) or 0)
        ctr   = round(float(row.get("ctr", 0) or 0) / 100, 4)  # Meta returns as %
        cpc   = round(float(row.get("cpc", 0) or 0), 2)
        leads = round(leads)
        cpl   = round(spend / leads, 2) if leads > 0 else ""

        results.append({
            "month":        month_key,
            "spend":        round(spend, 2),
            "impressions":  impr,
            "cpm":          cpm,
            "clicks":       clk,
            "ctr":          ctr,
            "cpc":          cpc,
            "reach":        reach,
            "freq":         freq,
            "vcr":          vcr if vcr is not None else "",
            "leads":        leads,
            "cpl":          cpl,
            "brand_lift":   "",   # populated manually from Meta Brand Lift study
            "assisted_conv": round(assisted) if assisted > 0 else "",
        })

    return results


# ── Sheet write ────────────────────────────────────────────────────────────────

def upsert_channel_summary(service, new_rows: list[dict], source: str) -> None:
    """
    Upsert rows into ChannelSummary tab for the given source.
    Preserves rows from all other sources.
    """
    # Ensure tab exists
    meta = service.spreadsheets().get(spreadsheetId=SHEET_ID).execute()
    existing_tabs = [s["properties"]["title"] for s in meta.get("sheets", [])]
    if CHANNEL_SUMMARY_TAB not in existing_tabs:
        service.spreadsheets().batchUpdate(
            spreadsheetId=SHEET_ID,
            body={"requests": [{"addSheet": {"properties": {"title": CHANNEL_SUMMARY_TAB}}}]},
        ).execute()
        print(f"  Created tab: {CHANNEL_SUMMARY_TAB}")

    # Read existing
    try:
        existing = service.spreadsheets().values().get(
            spreadsheetId=SHEET_ID,
            range=f"{CHANNEL_SUMMARY_TAB}!A:R",
        ).execute().get("values", [])
    except Exception:
        existing = []

    preserved = []
    for row in existing[1:]:  # skip header
        row_source = row[3].strip().lower() if len(row) > 3 else ""
        if row_source != source.lower():
            preserved.append(row)

    def row_to_list(r: dict) -> list:
        return [
            r["month"], CHANNEL_LABEL, CHANNEL_TYPE, source,
            "",                  # budget — filled manually
            r["spend"],
            r["impressions"],
            r["cpm"],
            r["clicks"],
            r["ctr"],
            r["cpc"],
            r.get("reach", ""),
            r.get("freq", ""),
            r.get("vcr", ""),
            r.get("leads", ""),
            r.get("cpl", ""),
            r.get("brand_lift", ""),
            r.get("assisted_conv", ""),
        ]

    new_lists = [row_to_list(r) for r in new_rows]
    all_rows = preserved + new_lists
    all_rows.sort(key=lambda r: (r[0], r[1]))

    service.spreadsheets().values().clear(
        spreadsheetId=SHEET_ID,
        range=f"{CHANNEL_SUMMARY_TAB}!A:R",
    ).execute()
    service.spreadsheets().values().update(
        spreadsheetId=SHEET_ID,
        range=f"{CHANNEL_SUMMARY_TAB}!A1",
        valueInputOption="RAW",
        body={"values": [CHANNEL_SUMMARY_HEADERS] + all_rows},
    ).execute()
    print(f"  ChannelSummary: wrote {len(new_lists)} Meta rows "
          f"({len(preserved)} other-source rows preserved).")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Sync Meta Ads (Glofox) awareness data to ChannelSummary tab"
    )
    parser.add_argument("--months", type=int, default=3,
                        help="Months of history to pull (default: 3)")
    args = parser.parse_args()

    account_id = os.environ.get("META_GF_ACCOUNT_ID")
    token      = os.environ.get("META_GF_ACCESS_TOKEN")
    if not account_id or not token:
        raise EnvironmentError(
            "Missing required env vars: META_GF_ACCOUNT_ID and META_GF_ACCESS_TOKEN\n"
            "Add to ~/.zshrc:  export META_GF_ACCOUNT_ID='act_XXXXXXXX'\n"
            "                  export META_GF_ACCESS_TOKEN='EAA...'"
        )

    print(f"[1/3] Fetching last {args.months} months of Meta Ads data...")
    rows = fetch_meta_monthly(account_id, token, args.months)
    print(f"  Retrieved {len(rows)} monthly rows.")

    if not rows:
        print("  No data returned — check account ID, token, and date range.")
        return

    print("[2/3] Connecting to Google Sheets...")
    service = get_sheets_service()

    print("[3/3] Writing to ChannelSummary tab...")
    upsert_channel_summary(service, rows, SOURCE_KEY)

    print("\nDone! Meta awareness rows updated in ChannelSummary.")
    print("NOTE: BrandLift column must be filled manually from Meta Brand Lift study results.")


if __name__ == "__main__":
    main()
