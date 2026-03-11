"""
Dashboard Generator

Reads Google Ads data (GadsData tab), MQL/SQL data (CampaignsData tab), and
aggregate KPIs (MonthlySummary tab) from the Glofox Google Sheet, then
generates dashboard/index.html with all data embedded as JSON.

The HTML template (dashboard/template.html) handles all rendering via
vanilla JS + Chart.js. This script only prepares and injects the data.

Usage:
    python scripts/generate_dashboard.py
    python scripts/generate_dashboard.py --template dashboard/template.html --output dashboard/index.html

Author: Claude Code
Created: 2026-03-11
"""

import argparse
import base64
import json
import os
import re
from datetime import date
from pathlib import Path
from typing import Any

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

# ── Constants ────────────────────────────────────────────────────────────────

SHEET_ID = "1-M1R5RfWkQiQKvVnclI4d0KpSC1Ww042iCUv6IFe6mc"
SHEETS_SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

MONTH_ABBR = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


# ── Auth ──────────────────────────────────────────────────────────────────────

def get_sheets_service():
    creds_path = os.path.expanduser("~/.config/glofox-mcp-credentials.json")

    if os.path.exists(creds_path):
        creds = Credentials.from_service_account_file(creds_path, scopes=SHEETS_SCOPES)
    else:
        sa_key_b64 = os.environ.get("GLOFOX_SHEETS_SA_KEY")
        if not sa_key_b64:
            raise FileNotFoundError(
                f"Credentials not found at {creds_path} and GLOFOX_SHEETS_SA_KEY is not set."
            )
        sa_key_data = json.loads(base64.b64decode(sa_key_b64).decode())
        creds = Credentials.from_service_account_info(sa_key_data, scopes=SHEETS_SCOPES)

    return build("sheets", "v4", credentials=creds)


# ── Sheet reading ─────────────────────────────────────────────────────────────

def read_tab(service, tab: str, range_: str = "A:Z") -> list[list]:
    """Read a sheet tab and return all rows (each row is a list of cell values)."""
    result = service.spreadsheets().values().get(
        spreadsheetId=SHEET_ID,
        range=f"{tab}!{range_}",
    ).execute()
    return result.get("values", [])


# ── Type coercion ─────────────────────────────────────────────────────────────

def _clean(val: Any) -> str:
    return str(val).strip().replace(",", "").replace("$", "").replace("%", "")


def safe_float(val: Any, default: float = 0.0) -> float:
    try:
        cleaned = _clean(val)
        return float(cleaned) if cleaned and cleaned not in ("-", "") else default
    except (ValueError, TypeError):
        return default


def safe_int(val: Any) -> int:
    return int(safe_float(val))


# ── Campaign name parsing ─────────────────────────────────────────────────────

def parse_campaign_meta(name: str) -> dict:
    """
    Extract campaign_type, region, and channel from a Glofox campaign name.

    Naming convention: SEGMENT_Direction_Channel_PPC_Type_CampaignType_Region_MMDDYY
    Example: SMB_Inbound_Google_PPC_SEM_GymMgmt_WW_010125
    """
    parts = name.split("_")

    # Campaign type (check substrings in order of specificity)
    if "GymMgmt" in parts:
        campaign_type = "GymManagement"
    elif "Branded" in parts:
        campaign_type = "Branded"
    elif "Competitor" in parts:
        campaign_type = "Competitor"
    elif "Modality" in parts:
        campaign_type = "Modality"
    else:
        campaign_type = "Other"

    # Region — check each part against known region codes
    region = "Global"  # default (WW or unrecognised)
    for p in parts:
        pu = p.upper()
        if pu == "APAC":
            region = "APAC"
            break
        if pu == "UK":
            region = "EMEA"
            break
        if pu in ("USA", "NA", "CA"):
            region = "NAM"
            break
        # NA_Tier1 gets split so "NA" is already caught above
        if pu == "NAM":
            region = "NAM"
            break

    # Channel classification for Paid Search vs Paid Other widget
    if "SEM" in parts:
        channel = "Paid Search"
    elif any(p in parts for p in ("SM", "DG", "DIS")):
        channel = "Paid Other"
    else:
        channel = "Other"

    return {"campaign_type": campaign_type, "region": region, "channel": channel}


def is_paid_ppc(name: str, source: str = "") -> bool:
    """Return True if this row should be included in paid PPC analysis."""
    # Source filter: must be "Paid" or blank (GadsData has no Source column)
    if source and source.lower() not in ("paid", ""):
        return False
    # Must contain _PPC_ marker
    if "_PPC_" not in name:
        return False
    # Exclude non-SMB segments
    if name.startswith("TZ_") or name.startswith("MML_"):
        return False
    return True


# ── Month label parsing ───────────────────────────────────────────────────────

def parse_month_label(label: str) -> tuple[int, int] | None:
    """Parse 'Jan '25' or 'Feb 2024' → (year, month). Returns None if unparseable."""
    m = re.match(r"([A-Za-z]+)[,\s]+'?(\d{2,4})", label.strip())
    if not m:
        return None
    mon_name = m.group(1).lower()
    yr_str = m.group(2)
    month = MONTH_ABBR.get(mon_name)
    if not month:
        return None
    year = int(yr_str) if len(yr_str) == 4 else 2000 + int(yr_str)
    return (year, month)


def month_label(year: int, month: int) -> str:
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    return f"{months[month - 1]} '{str(year)[2:]}"


# ── Data loading (positional — column headers in these tabs are unreliable) ───

def load_gads_data(service) -> list[dict]:
    """
    GadsData tab (written by sync_gads_to_sheet.py).
    Columns: Campaign | Year | Month | Impressions | Clicks | Cost
    """
    rows = read_tab(service, "GadsData")
    result = []
    for row in rows[1:]:  # skip header
        if len(row) < 6:
            continue
        name = str(row[0]).strip()
        if not name:
            continue
        result.append({
            "name": name,
            "year": safe_int(row[1]),
            "month": safe_int(row[2]),
            "impressions": safe_int(row[3]),
            "clicks": safe_int(row[4]),
            "cost": safe_float(row[5]),
        })
    return result


def load_campaigns_data(service) -> list[dict]:
    """
    CampaignsData tab.
    Columns (positional): Source | Campaign | Year | Month | MQL | SQL
    """
    rows = read_tab(service, "CampaignsData")
    result = []
    for row in rows[1:]:  # skip header
        if len(row) < 6:
            continue
        source = str(row[0]).strip()
        name = str(row[1]).strip()
        year = safe_int(row[2])
        month = safe_int(row[3])
        mql = safe_int(row[4])
        sql = safe_int(row[5])

        if not name or year == 0 or month == 0:
            continue
        if not is_paid_ppc(name, source):
            continue

        result.append({
            "name": name,
            "year": year,
            "month": month,
            "mql": mql,
            "sql": sql,
        })
    return result


def load_monthly_summary(service) -> list[dict]:
    """
    MonthlySummary tab.
    Positional columns:
      0:  Period label (e.g. "Jan '24")
      1:  Spend
      2:  Sessions
      3:  Demo Reqs
      4:  Session to DR
      5:  Sess:MQL
      6:  MQL
      7:  NW MQL%
      8:  SQL
      9:  MQL to SQL
      10: Total Pipeline
      11: CW
      12: MQL to CW
      13: SQL to CW
      14: CW$
      15: CAC
      16: CP MQL
      17: CP SQL
      18: CW$/MQL
    """
    rows = read_tab(service, "MonthlySummary")
    result = []
    for row in rows[1:]:  # skip header
        if len(row) < 9:
            continue
        label = str(row[0]).strip()
        parsed = parse_month_label(label)
        if not parsed:
            continue
        year, month = parsed

        result.append({
            "year": year,
            "month": month,
            "label": label,
            "spend": safe_float(row[1] if len(row) > 1 else 0),
            "mql": safe_int(row[6] if len(row) > 6 else 0),
            "sql": safe_int(row[8] if len(row) > 8 else 0),
            "mql_sql_rate": safe_float(row[9] if len(row) > 9 else 0),
            "cw": safe_int(row[11] if len(row) > 11 else 0),
            "cp_mql": safe_float(row[16] if len(row) > 16 else 0),
            "cp_sql": safe_float(row[17] if len(row) > 17 else 0),
            "cac": safe_float(row[15] if len(row) > 15 else 0),
        })

    result.sort(key=lambda x: (x["year"], x["month"]))
    return result


# ── Data join ─────────────────────────────────────────────────────────────────

def build_campaign_rows(
    gads_data: list[dict],
    campaigns_data: list[dict],
) -> list[dict]:
    """
    Join GadsData + CampaignsData on (campaign_name, year, month).
    GadsData is the primary source (provides spend/clicks).
    CampaignsData-only rows are also included (MQL/SQL without cost).
    """
    # Index CampaignsData for fast lookup
    cd_index: dict[tuple, dict] = {}
    for row in campaigns_data:
        key = (row["name"], row["year"], row["month"])
        # If duplicate key, accumulate (shouldn't normally happen)
        if key in cd_index:
            cd_index[key]["mql"] += row["mql"]
            cd_index[key]["sql"] += row["sql"]
        else:
            cd_index[key] = {"mql": row["mql"], "sql": row["sql"]}

    merged: list[dict] = []
    seen: set[tuple] = set()

    # Primary: rows from GadsData
    for row in gads_data:
        if not is_paid_ppc(row["name"]):
            continue
        key = (row["name"], row["year"], row["month"])
        seen.add(key)
        cd = cd_index.get(key, {"mql": 0, "sql": 0})
        meta = parse_campaign_meta(row["name"])

        merged.append({
            "campaign_name": row["name"],
            "year": row["year"],
            "month": row["month"],
            "label": month_label(row["year"], row["month"]),
            "campaign_type": meta["campaign_type"],
            "region": meta["region"],
            "channel": meta["channel"],
            "impressions": row["impressions"],
            "clicks": row["clicks"],
            "cost": row["cost"],
            "mql": cd["mql"],
            "sql": cd["sql"],
        })

    # Secondary: CampaignsData rows with no matching Gads entry
    for row in campaigns_data:
        key = (row["name"], row["year"], row["month"])
        if key in seen:
            continue
        meta = parse_campaign_meta(row["name"])
        merged.append({
            "campaign_name": row["name"],
            "year": row["year"],
            "month": row["month"],
            "label": month_label(row["year"], row["month"]),
            "campaign_type": meta["campaign_type"],
            "region": meta["region"],
            "channel": meta["channel"],
            "impressions": 0,
            "clicks": 0,
            "cost": 0.0,
            "mql": row["mql"],
            "sql": row["sql"],
        })

    merged.sort(key=lambda x: (x["year"], x["month"], x["campaign_name"]))
    return merged


# ── HTML generation ───────────────────────────────────────────────────────────

def render_html(template_path: str, data: dict) -> str:
    """Inject the data JSON payload into the HTML template."""
    template = Path(template_path).read_text(encoding="utf-8")
    data_json = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    return template.replace("/* __DASHBOARD_DATA__ */", data_json)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Generate Glofox paid media dashboard HTML"
    )
    parser.add_argument(
        "--template", default="dashboard/template.html",
        help="Path to HTML template file",
    )
    parser.add_argument(
        "--output", default="dashboard/index.html",
        help="Path for generated HTML output",
    )
    args = parser.parse_args()

    print("[1/5] Connecting to Google Sheets...")
    service = get_sheets_service()

    print("[2/5] Reading sheet data...")
    gads_data = load_gads_data(service)
    campaigns_data = load_campaigns_data(service)
    monthly_summary = load_monthly_summary(service)
    print(f"  GadsData: {len(gads_data)} rows")
    print(f"  CampaignsData (paid PPC): {len(campaigns_data)} rows")
    print(f"  MonthlySummary: {len(monthly_summary)} periods")

    print("[3/5] Joining and processing data...")
    campaign_rows = build_campaign_rows(gads_data, campaigns_data)
    print(f"  Merged campaign rows: {len(campaign_rows)}")

    print("[4/5] Building dashboard payload...")
    dashboard_data = {
        "generated_at": date.today().isoformat(),
        "campaigns": campaign_rows,
        "monthly_kpis": monthly_summary,
    }

    print("[5/5] Rendering HTML...")
    html = render_html(args.template, dashboard_data)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")

    print(f"\nDashboard written to: {args.output}")
    print(f"Campaign rows included: {len(campaign_rows)}")
    print(f"Monthly KPI periods: {len(monthly_summary)}")


if __name__ == "__main__":
    main()
