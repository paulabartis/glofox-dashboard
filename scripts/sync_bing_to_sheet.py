"""
Bing Ads (Microsoft Advertising) → Google Sheet Sync (Glofox account)

Pulls Microsoft Advertising Search campaign data monthly and writes to:
  1. ChannelSummary tab — "Bing" row per month (for CMO channel overview)
  2. BingData tab — same schema as GadsData (for existing campaign analysis)

Uses the Bing Ads Python SDK (bingads).

Setup:
    pip install bingads

    Add to ~/.zshrc:
       export BING_DEVELOPER_TOKEN="BBD..."
       export BING_CLIENT_ID="XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX"   # OAuth app client ID
       export BING_CLIENT_SECRET="XXXXXXX"                             # OAuth app secret
       export BING_REFRESH_TOKEN="1!AAAA..."                           # OAuth refresh token
       export BING_CUSTOMER_ID="XXXXXXXX"                              # top-level customer ID
       export BING_ACCOUNT_ID="XXXXXXXX"                               # Glofox ad account ID

    To get a refresh token, run:
       python scripts/sync_bing_to_sheet.py --auth

Usage:
    python scripts/sync_bing_to_sheet.py
    python scripts/sync_bing_to_sheet.py --months 3

Author: Claude Code
Created: 2026-03-27
"""

import argparse
import base64
import json
import os
import time
import webbrowser
from calendar import monthrange
from datetime import date, timedelta
from io import StringIO

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

# ── Constants ─────────────────────────────────────────────────────────────────

SHEET_ID = "1-M1R5RfWkQiQKvVnclI4d0KpSC1Ww042iCUv6IFe6mc"
CHANNEL_SUMMARY_TAB = "ChannelSummary"
BING_DATA_TAB = "BingData"
SHEETS_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
SOURCE_KEY = "bing"
CHANNEL_LABEL = "Bing"
CHANNEL_TYPE = "sql"

CHANNEL_SUMMARY_HEADERS = [
    "Month", "Channel", "ChannelType", "Source", "Budget", "Spend",
    "Impressions", "CPM", "Clicks", "CTR", "CPC", "Reach", "Freq", "VCR",
    "Leads", "CPL", "BrandLift", "AssistedConv",
]
BING_DATA_HEADERS = ["Campaign", "Year", "Month", "Impressions", "Clicks", "Cost"]


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


def get_bing_credentials() -> dict:
    """Load Bing Ads credentials from environment variables."""
    required = [
        "BING_DEVELOPER_TOKEN", "BING_CLIENT_ID", "BING_CLIENT_SECRET",
        "BING_REFRESH_TOKEN", "BING_CUSTOMER_ID", "BING_ACCOUNT_ID",
    ]
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        raise EnvironmentError(
            f"Missing env vars: {', '.join(missing)}\n"
            "Add to ~/.zshrc (see script header for setup instructions)."
        )
    return {k: os.environ[k] for k in required}


# ── Bing data fetch ────────────────────────────────────────────────────────────

def fetch_bing_monthly(creds: dict, months: int) -> tuple[list[dict], list[dict]]:
    """
    Pull monthly Bing Ads campaign performance data.

    Returns:
        (channel_rows, campaign_rows) where:
        - channel_rows: one dict per month (for ChannelSummary)
        - campaign_rows: one dict per (campaign, year, month) (for BingData)
    """
    try:
        from bingads import AuthorizationData, OAuthDesktopMobileAuthCodeGrant
        from bingads.v13.reporting import (
            ReportingServiceManager, ReportingDownloadParameters,
        )
        import bingads.v13.reporting.reporting_service_manager as rsm
    except ImportError:
        raise ImportError(
            "bingads SDK not installed. Run: pip install bingads"
        )

    # Build OAuth credentials
    oauth = OAuthDesktopMobileAuthCodeGrant(
        client_id=creds["BING_CLIENT_ID"],
        env="production",
    )
    oauth._oauth_tokens = type("T", (), {
        "access_token": None,
        "refresh_token": creds["BING_REFRESH_TOKEN"],
        "access_token_expires_in_seconds": 3600,
    })()
    oauth._client_secret = creds["BING_CLIENT_SECRET"]

    auth_data = AuthorizationData(
        account_id=int(creds["BING_ACCOUNT_ID"]),
        customer_id=int(creds["BING_CUSTOMER_ID"]),
        developer_token=creds["BING_DEVELOPER_TOKEN"],
        authentication=oauth,
    )

    # Build date range covering the requested months
    today = date.today()
    start_total = today.year * 12 + (today.month - 1) - (months - 1)
    s_year, s_month_idx = divmod(start_total, 12)
    s_month = s_month_idx + 1
    start_date = date(s_year, s_month, 1)
    end_date = today

    reporting_svc_mgr = ReportingServiceManager(
        authorization_data=auth_data,
        poll_interval_in_milliseconds=5000,
        environment="production",
    )

    from bingads.v13.reporting.reporting_service_manager import ReportingServiceManager as RSM
    reporting_svc = reporting_svc_mgr.service_client

    # Build report request
    report_request = reporting_svc.factory.create(
        "CampaignPerformanceReportRequest"
    )
    report_request.Aggregation = "Monthly"
    report_request.ExcludeColumnHeaders = False
    report_request.ExcludeReportFooter = True
    report_request.ExcludeReportHeader = True
    report_request.Format = "Csv"
    report_request.ReturnOnlyCompleteData = False

    # Scope
    scope = reporting_svc.factory.create("AccountThroughCampaignReportScope")
    account_ids = reporting_svc.factory.create("ns1:ArrayOflong")
    account_ids.long.append(int(creds["BING_ACCOUNT_ID"]))
    scope.AccountIds = account_ids
    report_request.Scope = scope

    # Date range
    time_period = reporting_svc.factory.create("ReportTime")
    time_period.CustomDateRangeStart = reporting_svc.factory.create("Date")
    time_period.CustomDateRangeStart.Day   = start_date.day
    time_period.CustomDateRangeStart.Month = start_date.month
    time_period.CustomDateRangeStart.Year  = start_date.year
    time_period.CustomDateRangeEnd = reporting_svc.factory.create("Date")
    time_period.CustomDateRangeEnd.Day   = end_date.day
    time_period.CustomDateRangeEnd.Month = end_date.month
    time_period.CustomDateRangeEnd.Year  = end_date.year
    time_period.ReportTimeZone = "GreenwichMeanTimeDublinEdinburghLisbonLondon"
    report_request.Time = time_period

    # Columns
    cols = reporting_svc.factory.create(
        "ArrayOfCampaignPerformanceReportColumn"
    )
    cols.CampaignPerformanceReportColumn = [
        "TimePeriod", "CampaignName", "Impressions", "Clicks", "Spend",
        "AverageCpc", "Ctr", "ImpressionSharePercent",
    ]
    report_request.Columns = cols

    # Submit and download
    params = ReportingDownloadParameters(
        report_request=report_request,
        result_file_directory="/tmp/",
        result_file_name="bing_report.csv",
        overwrite_result_file=True,
        timeout_in_milliseconds=300000,
    )

    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tf:
        params.result_file_directory = os.path.dirname(tf.name)
        params.result_file_name = os.path.basename(tf.name)

    reporting_svc_mgr.download_file(params)

    # Parse CSV
    import csv
    campaign_rows = []
    monthly_agg: dict[str, dict] = {}

    with open(os.path.join(params.result_file_directory, params.result_file_name)) as f:
        reader = csv.DictReader(f)
        for r in reader:
            # TimePeriod format: "2026-02-01"
            tp = r.get("TimePeriod", "").strip()
            if len(tp) >= 7:
                year  = int(tp[:4])
                month = int(tp[5:7])
            else:
                continue

            name        = r.get("CampaignName", "").strip()
            impressions = int(r.get("Impressions", "0").replace(",", "") or 0)
            clicks      = int(r.get("Clicks", "0").replace(",", "") or 0)
            spend       = float(r.get("Spend", "0").replace(",", "") or 0)

            campaign_rows.append({
                "campaign_name": name,
                "year": year, "month": month,
                "impressions": impressions, "clicks": clicks, "cost": round(spend, 2),
            })

            month_key = f"{year}-{month:02d}"
            if month_key not in monthly_agg:
                monthly_agg[month_key] = {"spend": 0.0, "impressions": 0, "clicks": 0}
            monthly_agg[month_key]["spend"]       += spend
            monthly_agg[month_key]["impressions"] += impressions
            monthly_agg[month_key]["clicks"]      += clicks

    channel_rows = []
    for month_key, v in sorted(monthly_agg.items()):
        sp  = round(v["spend"], 2)
        imp = v["impressions"]
        clk = v["clicks"]
        channel_rows.append({
            "month":       month_key,
            "spend":       sp,
            "impressions": imp,
            "cpm":         round(sp / imp * 1000, 2) if imp > 0 else "",
            "clicks":      clk,
            "ctr":         round(clk / imp, 4)       if imp > 0 else "",
            "cpc":         round(sp / clk, 2)        if clk > 0 else "",
        })

    return channel_rows, campaign_rows


# ── Sheet writes ───────────────────────────────────────────────────────────────

def ensure_tab(service, tab_name: str) -> None:
    meta = service.spreadsheets().get(spreadsheetId=SHEET_ID).execute()
    existing = [s["properties"]["title"] for s in meta.get("sheets", [])]
    if tab_name not in existing:
        service.spreadsheets().batchUpdate(
            spreadsheetId=SHEET_ID,
            body={"requests": [{"addSheet": {"properties": {"title": tab_name}}}]},
        ).execute()


def upsert_channel_summary(service, channel_rows: list[dict]) -> None:
    ensure_tab(service, CHANNEL_SUMMARY_TAB)

    try:
        existing = service.spreadsheets().values().get(
            spreadsheetId=SHEET_ID,
            range=f"{CHANNEL_SUMMARY_TAB}!A:R",
        ).execute().get("values", [])
    except Exception:
        existing = []

    preserved = [
        row for row in existing[1:]
        if (row[3].strip().lower() if len(row) > 3 else "") != SOURCE_KEY
    ]

    def to_list(r: dict) -> list:
        return [
            r["month"], CHANNEL_LABEL, CHANNEL_TYPE, SOURCE_KEY,
            "",               # budget — filled manually
            r["spend"], r["impressions"], r.get("cpm", ""),
            r["clicks"], r.get("ctr", ""), r.get("cpc", ""),
            "", "", "", "", "", "", "",   # reach, freq, vcr, leads, cpl, brand_lift, assisted_conv
        ]

    new_lists = [to_list(r) for r in channel_rows]
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
    print(f"  ChannelSummary: wrote {len(new_lists)} Bing channel rows "
          f"({len(preserved)} other-source rows preserved).")


def write_bing_data(service, campaign_rows: list[dict]) -> None:
    """Write campaign-level rows to BingData tab (same schema as GadsData)."""
    ensure_tab(service, BING_DATA_TAB)
    service.spreadsheets().values().clear(
        spreadsheetId=SHEET_ID, range=f"{BING_DATA_TAB}!A:F"
    ).execute()
    values = [BING_DATA_HEADERS] + [
        [r["campaign_name"], r["year"], r["month"],
         r["impressions"], r["clicks"], r["cost"]]
        for r in campaign_rows
    ]
    service.spreadsheets().values().update(
        spreadsheetId=SHEET_ID,
        range=f"{BING_DATA_TAB}!A1",
        valueInputOption="RAW",
        body={"values": values},
    ).execute()
    print(f"  BingData: wrote {len(campaign_rows)} campaign-month rows.")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Sync Microsoft Advertising (Bing) data to ChannelSummary + BingData tabs"
    )
    parser.add_argument("--months", type=int, default=3,
                        help="Months of history to pull (default: 3)")
    args = parser.parse_args()

    creds = get_bing_credentials()

    print(f"[1/3] Fetching last {args.months} months of Bing Ads data...")
    channel_rows, campaign_rows = fetch_bing_monthly(creds, args.months)
    print(f"  Retrieved {len(channel_rows)} monthly channel rows, {len(campaign_rows)} campaign rows.")

    if not channel_rows:
        print("  No data returned — check credentials and account ID.")
        return

    print("[2/3] Connecting to Google Sheets...")
    service = get_sheets_service()

    print("[3/3] Writing to Google Sheet...")
    upsert_channel_summary(service, channel_rows)
    write_bing_data(service, campaign_rows)

    print("\nDone! Bing rows updated in ChannelSummary and BingData.")
    print("NOTE: MQL/SQL attribution comes from Salesforce/CampaignsData, not this script.")


if __name__ == "__main__":
    main()
