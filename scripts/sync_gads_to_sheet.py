"""
Google Ads → Google Sheet Sync

Pulls Google Ads campaign performance data (impressions, clicks, cost) with
monthly segmentation and writes to the GadsData tab of the Glofox Looker
export sheet. Run this weekly before generating the dashboard.

Usage:
    python scripts/sync_gads_to_sheet.py
    python scripts/sync_gads_to_sheet.py --months 13

Required environment variables (Google Ads):
    GOOGLE_ADS_DEVELOPER_TOKEN
    GOOGLE_ADS_CLIENT_ID
    GOOGLE_ADS_CLIENT_SECRET
    GOOGLE_ADS_REFRESH_TOKEN
    GOOGLE_ADS_CUSTOMER_ID  (MCC account ID)

Required credentials (Google Sheets):
    ~/.config/glofox-mcp-credentials.json  (service account)
    OR env var GLOFOX_SHEETS_SA_KEY        (base64-encoded JSON, for GitHub Actions)

Author: Claude Code
Created: 2026-03-11
"""

import argparse
import base64
import json
import os
from datetime import date, timedelta

from google.ads.googleads.client import GoogleAdsClient
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

# ── Constants ────────────────────────────────────────────────────────────────

SHEET_ID = "1-M1R5RfWkQiQKvVnclI4d0KpSC1Ww042iCUv6IFe6mc"
GADS_TAB = "GadsData"
ADGROUP_TAB = "AdGroupData"
IS_TAB = "ImpShareWeekly"
GLOFOX_CUSTOMER_ID = "6129012053"
SHEETS_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


# ── Auth helpers ─────────────────────────────────────────────────────────────

def get_gads_client() -> GoogleAdsClient:
    """Initialize Google Ads API client from environment variables."""
    return GoogleAdsClient.load_from_dict({
        "developer_token": os.environ["GOOGLE_ADS_DEVELOPER_TOKEN"],
        "client_id": os.environ["GOOGLE_ADS_CLIENT_ID"],
        "client_secret": os.environ["GOOGLE_ADS_CLIENT_SECRET"],
        "refresh_token": os.environ["GOOGLE_ADS_REFRESH_TOKEN"],
        "login_customer_id": os.environ["GOOGLE_ADS_CUSTOMER_ID"],
        "use_proto_plus": True,
    })


def get_sheets_service():
    """Initialize Google Sheets API service using service account credentials."""
    creds_path = os.path.expanduser("~/.config/glofox-mcp-credentials.json")

    if os.path.exists(creds_path):
        creds = Credentials.from_service_account_file(creds_path, scopes=SHEETS_SCOPES)
    else:
        # GitHub Actions path: credentials in environment variable (base64-encoded JSON)
        sa_key_b64 = os.environ.get("GLOFOX_SHEETS_SA_KEY")
        if not sa_key_b64:
            raise FileNotFoundError(
                f"Service account credentials not found at {creds_path} "
                "and GLOFOX_SHEETS_SA_KEY env var is not set."
            )
        sa_key_data = json.loads(base64.b64decode(sa_key_b64).decode())
        creds = Credentials.from_service_account_info(sa_key_data, scopes=SHEETS_SCOPES)

    return build("sheets", "v4", credentials=creds)


# ── Utility ──────────────────────────────────────────────────────────────────

def micros_to_currency(micros: int) -> float:
    return micros / 1_000_000


def months_ago_start(n: int) -> date:
    """Return the first day of the month n months before the current month."""
    today = date.today()
    total = today.year * 12 + (today.month - 1) - (n - 1)
    year, month = divmod(total, 12)
    month += 1  # divmod gives 0-based month
    return date(year, month, 1)


# ── Google Ads data fetch ─────────────────────────────────────────────────────

def fetch_gads_monthly(client: GoogleAdsClient, months: int) -> list[dict]:
    """
    Fetch Google Ads campaign data segmented by calendar month.

    Args:
        client: GoogleAdsClient instance
        months: How many months of history to pull (e.g. 13)

    Returns:
        List of dicts: campaign_name, year, month, impressions, clicks, cost
    """
    start = months_ago_start(months)
    end = date.today()

    ga_service = client.get_service("GoogleAdsService")

    query = f"""
        SELECT
            campaign.name,
            segments.year,
            segments.month,
            metrics.impressions,
            metrics.clicks,
            metrics.cost_micros
        FROM campaign
        WHERE segments.date BETWEEN '{start.isoformat()}' AND '{end.isoformat()}'
            AND campaign.status != 'REMOVED'
        ORDER BY campaign.name, segments.year, segments.month
    """

    response = ga_service.search(customer_id=GLOFOX_CUSTOMER_ID, query=query)

    rows = []
    for row in response:
        rows.append({
            "campaign_name": row.campaign.name,
            "year": row.segments.year,
            "month": row.segments.month,
            "impressions": row.metrics.impressions,
            "clicks": row.metrics.clicks,
            "cost": round(micros_to_currency(row.metrics.cost_micros), 2),
        })

    return rows


def fetch_adgroup_monthly(client: GoogleAdsClient, months: int) -> list[dict]:
    """
    Fetch Google Ads ad group performance segmented by calendar month.

    Returns:
        List of dicts: campaign_name, adgroup_name, year, month, impressions, clicks, cost
    """
    start = months_ago_start(months)
    end = date.today()

    ga_service = client.get_service("GoogleAdsService")

    query = f"""
        SELECT
            campaign.name,
            ad_group.name,
            segments.year,
            segments.month,
            metrics.impressions,
            metrics.clicks,
            metrics.cost_micros
        FROM ad_group
        WHERE segments.date BETWEEN '{start.isoformat()}' AND '{end.isoformat()}'
            AND campaign.status != 'REMOVED'
            AND ad_group.status != 'REMOVED'
        ORDER BY campaign.name, ad_group.name, segments.year, segments.month
    """

    response = ga_service.search(customer_id=GLOFOX_CUSTOMER_ID, query=query)

    rows = []
    for row in response:
        rows.append({
            "campaign_name": row.campaign.name,
            "adgroup_name": row.ad_group.name,
            "year": row.segments.year,
            "month": row.segments.month,
            "impressions": row.metrics.impressions,
            "clicks": row.metrics.clicks,
            "cost": round(micros_to_currency(row.metrics.cost_micros), 2),
        })

    return rows


def fetch_impression_share_weekly(client: GoogleAdsClient, weeks: int = 16) -> list[dict]:
    """
    Fetch Search Impression Share and Lost IS (Rank) for enabled Paid Search campaigns,
    aggregated by ISO week using impression-weighted averaging.

    Returns:
        List of dicts: week (YYYY-MM-DD Monday), impressions, search_is, lost_is_rank
    """
    # Start from the Monday of the week `weeks` ago
    today = date.today()
    start = today - timedelta(weeks=weeks)
    start = start - timedelta(days=start.weekday())  # snap back to Monday
    end = today

    ga_service = client.get_service("GoogleAdsService")

    query = f"""
        SELECT
            segments.date,
            metrics.impressions,
            metrics.search_impression_share,
            metrics.search_rank_lost_impression_share
        FROM campaign
        WHERE segments.date BETWEEN '{start.isoformat()}' AND '{end.isoformat()}'
            AND campaign.status = 'ENABLED'
            AND campaign.advertising_channel_type = 'SEARCH'
        ORDER BY segments.date
    """

    response = ga_service.search(customer_id=GLOFOX_CUSTOMER_ID, query=query)

    # Impression-weighted aggregation per ISO week (Monday as key)
    weekly: dict[date, dict] = {}
    for row in response:
        d = date.fromisoformat(row.segments.date)
        week_start = d - timedelta(days=d.weekday())  # Monday
        imp = row.metrics.impressions
        try:
            is_pct = float(row.metrics.search_impression_share)
            is_pct = is_pct if 0.0 <= is_pct <= 1.0 else 0.0
        except (TypeError, ValueError):
            is_pct = 0.0
        try:
            rank_lost = float(row.metrics.search_rank_lost_impression_share)
            rank_lost = rank_lost if 0.0 <= rank_lost <= 1.0 else 0.0
        except (TypeError, ValueError):
            rank_lost = 0.0

        if week_start not in weekly:
            weekly[week_start] = {"impressions": 0, "is_w": 0.0, "rank_w": 0.0}
        weekly[week_start]["impressions"] += imp
        weekly[week_start]["is_w"] += is_pct * imp
        weekly[week_start]["rank_w"] += rank_lost * imp

    rows = []
    for ws in sorted(weekly.keys()):
        w = weekly[ws]
        imp = w["impressions"]
        search_is  = round(w["is_w"]   / imp, 4) if imp > 0 else None
        lost_is    = round(w["rank_w"] / imp, 4) if imp > 0 else None
        rows.append({
            "week":        ws.isoformat(),
            "impressions": imp,
            "search_is":   search_is,
            "lost_is_rank": lost_is,
        })

    return rows


# ── Google Sheet write ────────────────────────────────────────────────────────

def ensure_tab_exists(service, tab_name: str) -> None:
    """Create the tab if it doesn't already exist."""
    meta = service.spreadsheets().get(spreadsheetId=SHEET_ID).execute()
    existing = [s["properties"]["title"] for s in meta.get("sheets", [])]
    if tab_name not in existing:
        service.spreadsheets().batchUpdate(
            spreadsheetId=SHEET_ID,
            body={"requests": [{"addSheet": {"properties": {"title": tab_name}}}]},
        ).execute()
        print(f"  Created new tab: {tab_name}")


def write_to_sheet(service, rows: list[dict]) -> None:
    """Clear GadsData tab and write fresh data with headers."""
    sheets = service.spreadsheets()

    ensure_tab_exists(service, GADS_TAB)

    # Clear existing content
    sheets.values().clear(
        spreadsheetId=SHEET_ID,
        range=f"{GADS_TAB}!A:F",
    ).execute()

    # Build values: header row + data rows
    headers = ["Campaign", "Year", "Month", "Impressions", "Clicks", "Cost"]
    values = [headers] + [
        [
            r["campaign_name"],
            r["year"],
            r["month"],
            r["impressions"],
            r["clicks"],
            r["cost"],
        ]
        for r in rows
    ]

    sheets.values().update(
        spreadsheetId=SHEET_ID,
        range=f"{GADS_TAB}!A1",
        valueInputOption="RAW",
        body={"values": values},
    ).execute()

    print(f"  Written {len(rows)} data rows to '{GADS_TAB}' tab.")


def write_adgroup_to_sheet(service, rows: list[dict]) -> None:
    """Clear AdGroupData tab and write fresh ad group data with headers."""
    sheets = service.spreadsheets()

    ensure_tab_exists(service, ADGROUP_TAB)

    sheets.values().clear(
        spreadsheetId=SHEET_ID,
        range=f"{ADGROUP_TAB}!A:G",
    ).execute()

    headers = ["Campaign", "Ad Group", "Year", "Month", "Impressions", "Clicks", "Cost"]
    values = [headers] + [
        [
            r["campaign_name"],
            r["adgroup_name"],
            r["year"],
            r["month"],
            r["impressions"],
            r["clicks"],
            r["cost"],
        ]
        for r in rows
    ]

    sheets.values().update(
        spreadsheetId=SHEET_ID,
        range=f"{ADGROUP_TAB}!A1",
        valueInputOption="RAW",
        body={"values": values},
    ).execute()

    print(f"  Written {len(rows)} data rows to '{ADGROUP_TAB}' tab.")


def fetch_change_events(client: GoogleAdsClient, days: int = 14) -> list[dict]:
    """
    Fetch account change events from the last 14 days.
    Covers: campaign status/budget edits, ad group changes, keyword changes, ad approvals.
    Filters out pure automated bid-strategy changes (no user email).

    Returns:
        List of dicts: change_datetime, user_email, resource_type, operation,
                       changed_fields, campaign_name
    """
    ga_service = client.get_service("GoogleAdsService")

    query = """
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
        LIMIT 300
    """

    try:
        response = ga_service.search(customer_id=GLOFOX_CUSTOMER_ID, query=query)
    except Exception as e:
        print(f"  WARNING: Could not fetch change events: {e}")
        return []

    rows = []
    for row in response:
        ce = row.change_event

        # Extract changed fields from FieldMask
        try:
            fields = ", ".join(ce.changed_fields.paths) if ce.changed_fields.paths else ""
        except Exception:
            fields = ""

        # Resource type and operation as readable strings
        try:
            resource_type = ce.change_resource_type.name
        except Exception:
            resource_type = "UNKNOWN"
        try:
            operation = ce.resource_change_operation.name
        except Exception:
            operation = "UNKNOWN"

        user = str(ce.user_email).strip() if ce.user_email else ""

        # Skip pure automated bid-strategy noise (no user, bidding strategy update)
        if not user and resource_type in ("BIDDING_STRATEGY", "AD_GROUP_BID_MODIFIER"):
            continue

        rows.append({
            "change_datetime":  str(ce.change_date_time),
            "user_email":       user or "Automated",
            "resource_type":    resource_type,
            "operation":        operation,
            "changed_fields":   fields,
            "campaign_name":    str(row.campaign.name) if row.campaign.name else "",
        })

    return rows


def write_is_to_sheet(service, rows: list[dict]) -> None:
    """Clear ImpShareWeekly tab and write fresh weekly IS data with headers."""
    sheets = service.spreadsheets()

    ensure_tab_exists(service, IS_TAB)

    sheets.values().clear(
        spreadsheetId=SHEET_ID,
        range=f"{IS_TAB}!A:D",
    ).execute()

    headers = ["Week", "Impressions", "SearchIS", "LostIS_Rank"]
    values = [headers] + [
        [
            r["week"],
            r["impressions"],
            r["search_is"] if r["search_is"] is not None else "",
            r["lost_is_rank"] if r["lost_is_rank"] is not None else "",
        ]
        for r in rows
    ]

    sheets.values().update(
        spreadsheetId=SHEET_ID,
        range=f"{IS_TAB}!A1",
        valueInputOption="RAW",
        body={"values": values},
    ).execute()

    print(f"  Written {len(rows)} weekly rows to '{IS_TAB}' tab.")


def write_change_events_to_sheet(service, rows: list[dict]) -> None:
    """Clear ChangeEvents tab and write fresh change event data with headers."""
    tab = "ChangeEvents"
    sheets = service.spreadsheets()

    ensure_tab_exists(service, tab)

    sheets.values().clear(
        spreadsheetId=SHEET_ID,
        range=f"{tab}!A:F",
    ).execute()

    headers = ["DateTime", "User", "ResourceType", "Operation", "Campaign", "ChangedFields"]
    values = [headers] + [
        [
            r["change_datetime"],
            r["user_email"],
            r["resource_type"],
            r["operation"],
            r["campaign_name"],
            r["changed_fields"],
        ]
        for r in rows
    ]

    sheets.values().update(
        spreadsheetId=SHEET_ID,
        range=f"{tab}!A1",
        valueInputOption="RAW",
        body={"values": values},
    ).execute()

    print(f"  Written {len(rows)} change events to '{tab}' tab.")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Sync Google Ads campaign data to GadsData tab in Glofox Google Sheet"
    )
    parser.add_argument(
        "--months", type=int, default=13,
        help="Months of history to pull (default: 13)"
    )
    args = parser.parse_args()

    print(f"[1/5] Connecting to Google Ads API...")
    try:
        gads_client = get_gads_client()
    except KeyError as e:
        print(f"\nERROR: Missing environment variable: {e}")
        print("Required: GOOGLE_ADS_DEVELOPER_TOKEN, GOOGLE_ADS_CLIENT_ID, "
              "GOOGLE_ADS_CLIENT_SECRET, GOOGLE_ADS_REFRESH_TOKEN, GOOGLE_ADS_CUSTOMER_ID")
        raise

    print(f"[2/5] Fetching last {args.months} months of campaign data from Google Ads...")
    rows = fetch_gads_monthly(gads_client, args.months)
    print(f"  Retrieved {len(rows)} campaign-month rows.")

    print(f"[3/5] Fetching last {args.months} months of ad group data from Google Ads...")
    ag_rows = fetch_adgroup_monthly(gads_client, args.months)
    print(f"  Retrieved {len(ag_rows)} ad group-month rows.")

    print(f"[4/6] Fetching last 16 weeks of Impression Share data from Google Ads...")
    is_rows = fetch_impression_share_weekly(gads_client, weeks=16)
    print(f"  Retrieved {len(is_rows)} weekly IS rows.")

    print(f"[5/6] Fetching last 14 days of account change events from Google Ads...")
    change_rows = fetch_change_events(gads_client, days=14)
    print(f"  Retrieved {len(change_rows)} change events.")

    print(f"[6/6] Writing to Google Sheet...")
    sheets_service = get_sheets_service()
    write_to_sheet(sheets_service, rows)
    write_adgroup_to_sheet(sheets_service, ag_rows)
    write_is_to_sheet(sheets_service, is_rows)
    write_change_events_to_sheet(sheets_service, change_rows)

    print("\nDone! GadsData, AdGroupData, ImpShareWeekly, and ChangeEvents tabs are up to date.")


if __name__ == "__main__":
    main()
