"""
Salesforce → Google Sheet Sync (CampaignsData + MonthlySummary)

Replaces the Looker weekly export for the Glofox Paid Media Dashboard. Looker
used to write MQL/SQL-by-campaign rows into CampaignsData and monthly
aggregate KPIs into MonthlySummary — Looker access is gone, so this script
pulls the same shape of data directly from Salesforce.

Scope: SF-derived columns only (MQL, SQL, CW, CW$, MQL→SQL, MQL→CW, SQL→CW,
Total Pipeline). Sessions/Demo Reqs (GA4-sourced) are left untouched — out of
scope for this script. Only campaigns/months >= --since are touched; earlier
rows (written by Looker) are preserved exactly as-is.

CampaignsData shape: written as a UNION of independently-grouped MQL rows
(MQL>0, SQL=0, grouped by MQL date's campaign+month) and SQL rows (MQL=0,
SQL>0, grouped by Opportunity CreatedDate's campaign+month) — matching the
shape Looker already used, so generate_dashboard.py needs zero changes.

Auth: same interactive Salesforce CLI pattern as fetch_sf_leads.py.
    sf org login web --alias glofox-prod      # once per session if token expired

Usage:
    python3 scripts/sync_sf_to_sheet.py                  # since 2026-01, writes to sheet
    python3 scripts/sync_sf_to_sheet.py --dry-run         # compute + print, skip writing
    python3 scripts/sync_sf_to_sheet.py --since 2026-04   # narrower backfill window

Author: Claude Code
Created: 2026-07-10
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
from datetime import date, datetime

import requests
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

# ── Constants ────────────────────────────────────────────────────────────────

SHEET_ID = "1-M1R5RfWkQiQKvVnclI4d0KpSC1Ww042iCUv6IFe6mc"
CAMPAIGNS_TAB = "CampaignsData"
MONTHLY_TAB = "MonthlySummary"
GADS_TAB = "GadsData"
SHEETS_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

DEFAULT_ALIAS = "glofox-prod"
API_VERSION = "v59.0"

MONTH_ABBR = {
    1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
    7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec",
}
MONTH_NAME_TO_NUM = {v.lower(): k for k, v in MONTH_ABBR.items()}


# ── Auth via SF CLI (same pattern as fetch_sf_leads.py) ───────────────────────

def get_sf_token(alias: str) -> tuple[str, str]:
    try:
        result = subprocess.run(
            ["sf", "org", "display", "--target-org", alias, "--json"],
            capture_output=True, text=True, check=True
        )
    except subprocess.CalledProcessError as e:
        print(f"ERROR: SF CLI error: {e.stderr}")
        print(f"\nHave you logged in? Run:\n  sf org login web --alias {alias}")
        sys.exit(1)
    except FileNotFoundError:
        print("ERROR: SF CLI not found. Install it with:\n  npm install -g @salesforce/cli")
        sys.exit(1)

    data = json.loads(result.stdout)
    if data.get("status") != 0:
        print(f"ERROR: SF CLI returned error: {data.get('message', 'unknown error')}")
        print(f"\nTry re-authenticating:\n  sf org login web --alias {alias}")
        sys.exit(1)

    result_data = data.get("result", {})
    access_token = result_data.get("accessToken")
    instance_url = result_data.get("instanceUrl")
    if not access_token or not instance_url:
        print("ERROR: Could not extract token from SF CLI output.")
        sys.exit(1)

    return access_token, instance_url


# ── SOQL query with pagination ────────────────────────────────────────────────

def soql_query(instance_url: str, access_token: str, query: str) -> list[dict]:
    """Run a SOQL query via the REST Query API, following nextRecordsUrl."""
    headers = {"Authorization": f"Bearer {access_token}"}
    url = f"{instance_url}/services/data/{API_VERSION}/query"
    params = {"q": query}
    records = []

    while True:
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        if resp.status_code == 401:
            print("ERROR: Token expired. Re-authenticate:")
            print(f"  sf org login web --alias {DEFAULT_ALIAS}")
            sys.exit(1)
        if not resp.ok:
            print(f"ERROR: SOQL query failed ({resp.status_code}): {resp.text[:500]}")
            sys.exit(1)

        data = resp.json()
        records.extend(data.get("records", []))

        if data.get("done", True):
            break
        # nextRecordsUrl is a full path (e.g. /services/data/v59.0/query/01g...-2000)
        url = f"{instance_url}{data['nextRecordsUrl']}"
        params = None

    return records


# ── Campaign filtering (mirrors generate_dashboard.py::is_paid_ppc) ──────────

def is_paid_ppc(name: str) -> bool:
    if not name:
        return False
    if "_PPC_" not in name:
        return False
    if name.startswith("TZ_") or name.startswith("MML_"):
        return False
    return True


# ── Date parsing ───────────────────────────────────────────────────────────────

def year_month_from_sf_date(sf_date: str) -> tuple[int, int] | None:
    """Parse a Salesforce date/datetime string ('2026-07-10' or
    '2026-07-10T14:11:54.000+0000') into (year, month)."""
    if not sf_date:
        return None
    try:
        return int(sf_date[0:4]), int(sf_date[5:7])
    except (ValueError, IndexError):
        return None


def month_label(year: int, month: int) -> str:
    return f"{MONTH_ABBR[month]} '{str(year)[2:]}"


def parse_since(since_str: str) -> tuple[int, int]:
    """Parse '2026-01' → (2026, 1)."""
    year_s, month_s = since_str.split("-")
    return int(year_s), int(month_s)


def months_from(since_ym: tuple[int, int]) -> list[tuple[int, int]]:
    """All (year, month) tuples from since_ym through the current month, inclusive."""
    today = date.today()
    result = []
    y, m = since_ym
    while (y, m) <= (today.year, today.month):
        result.append((y, m))
        m += 1
        if m > 12:
            m = 1
            y += 1
    return result


# ── Salesforce data pulls ─────────────────────────────────────────────────────

def fetch_mql_records(instance_url: str, token: str, since_iso: str) -> list[dict]:
    """
    Pull MQL'd Leads + Contacts with campaign attribution, dedup by email
    (a Lead that converts becomes a Contact — same dedup logic as
    fetch_sf_leads.py::merge_reports, applied here at the SOQL layer).
    """
    fields = "Email, Campaign_Most_Recent__r.Name, MQL_Date_Most_Recent__c"
    base_where = (
        f"Campaign_Most_Recent__c != null "
        f"AND MQL_Date_Most_Recent__c >= {since_iso} AND Email != null"
    )
    # Contact pool matches Power BI's [MQLs] measure definition exactly: only
    # Contacts that originated as a converted Lead count — otherwise a Contact
    # created directly (not via lead conversion) would be double-counted
    # against Power BI's methodology.
    contact_where = base_where + " AND Converted_Lead_ID_18_Digit__c != null"

    leads = soql_query(instance_url, token, f"SELECT {fields} FROM Lead WHERE {base_where}")
    contacts = soql_query(instance_url, token, f"SELECT {fields} FROM Contact WHERE {contact_where}")

    by_email: dict[str, dict] = {}
    for rec in leads + contacts:
        email = (rec.get("Email") or "").strip().lower()
        campaign_rel = rec.get("Campaign_Most_Recent__r") or {}
        campaign_name = campaign_rel.get("Name")
        mql_date = rec.get("MQL_Date_Most_Recent__c")
        if not email or not campaign_name or not mql_date:
            continue
        existing = by_email.get(email)
        if existing is None or mql_date > existing["mql_date"]:
            by_email[email] = {"campaign": campaign_name, "mql_date": mql_date}

    return list(by_email.values())


def fetch_sql_records(instance_url: str, token: str, since_iso: str) -> list[dict]:
    """Pull Opportunities with campaign attribution (SQL = Opportunity created)."""
    fields = "Campaign.Name, CreatedDate, IsWon, Amount"
    where = f"CampaignId != null AND CreatedDate >= {since_iso}"
    opps = soql_query(instance_url, token, f"SELECT {fields} FROM Opportunity WHERE {where}")

    result = []
    for rec in opps:
        campaign_rel = rec.get("Campaign") or {}
        campaign_name = campaign_rel.get("Name")
        created = rec.get("CreatedDate")
        if not campaign_name or not created:
            continue
        result.append({
            "campaign": campaign_name,
            "created_date": created,
            "is_won": bool(rec.get("IsWon")),
            "amount": rec.get("Amount") or 0,
        })
    return result


# ── Aggregation ────────────────────────────────────────────────────────────────

def aggregate_mql_by_campaign_month(records: list[dict]) -> dict[tuple, int]:
    agg: dict[tuple, int] = {}
    for r in records:
        if not is_paid_ppc(r["campaign"]):
            continue
        ym = year_month_from_sf_date(r["mql_date"])
        if not ym:
            continue
        key = (r["campaign"], ym[0], ym[1])
        agg[key] = agg.get(key, 0) + 1
    return agg


def aggregate_sql_by_campaign_month(records: list[dict]) -> dict[tuple, int]:
    agg: dict[tuple, int] = {}
    for r in records:
        if not is_paid_ppc(r["campaign"]):
            continue
        ym = year_month_from_sf_date(r["created_date"])
        if not ym:
            continue
        key = (r["campaign"], ym[0], ym[1])
        agg[key] = agg.get(key, 0) + 1
    return agg


def aggregate_monthly_totals(sql_records: list[dict]) -> dict[tuple, dict]:
    """Per (year, month) across all paid-PPC campaigns: sql, cw count, cw$, total pipeline."""
    agg: dict[tuple, dict] = {}
    for r in sql_records:
        if not is_paid_ppc(r["campaign"]):
            continue
        ym = year_month_from_sf_date(r["created_date"])
        if not ym:
            continue
        key = ym
        if key not in agg:
            agg[key] = {"sql": 0, "cw": 0, "cw_amount": 0.0, "pipeline": 0.0}
        agg[key]["sql"] += 1
        agg[key]["pipeline"] += float(r["amount"] or 0)
        if r["is_won"]:
            agg[key]["cw"] += 1
            agg[key]["cw_amount"] += float(r["amount"] or 0)
    return agg


def aggregate_mql_monthly_totals(mql_records: list[dict]) -> dict[tuple, int]:
    agg: dict[tuple, int] = {}
    for r in mql_records:
        if not is_paid_ppc(r["campaign"]):
            continue
        ym = year_month_from_sf_date(r["mql_date"])
        if not ym:
            continue
        agg[ym] = agg.get(ym, 0) + 1
    return agg


# ── Google Sheets ──────────────────────────────────────────────────────────────

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


def read_tab(service, tab_name: str) -> list[list]:
    result = service.spreadsheets().values().get(
        spreadsheetId=SHEET_ID, range=f"{tab_name}!A:Z"
    ).execute()
    return result.get("values", [])


def safe_int(v) -> int:
    try:
        return int(float(str(v).strip()))
    except (ValueError, TypeError):
        return 0


def gads_spend_by_month(service, months: list[tuple]) -> dict[tuple, float]:
    """Sum GadsData Cost by (year, month) for the requested months (fallback
    Spend source for MonthlySummary months with no existing Looker row)."""
    rows = read_tab(service, GADS_TAB)
    wanted = set(months)
    spend: dict[tuple, float] = {}
    for row in rows[1:]:
        if len(row) < 6:
            continue
        yr_s, mo_s = str(row[1]).strip(), str(row[2]).strip()
        if "-" in mo_s:
            yr, mo = int(mo_s[0:4]), int(mo_s[5:7])
        elif "-" in yr_s:
            yr, mo = int(yr_s[0:4]), int(yr_s[5:7])
        else:
            yr, mo = safe_int(yr_s), safe_int(mo_s)
        if (yr, mo) not in wanted:
            continue
        try:
            cost = float(row[5])
        except (ValueError, TypeError):
            continue
        spend[(yr, mo)] = spend.get((yr, mo), 0.0) + cost
    return spend


def sync_campaigns_data(service, since_ym: tuple, mql_agg: dict, sql_agg: dict, dry_run: bool) -> None:
    rows = read_tab(service, CAMPAIGNS_TAB)
    header = rows[0] if rows else ["Source", "Campaign", "Year", "Month", "MQL", "SQL"]

    kept = []
    removed = 0
    for row in rows[1:]:
        if len(row) < 6:
            kept.append(row)
            continue
        source, name, yr, mo = str(row[0]).strip(), str(row[1]).strip(), safe_int(row[2]), safe_int(row[3])
        if source.lower() == "paid" and is_paid_ppc(name) and (yr, mo) >= since_ym:
            removed += 1
            continue
        kept.append(row)

    new_rows = []
    for (campaign, yr, mo), count in sorted(mql_agg.items()):
        new_rows.append(["Paid", campaign, yr, mo, count, 0])
    for (campaign, yr, mo), count in sorted(sql_agg.items()):
        new_rows.append(["Paid", campaign, yr, mo, 0, count])

    print(f"  CampaignsData: removing {removed} stale Paid/PPC rows >= {since_ym}, "
          f"adding {len(new_rows)} new rows ({len(mql_agg)} MQL rows, {len(sql_agg)} SQL rows).")

    if dry_run:
        return

    all_rows = kept + new_rows
    service.spreadsheets().values().clear(
        spreadsheetId=SHEET_ID, range=f"{CAMPAIGNS_TAB}!A:Z"
    ).execute()
    service.spreadsheets().values().update(
        spreadsheetId=SHEET_ID, range=f"{CAMPAIGNS_TAB}!A1",
        valueInputOption="RAW",
        body={"values": [header] + all_rows},
    ).execute()
    print(f"  CampaignsData: wrote {len(all_rows)} total rows.")


def sync_monthly_summary(service, months: list[tuple], mql_by_month: dict,
                          monthly_totals: dict, spend_fallback: dict, dry_run: bool) -> None:
    rows = read_tab(service, MONTHLY_TAB)
    header = rows[0] if rows else None
    if header is None:
        print("  MonthlySummary: tab is empty, skipping (expected header row).")
        return

    # Index existing rows by (year, month) parsed from the label column
    by_ym: dict[tuple, list] = {}
    other_rows: list[list] = []
    for row in rows[1:]:
        label = str(row[0]).strip() if row else ""
        parts = label.replace(",", " ").split()
        ym = None
        if len(parts) == 2:
            mon = MONTH_NAME_TO_NUM.get(parts[0].lower())
            yr_s = parts[1].lstrip("'")
            if mon and yr_s.isdigit():
                yr = int(yr_s) if len(yr_s) == 4 else 2000 + int(yr_s)
                ym = (yr, mon)
        if ym and ym in set(months):
            by_ym[ym] = row
        else:
            other_rows.append(row)

    updated, created = 0, 0
    result_rows = []
    for ym in months:
        row = list(by_ym.get(ym, []))
        # Pad to header width
        while len(row) < len(header):
            row.append("")
        totals = monthly_totals.get(ym, {"sql": 0, "cw": 0, "cw_amount": 0.0, "pipeline": 0.0})
        mql = mql_by_month.get(ym, 0)
        sql = totals["sql"]
        cw = totals["cw"]

        if not row[0]:
            row[0] = month_label(*ym)
            spend = spend_fallback.get(ym, "")
            row[1] = round(spend, 2) if spend else ""
            created += 1
        else:
            updated += 1

        spend_val = row[1] if row[1] not in ("", None) else spend_fallback.get(ym, 0)
        try:
            spend_val = float(spend_val)
        except (ValueError, TypeError):
            spend_val = 0.0

        row[6] = mql                                   # MQL
        row[8] = sql                                    # SQL
        row[9] = round(sql / mql, 4) if mql else 0       # MQL to SQL
        row[10] = round(totals["pipeline"], 2)          # Total Pipeline
        row[11] = cw                                    # CW
        row[12] = round(cw / mql, 4) if mql else 0       # MQL to CW
        row[13] = round(cw / sql, 4) if sql else 0       # SQL to CW
        row[14] = round(totals["cw_amount"], 2)          # CW$
        row[15] = round(spend_val / cw, 2) if cw and spend_val else (row[15] if len(row) > 15 else "")  # CAC
        row[16] = round(spend_val / mql, 2) if mql and spend_val else (row[16] if len(row) > 16 else "")  # CP MQL
        row[17] = round(spend_val / sql, 2) if sql and spend_val else (row[17] if len(row) > 17 else "")  # CP SQL
        row[18] = round(totals["cw_amount"] / mql, 2) if mql and totals["cw_amount"] else (row[18] if len(row) > 18 else "")  # CW$/MQL

        result_rows.append(row)

    print(f"  MonthlySummary: updating {updated} existing month rows, creating {created} new month rows "
          f"for {[month_label(*ym) for ym in months]}.")

    if dry_run:
        return

    all_rows = other_rows + result_rows
    service.spreadsheets().values().clear(
        spreadsheetId=SHEET_ID, range=f"{MONTHLY_TAB}!A:Z"
    ).execute()
    service.spreadsheets().values().update(
        spreadsheetId=SHEET_ID, range=f"{MONTHLY_TAB}!A1",
        valueInputOption="RAW",
        body={"values": [header] + all_rows},
    ).execute()
    print(f"  MonthlySummary: wrote {len(all_rows)} total rows.")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Sync Salesforce MQL/SQL data to CampaignsData + MonthlySummary tabs "
                     "(replaces the dead Looker export)"
    )
    parser.add_argument("--alias", default=DEFAULT_ALIAS, help="SF CLI org alias")
    parser.add_argument("--since", default="2026-01", help="YYYY-MM to backfill from (default: 2026-01)")
    parser.add_argument("--dry-run", action="store_true", help="Compute and print, skip writing to the sheet")
    args = parser.parse_args()

    since_ym = parse_since(args.since)
    since_iso = f"{since_ym[0]:04d}-{since_ym[1]:02d}-01T00:00:00Z"
    months = months_from(since_ym)

    print(f"[1/5] Getting Salesforce token for org: {args.alias}")
    access_token, instance_url = get_sf_token(args.alias)
    print(f"  Connected to {instance_url}")

    print(f"\n[2/5] Pulling MQL records (Lead + Contact) since {since_iso}...")
    mql_records = fetch_mql_records(instance_url, access_token, since_iso)
    print(f"  {len(mql_records)} deduplicated MQL records (all campaigns).")

    print(f"\n[3/5] Pulling SQL/Opportunity records since {since_iso}...")
    sql_records = fetch_sql_records(instance_url, access_token, since_iso)
    print(f"  {len(sql_records)} Opportunity records (all campaigns).")

    mql_agg = aggregate_mql_by_campaign_month(mql_records)
    sql_agg = aggregate_sql_by_campaign_month(sql_records)
    mql_by_month = aggregate_mql_monthly_totals(mql_records)
    monthly_totals = aggregate_monthly_totals(sql_records)

    print(f"\n[4/5] Paid-PPC totals by month:")
    for ym in months:
        t = monthly_totals.get(ym, {"sql": 0, "cw": 0, "cw_amount": 0.0, "pipeline": 0.0})
        print(f"  {month_label(*ym)}: MQL={mql_by_month.get(ym, 0):>4}  SQL={t['sql']:>4}  "
              f"CW={t['cw']:>3}  CW$={t['cw_amount']:>10,.0f}")

    print(f"\n[5/5] {'[DRY RUN] ' if args.dry_run else ''}Writing to Google Sheet...")
    sheets_service = get_sheets_service()
    spend_fallback = gads_spend_by_month(sheets_service, months)
    sync_campaigns_data(sheets_service, since_ym, mql_agg, sql_agg, args.dry_run)
    sync_monthly_summary(sheets_service, months, mql_by_month, monthly_totals, spend_fallback, args.dry_run)

    if args.dry_run:
        print("\nDry run complete — nothing written. Re-run without --dry-run to write.")
    else:
        print("\nDone! CampaignsData and MonthlySummary are now sourced directly from Salesforce "
              f"for {month_label(*months[0])}–{month_label(*months[-1])}.")


if __name__ == "__main__":
    main()
