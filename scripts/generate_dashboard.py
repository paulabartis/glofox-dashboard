"""
Dashboard Generator

Reads Google Ads data (GadsData tab), MQL/SQL data (CampaignsData tab), and
aggregate KPIs (MonthlySummary tab) from the Glofox Google Sheet, then
generates dashboard/index.html with all data embedded as JSON.

The HTML template (dashboard/template.html) handles all rendering via
vanilla JS + Chart.js. This script only prepares and injects the data.

Usage:
    python scripts/generate_dashboard.py
    python scripts/generate_dashboard.py --template dashboard/template.html --output index.html

Author: Claude Code
Created: 2026-03-11
"""

from __future__ import annotations

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


def parse_month_from_date(val: Any) -> int:
    """
    Extract month integer from Google Ads API date field.
    The Sheets API stores segments.month as a date string e.g. '2025-08-01'.
    Returns the month as int (1-12), or 0 if unparseable.
    """
    s = str(val).strip()
    # Format: YYYY-MM-DD
    if len(s) == 10 and s[4] == "-":
        try:
            return int(s[5:7])
        except ValueError:
            pass
    # Fallback: try plain integer
    return safe_int(val)


# ── Campaign name parsing ─────────────────────────────────────────────────────

def parse_campaign_meta(name: str) -> dict:
    """
    Extract campaign_type, region, and channel from a Glofox campaign name.

    Naming convention: SEGMENT_Direction_Channel_PPC_Type_CampaignType_Region_MMDDYY
    Example: SMB_Inbound_Google_PPC_SEM_GymMgmt_WW_010125
    """
    parts = name.split("_")

    # Channel classification first — needed to set Demand Gen campaign type
    if "SEM" in parts:
        channel = "Paid Search"
    elif any(p in parts for p in ("SM", "DG", "DIS")):
        channel = "Paid Other"
    else:
        channel = "Other"

    # Campaign type (check substrings in order of specificity)
    # DG/DIS campaigns without a named type → "Demand Gen" bucket
    if "GymMgmt" in parts:
        campaign_type = "GymManagement"
    elif "Branded" in parts:
        campaign_type = "Branded"
    elif "Competitor" in parts:
        campaign_type = "Competitor"
    elif "Modality" in parts:
        campaign_type = "Modality"
    elif channel == "Paid Other":
        campaign_type = "Demand Gen"
    else:
        campaign_type = "Other"

    # Region — check each part against known region codes
    region = "EMEA"  # default (WW or unrecognised → EMEA)
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
            "month": parse_month_from_date(row[2]),
            "impressions": safe_int(row[3]),
            "clicks": safe_int(row[4]),
            "cost": safe_float(row[5]),
        })
    return result


def parse_adgroup_campaign_name(name: str) -> dict:
    """
    Parse Google Ads readable campaign names into campaign_type + region.
    Scans ALL words (not just last) so suffixes like 'tCPA', 'Test', 'May 2025'
    don't break classification.

    Region priority: APAC > NAM > EMEA (default / WW / UK / EU / global).
    Region tokens (case-insensitive, matched as whole tokens after splitting on
    spaces, underscores and hyphens):
      APAC, AU                           → APAC
      USA, US, CA, NAM, NA, "NA TIER"   → NAM
      UK, WW, EU, EMEA, GLOBAL          → EMEA  (also the default)
    """
    name_upper = name.upper()

    # Tokenise on spaces, underscores, hyphens so 'PMax_Prospect_US' → ['US']
    import re as _re
    tokens = set(_re.split(r'[\s_\-]+', name_upper))

    # Region — check all tokens, priority: APAC > NAM > EMEA
    if tokens & {"APAC", "AU"}:
        region = "APAC"
    elif tokens & {"USA", "US", "CA", "NAM", "NA"}:
        region = "NAM"
    else:
        region = "EMEA"  # WW, UK, EU, EMEA, Global, or unrecognised → EMEA

    # Campaign type from name content
    if "COMPETITOR" in name_upper:
        campaign_type = "Competitor"
    elif "GYM MANAGEMENT" in name_upper or "GYM_MANAGEMENT" in name_upper or "GYMMGMT" in name_upper:
        campaign_type = "GymManagement"
    elif "MODALITY" in name_upper:
        campaign_type = "Modality"
    elif "BRANDED" in name_upper or "GLOFOX" in name_upper:
        campaign_type = "Branded"
    elif any(t in name_upper for t in ("PROSPECT", "RETARGET", "PMAX", "DG ", "DEMAND GEN")):
        campaign_type = "Demand Gen"
    else:
        campaign_type = "Other"

    return {"campaign_type": campaign_type, "region": region}


def make_display_name(name: str) -> str:
    """
    Convert a Looker-style campaign name to a short human-readable label.
    e.g. 'SMB_Inbound_Google_PPC_SEM_GymMgmt_WW_010125' → 'GymMgmt · WW · Google Search'
    """
    parts = name.split("_")
    provider_map = {"Google": "Google", "Bing": "Bing", "FB": "Meta", "Meta": "Meta"}
    provider = next((provider_map[p] for p in parts if p in provider_map), "")
    try:
        ppc_idx = parts.index("PPC")
    except ValueError:
        return name[:40]
    relevant = parts[ppc_idx + 1:]
    if relevant and re.match(r"^\d{6}$", relevant[-1]):
        relevant = relevant[:-1]
    channel_map = {"SEM": "Search", "DG": "Demand Gen", "DIS": "Display", "SM": "Social"}
    channel = channel_map.get(relevant[0], "") if relevant else ""
    rest = relevant[1:] if relevant else []
    label_parts = [r for r in rest if r]
    if provider and channel:
        label_parts.append(f"{provider} {channel}")
    elif channel:
        label_parts.append(channel)
    return " · ".join(label_parts) if label_parts else name[:40]


def load_adgroup_data(service) -> list[dict]:
    """
    AdGroupData tab (written by sync_gads_to_sheet.py).
    Columns: Campaign | Ad Group | Year | Month | Impressions | Clicks | Cost

    Uses parse_adgroup_campaign_name() since Google Ads API returns human-readable
    names (e.g. 'Competitor Brands USA'), not the Looker naming convention.
    """
    rows = read_tab(service, "AdGroupData")
    result = []
    for row in rows[1:]:  # skip header
        if len(row) < 7:
            continue
        campaign = str(row[0]).strip()
        adgroup = str(row[1]).strip()
        if not campaign or not adgroup:
            continue
        meta = parse_adgroup_campaign_name(campaign)
        result.append({
            "campaign": campaign,
            "adgroup": adgroup,
            "year": safe_int(row[2]),
            "month": parse_month_from_date(row[3]),
            "impressions": safe_int(row[4]),
            "clicks": safe_int(row[5]),
            "cost": safe_float(row[6]),
            "campaign_type": meta["campaign_type"],
            "region": meta["region"],
        })
    return result


def load_search_terms(service) -> list[dict]:
    """
    SearchTermsData tab (written by sync_gads_to_sheet.py).
    Columns: Search Term | Campaign | Ad Group | Year | Month | Impressions | Clicks | Cost | Conversions

    Uses parse_adgroup_campaign_name() since these are Google Ads readable names.
    Returns empty list if tab doesn't exist yet.
    """
    try:
        rows = read_tab(service, "SearchTermsData")
    except Exception:
        return []
    result = []
    for row in rows[1:]:  # skip header
        if len(row) < 8:
            continue
        search_term   = str(row[0]).strip()
        campaign_name = str(row[1]).strip()
        adgroup_name  = str(row[2]).strip()
        if not search_term or not campaign_name:
            continue
        meta = parse_adgroup_campaign_name(campaign_name)
        result.append({
            "search_term":   search_term,
            "campaign":      campaign_name,
            "adgroup":       adgroup_name,
            "year":          safe_int(row[3]),
            "month":         parse_month_from_date(row[4]),
            "impressions":   safe_int(row[5]),
            "clicks":        safe_int(row[6]),
            "cost":          safe_float(row[7]),
            "conversions":   safe_float(row[8]) if len(row) > 8 else 0.0,
            "campaign_type": meta["campaign_type"],
            "region":        meta["region"],
        })
    return result


def load_campaign_ids(service) -> dict[str, str]:
    """
    CampaignIds tab (written by sync_gads_to_sheet.py fetch_campaign_ids).
    Returns {campaign_name: campaign_id} for Google Ads deep links.
    Returns empty dict if tab doesn't exist yet.
    """
    try:
        rows = read_tab(service, "CampaignIds")
    except Exception:
        return {}
    result = {}
    for row in rows[1:]:  # skip header
        if len(row) < 2:
            continue
        campaign_id   = str(row[0]).strip()
        campaign_name = str(row[1]).strip()
        if campaign_id and campaign_name:
            result[campaign_name] = campaign_id
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


def load_change_events(service) -> list[dict]:
    """
    ChangeEvents tab (written by sync_gads_to_sheet.py).
    Columns: DateTime | User | ResourceType | Operation | Campaign | ChangedFields
    Returns empty list if tab doesn't exist yet.
    """
    try:
        rows = read_tab(service, "ChangeEvents")
    except Exception:
        return []
    result = []
    for row in rows[1:]:  # skip header
        if len(row) < 4:
            continue
        result.append({
            "change_datetime": str(row[0]).strip(),
            "user_email":      str(row[1]).strip() if len(row) > 1 else "",
            "resource_type":   str(row[2]).strip() if len(row) > 2 else "",
            "operation":       str(row[3]).strip() if len(row) > 3 else "",
            "campaign_name":   str(row[4]).strip() if len(row) > 4 else "",
            "changed_fields":  str(row[5]).strip() if len(row) > 5 else "",
        })
    return result


def load_is_weekly(service) -> list[dict]:
    """
    ImpShareWeekly tab (written by sync_gads_to_sheet.py).
    Columns: Week | Campaign | Impressions | SearchIS | LostIS_Rank
    Returns one row per (campaign, week). JS computes the "All" aggregate on the fly.
    Returns empty list if tab doesn't exist yet.
    """
    try:
        rows = read_tab(service, "ImpShareWeekly")
    except Exception:
        return []
    result = []
    for row in rows[1:]:  # skip header
        if len(row) < 1:
            continue
        week = str(row[0]).strip()
        if not week:
            continue
        # Support both old 4-col format (no campaign) and new 5-col format
        if len(row) >= 5:
            campaign    = str(row[1]).strip()
            impressions = safe_int(row[2])
            search_is   = safe_float(row[3]) if row[3] != "" else None
            lost_is     = safe_float(row[4]) if row[4] != "" else None
        else:
            campaign    = "All"
            impressions = safe_int(row[1]) if len(row) > 1 else 0
            search_is   = safe_float(row[2]) if len(row) > 2 and row[2] != "" else None
            lost_is     = safe_float(row[3]) if len(row) > 3 and row[3] != "" else None
        result.append({
            "week":         week,
            "campaign":     campaign,
            "impressions":  impressions,
            "search_is":    search_is,
            "lost_is_rank": lost_is,
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
    Build campaign rows for the dashboard from two incompatible naming systems.

    GadsData uses Google Ads readable names ("Gym Management USA") while
    CampaignsData uses Looker-style names ("SMB_Inbound_Google_PPC_SEM_GymMgmt_USA_010125").
    A name-level join is impossible, so the two sources are kept separate:

    1. CampaignsData rows → one row per Looker campaign (MQL/SQL, cost=0).
    2. GadsData aggregate rows → one row per (campaign_type, region, year, month)
       carrying real cost/impressions/clicks, mql=sql=0, flagged _is_gads_agg=True.

    The JS groups by campaign_type and region, so Overview tab aggregates are correct.
    compute_optimizations() uses both row types to build per-(type, region) cards.
    """
    merged: list[dict] = []

    # ── 1. CampaignsData rows (MQL/SQL, no cost) ────────────────────────────
    for row in campaigns_data:
        meta = parse_campaign_meta(row["name"])
        merged.append({
            "campaign_name": row["name"],
            "year":          row["year"],
            "month":         row["month"],
            "label":         month_label(row["year"], row["month"]),
            "campaign_type": meta["campaign_type"],
            "region":        meta["region"],
            "channel":       meta["channel"],
            "impressions":   0,
            "clicks":        0,
            "cost":          0.0,
            "mql":           row["mql"],
            "sql":           row["sql"],
            "_is_gads_agg":  False,
        })

    # ── 2. GadsData aggregate rows (cost/traffic, no MQL/SQL) ───────────────
    # Aggregate GadsData by (campaign_type, region, year, month).
    # GadsData names are Google Ads readable → parse with parse_adgroup_campaign_name().
    gads_agg: dict[tuple, dict] = {}
    for row in gads_data:
        yr = row["year"]
        mo = row["month"]
        if yr == 0 or mo == 0:
            continue
        meta = parse_adgroup_campaign_name(row["name"])
        ct   = meta["campaign_type"]
        reg  = meta["region"]
        key  = (ct, reg, yr, mo)
        if key not in gads_agg:
            # Channel: Demand Gen campaigns → Paid Other; all others → Paid Search
            ch = "Paid Other" if ct == "Demand Gen" else "Paid Search"
            gads_agg[key] = {
                "campaign_type": ct,
                "region":        reg,
                "year":          yr,
                "month":         mo,
                "channel":       ch,
                "impressions":   0,
                "clicks":        0,
                "cost":          0.0,
            }
        gads_agg[key]["impressions"] += row["impressions"]
        gads_agg[key]["clicks"]      += row["clicks"]
        gads_agg[key]["cost"]        += row["cost"]

    for (ct, reg, yr, mo), g in gads_agg.items():
        merged.append({
            "campaign_name": f"__gads_{ct}_{reg}",
            "year":          yr,
            "month":         mo,
            "label":         month_label(yr, mo),
            "campaign_type": g["campaign_type"],
            "region":        g["region"],
            "channel":       g["channel"],
            "impressions":   g["impressions"],
            "clicks":        g["clicks"],
            "cost":          g["cost"],
            "mql":           0,
            "sql":           0,
            "_is_gads_agg":  True,
        })

    merged.sort(key=lambda x: (x["year"], x["month"], x["campaign_name"]))
    return merged


# ── Optimizations engine ─────────────────────────────────────────────────────

def compute_optimizations(
    campaign_rows: list[dict],
    adgroup_data: list[dict],
    campaign_ids_map: dict[str, str] | None = None,
) -> list[dict]:
    """
    Analyse the most recent 3 months of campaign data and generate up to 10
    prioritised optimization recommendations per (campaign_type, region) bucket.

    campaign_rows contains two row types (set by build_campaign_rows):
      • _is_gads_agg=False  → Looker/CampaignsData rows: real MQL/SQL, cost=0
      • _is_gads_agg=True   → GadsData aggregate rows:   real cost/impressions/clicks, mql=sql=0

    These are combined per (campaign_type, region) to give full metrics for each card.

    Returns a list of dicts (sorted by type → region) each with:
      name, display_name, campaign_type, region, channel,
      metrics {cost, impressions, clicks, mql, sql},
      issues [str, …], severity, period_label
    """
    _TYPE_ORDER   = ["GymManagement", "Modality", "Branded", "Competitor", "Demand Gen", "Other"]
    _REGION_ORDER = ["NAM", "EMEA", "APAC"]
    _TYPE_LABELS  = {
        "GymManagement": "Gym Mgmt", "Modality": "Modality",
        "Branded": "Branded", "Competitor": "Competitor",
        "Demand Gen": "Demand Gen", "Other": "Other",
    }

    # ── 1. Determine the 3-month window ──────────────────────────────────────
    all_yms = sorted({
        r["year"] * 100 + r["month"]
        for r in campaign_rows
        if r["year"] > 0 and r["month"] > 0
    })
    if not all_yms:
        return []

    max_ym   = all_yms[-1]
    max_year = max_ym // 100
    max_mon  = max_ym % 100
    s_mon    = max_mon - 2
    s_year   = max_year
    if s_mon <= 0:
        s_mon  += 12
        s_year -= 1
    from_ym = s_year * 100 + s_mon

    def _ym_label(ym: int) -> str:
        y, mo = divmod(ym, 100)
        return ["Jan","Feb","Mar","Apr","May","Jun",
                "Jul","Aug","Sep","Oct","Nov","Dec"][mo-1] + f" '{str(y)[2:]}"

    window_yms   = [ym for ym in all_yms if ym >= from_ym]
    period_label = (
        f"{_ym_label(window_yms[0])} – {_ym_label(window_yms[-1])}"
        if window_yms else "Last 3 months"
    )

    # ── 2. Separate cost rows (GadsData) and MQL/SQL rows (CampaignsData) ────
    # Group both by (campaign_type, region) — the natural join key.
    mql_sql_agg: dict[tuple, dict] = {}   # (ct, reg) → {mql, sql, channel}
    cost_agg:    dict[tuple, dict] = {}   # (ct, reg) → {cost, impressions, clicks, channel}

    for r in campaign_rows:
        if r["year"] * 100 + r["month"] < from_ym:
            continue
        ct  = r["campaign_type"]
        reg = r["region"]
        key = (ct, reg)

        if r.get("_is_gads_agg"):
            if key not in cost_agg:
                cost_agg[key] = {"channel": r["channel"], "impressions": 0, "clicks": 0, "cost": 0.0}
            cost_agg[key]["cost"]        += r["cost"]
            cost_agg[key]["impressions"] += r["impressions"]
            cost_agg[key]["clicks"]      += r["clicks"]
        else:
            if key not in mql_sql_agg:
                mql_sql_agg[key] = {"channel": r["channel"], "mql": 0, "sql": 0}
            mql_sql_agg[key]["mql"] += r["mql"]
            mql_sql_agg[key]["sql"] += r["sql"]

    # ── 3. Combine per-(campaign_type, region) ────────────────────────────────
    all_keys = set(mql_sql_agg.keys()) | set(cost_agg.keys())
    if not all_keys:
        return []

    camp_agg: dict[tuple, dict] = {}
    for key in all_keys:
        ct, reg    = key
        mq         = mql_sql_agg.get(key, {"mql": 0, "sql": 0, "channel": "Paid Search"})
        co         = cost_agg.get(key, {"cost": 0.0, "impressions": 0, "clicks": 0, "channel": "Paid Search"})
        # Prefer channel from cost_agg (GadsData) when cost is present, else from MQL rows
        channel    = co["channel"] if co["cost"] > 0 else mq.get("channel", "Paid Search")
        camp_agg[key] = {
            "campaign_type": ct,
            "region":        reg,
            "channel":       channel,
            "cost":          co["cost"],
            "impressions":   co["impressions"],
            "clicks":        co["clicks"],
            "mql":           mq["mql"],
            "sql":           mq["sql"],
        }

    # ── 4. Benchmarks ─────────────────────────────────────────────────────────
    cpcs    = [v["cost"]/v["clicks"] for v in camp_agg.values() if v["clicks"]  >= 30]
    cp_mqls = [v["cost"]/v["mql"]    for v in camp_agg.values()
               if v["mql"] >= 3 and v["cost"] > 0]
    avg_cpc    = sum(cpcs)    / len(cpcs)    if cpcs    else 0.0
    avg_cp_mql = sum(cp_mqls) / len(cp_mqls) if cp_mqls else 0.0

    # ── 5. Generate issues per (campaign_type, region) ────────────────────────
    result = []
    for (ct, reg), m in camp_agg.items():
        issues: list[tuple[int, str]] = []   # (priority, text)

        cost = m["cost"]
        imp  = m["impressions"]
        clk  = m["clicks"]
        mql  = m["mql"]
        sql  = m["sql"]
        ch   = m["channel"]

        ctr     = clk  / imp  if imp  > 0 else 0.0
        cpc     = cost / clk  if clk  > 0 else 0.0
        cp_mql  = cost / mql  if mql  > 0 else 0.0
        mql_sql = sql  / mql  if mql  > 0 else 0.0

        # P1 – Spend with 0 MQLs
        if cost > 300 and mql == 0:
            issues.append((1,
                f"${cost:,.0f} spend · 0 MQLs — "
                f"1. Test LP form manually (Inspect > Network). "
                f"2. Review search terms for off-target queries. "
                f"3. Add exact-match negatives. "
                f"4. Verify UTM tracking is capturing form submissions."))

        # P1 – Strong CTR but no MQL conversion (LP mismatch)
        if clk >= 30 and mql == 0 and ctr >= 0.025:
            issues.append((1,
                f"CTR {ctr*100:.1f}% · 0 MQLs from {clk:,} clicks — "
                f"1. Check LP headline matches ad copy. "
                f"2. Run session recording (Hotjar/FullStory) on the landing page. "
                f"3. Reduce form to 5 fields or fewer. "
                f"4. Add social proof or trust signals above the fold."))

        # P2 – Low CTR on Search
        if ch == "Paid Search" and imp >= 500 and ctr < 0.01:
            issues.append((2,
                f"CTR {ctr*100:.1f}% vs 2–4% Search benchmark — "
                f"1. Pin top-performing headline to position 1 in RSA. "
                f"2. Add urgency or a specific offer in headline 2. "
                f"3. Review keyword-to-ad-group relevance — tighten match types. "
                f"4. Test new description lines with feature + CTA."))

        # P2 – Low CTR on Display / Demand Gen
        if ch == "Paid Other" and imp >= 5000 and ctr < 0.002:
            issues.append((2,
                f"CTR {ctr*100:.2f}% for display/demand gen — "
                f"1. Rotate in new creatives — refresh images and video thumbnails. "
                f"2. Test a new audience segment (lookalike vs interest-based). "
                f"3. Check frequency — if avg > 5, creative fatigue is likely the cause."))

        # P2 – CPC above benchmark
        if avg_cpc > 0 and clk >= 20 and cpc > avg_cpc * 1.6:
            issues.append((2,
                f"CPC ${cpc:.2f} is {cpc/avg_cpc:.1f}× avg (${avg_cpc:.2f}) — "
                f"1. Lower Target CPA by 10% and monitor for 1 week. "
                f"2. Improve Quality Score: tighten ad-to-keyword relevance and LP experience. "
                f"3. Pause highest-CPC keywords with 0 conversions in last 90 days."))

        # P2 – Cost/MQL above benchmark
        if avg_cp_mql > 0 and mql >= 3 and cp_mql > avg_cp_mql * 1.5:
            excess = round((cp_mql - avg_cp_mql) * mql)
            issues.append((2,
                f"Cost/MQL ${cp_mql:,.0f} is {cp_mql/avg_cp_mql:.1f}× avg — "
                f"fixing to benchmark saves ~${excess:,}. "
                f"1. Pause keywords with $50+ spend and 0 MQLs. "
                f"2. Move broad match keywords to phrase or exact. "
                f"3. Review LP relevance — ensure ad intent matches form offer."))

        # P2 – Very low click-to-MQL rate
        if clk >= 50 and mql > 0 and (mql / clk) < 0.005:
            issues.append((2,
                f"Click-to-MQL {mql/clk*100:.2f}% — "
                f"1. A/B test a shorter LP variant with single CTA. "
                f"2. Reduce required form fields. "
                f"3. Add a progress indicator to the form. "
                f"4. Check mobile LP load speed (target < 3s)."))

        # P1/P2 – Low MQL→SQL rate (goal = 25%)
        if mql >= 5 and mql_sql < 0.15:
            missed = round(mql * (0.25 - mql_sql))
            issues.append((1,
                f"MQL→SQL {mql_sql*100:.0f}% is critically low — ~{missed} missed SQLs vs 25% goal. "
                f"1. Pull MQL list in Salesforce and check rejection reasons. "
                f"2. Review ICP criteria — are ad keywords attracting the right buyer segment? "
                f"3. Check sales routing speed — MQLs should be followed up within 2 hrs. "
                f"4. Lower MQL score threshold by 5 pts and monitor for 2 weeks."))
        elif mql >= 5 and mql_sql < 0.25:
            missed = round(mql * (0.25 - mql_sql))
            issues.append((2,
                f"MQL→SQL {mql_sql*100:.0f}% below 25% goal — ~{missed} missed SQLs. "
                f"1. Review recently rejected MQLs for patterns. "
                f"2. Confirm ICP alignment between ad targeting and LP messaging. "
                f"3. Check if MQLs are routing to the correct sales rep and region."))

        # P3 – MQLs but 0 SQLs
        if mql >= 5 and sql == 0:
            issues.append((3,
                f"{mql} MQLs · 0 SQLs — "
                f"1. Verify Salesforce campaign attribution is set correctly. "
                f"2. Check sales handoff — confirm MQLs are being actioned, not stalled. "
                f"3. Review MQL definition for this campaign type."))

        # P3 – Near-zero impressions relative to spend
        if cost > 200 and imp < 100 and clk == 0:
            issues.append((3,
                f"Only {imp} impressions on ${cost:,.0f} spend — "
                f"1. Check campaign status and ad approval. "
                f"2. Review bid — may be too low to enter auction. "
                f"3. Check audience or keyword eligibility (too narrow?). "
                f"4. Review Quality Score for active keywords."))

        # ── Sort, cap, severity ───────────────────────────────────────────────
        issues.sort(key=lambda x: x[0])
        top_issues = issues[:10]

        priorities = [p for p, _ in top_issues]
        if   any(p <= 1 for p in priorities): severity = "high"
        elif any(p <= 2 for p in priorities): severity = "medium"
        elif priorities:                      severity = "low"
        else:                                 severity = "ok"

        # Display name: human-readable type + region label
        type_lbl = _TYPE_LABELS.get(ct, ct)
        display_name = f"{type_lbl} · {reg}"

        # Campaign IDs for Google Ads deep links — derive from adgroup_data campaign names
        ids_map = campaign_ids_map or {}
        campaign_ids: list[str] = []
        if ids_map:
            seen_names: set[str] = set()
            for ag in adgroup_data:
                if ag["campaign_type"] == ct and ag["region"] == reg:
                    cname = ag["campaign"]
                    if cname not in seen_names:
                        seen_names.add(cname)
                        if cname in ids_map:
                            campaign_ids.append(ids_map[cname])

        result.append({
            "name":          f"{ct}_{reg}",
            "display_name":  display_name,
            "campaign_type": ct,
            "region":        reg,
            "channel":       ch,
            "metrics": {
                "cost":        round(cost, 2),
                "impressions": imp,
                "clicks":      clk,
                "mql":         mql,
                "sql":         sql,
            },
            "issues":        [t for _, t in top_issues],
            "severity":      severity,
            "period_label":  period_label,
            "campaign_ids":  campaign_ids,
        })

    # Sort by type order → region order → name
    def _sort_key(r: dict) -> tuple:
        t = _TYPE_ORDER.index(r["campaign_type"])   if r["campaign_type"] in _TYPE_ORDER   else 99
        g = _REGION_ORDER.index(r["region"])        if r["region"]        in _REGION_ORDER else 99
        return (t, g, r["name"])

    result.sort(key=_sort_key)
    return result


# ── Ad Group Optimizations ────────────────────────────────────────────────────

def compute_adgroup_optimizations(adgroup_data: list[dict]) -> list[dict]:
    """
    Flag ad-group-level issues from AdGroupData over the last 3 months.

    Issues checked (per ad group):
      P1 – Cost > $200 with 0 clicks       (bid/QS/targeting problem)
      P1 – Cost > $200 with CTR < 0.2%     (severely under-performing)
      P2 – CPC > 2× campaign-type average  (overpaying relative to peers)
      P2 – Impressions > 5k, CTR < 0.5%   (messaging/relevance issue, Search only)
      P3 – Previously active, now dormant  (0 impressions this period)

    Returns only ad groups with at least one issue (OK ad groups are excluded to
    keep the list focused).
    """
    today = date.today()
    # Compute cutoff for last 3 months
    cutoff_month = today.month - 3
    cutoff_year  = today.year
    if cutoff_month <= 0:
        cutoff_month += 12
        cutoff_year  -= 1
    cutoff_ym  = cutoff_year * 100 + cutoff_month
    current_ym = today.year * 100 + today.month

    # Separate window rows from historical (for dormant check)
    window_rows = [r for r in adgroup_data
                   if cutoff_ym <= r["year"] * 100 + r["month"] <= current_ym]

    # Aggregate by (campaign, adgroup) over the 3-month window
    agg: dict[tuple, dict] = {}
    for r in window_rows:
        key = (r["campaign"], r["adgroup"])
        if key not in agg:
            agg[key] = {
                "campaign":      r["campaign"],
                "adgroup":       r["adgroup"],
                "campaign_type": r.get("campaign_type", "Other"),
                "region":        r.get("region", ""),
                "impressions": 0, "clicks": 0, "cost": 0.0,
            }
        agg[key]["impressions"] += r["impressions"]
        agg[key]["clicks"]      += r["clicks"]
        agg[key]["cost"]        += r["cost"]

    # Campaign-type average CPC (for the 2× threshold)
    type_totals: dict[str, dict] = {}
    for ag in agg.values():
        ct = ag["campaign_type"]
        if ct not in type_totals:
            type_totals[ct] = {"cost": 0.0, "clicks": 0}
        type_totals[ct]["cost"]   += ag["cost"]
        type_totals[ct]["clicks"] += ag["clicks"]
    avg_cpc_by_type = {
        ct: v["cost"] / v["clicks"] if v["clicks"] > 0 else 0.0
        for ct, v in type_totals.items()
    }

    # Set of (campaign, adgroup) pairs that had impressions in prior months
    prior_active = {
        (r["campaign"], r["adgroup"])
        for r in adgroup_data
        if r["year"] * 100 + r["month"] < cutoff_ym and r["impressions"] > 0
    }

    results = []
    for ag in agg.values():
        imp  = ag["impressions"]
        clk  = ag["clicks"]
        cost = ag["cost"]
        ctr  = clk / imp if imp > 0 else 0.0
        cpc  = cost / clk if clk > 0 else 0.0
        avg_cpc = avg_cpc_by_type.get(ag["campaign_type"], 0.0)
        key  = (ag["campaign"], ag["adgroup"])

        issues: list[tuple[int, str]] = []

        # P1 – Spend with no clicks
        if cost > 200 and clk == 0:
            issues.append((1, f"${cost:,.0f} spent but 0 clicks — check bid, QS, or targeting"))

        # P1 – Very low CTR on meaningful spend
        if cost > 200 and imp > 0 and ctr < 0.002:
            issues.append((1, f"CTR {ctr*100:.2f}% on ${cost:,.0f} spend — severely under-performing"))

        # P2 – CPC outlier vs type average
        if avg_cpc > 0 and clk >= 10 and cpc > 2 * avg_cpc:
            issues.append((2,
                f"CPC ${cpc:.2f} is {cpc/avg_cpc:.1f}× the {ag['campaign_type']} average "
                f"(${avg_cpc:.2f}) — review bids"))

        # P2 – High impressions, low CTR (Search)
        if imp >= 5000 and ctr < 0.005 and "Search" not in ag.get("campaign_type", ""):
            issues.append((2, f"CTR {ctr*100:.2f}% on {imp:,} impressions — messaging or relevance issue"))

        # P3 – Gone dormant
        if imp == 0 and cost == 0 and key in prior_active:
            issues.append((3, "0 impressions this period — ad group may have gone dormant"))

        if not issues:
            continue  # only flag ad groups with real problems

        priorities = [p for p, _ in issues]
        if   any(p <= 1 for p in priorities): severity = "high"
        elif any(p <= 2 for p in priorities): severity = "medium"
        else:                                  severity = "low"

        results.append({
            "campaign":      ag["campaign"],
            "adgroup":       ag["adgroup"],
            "campaign_type": ag["campaign_type"],
            "region":        ag["region"],
            "severity":      severity,
            "metrics": {
                "impressions": imp,
                "clicks":      clk,
                "cost":        round(cost, 2),
                "ctr":         round(ctr, 4),
                "cpc":         round(cpc, 2),
                "avg_cpc":     round(avg_cpc, 2),
            },
            "issues": [text for _, text in sorted(issues)],
        })

    # Sort: severity first, then cost descending within severity
    _SEV = {"high": 0, "medium": 1, "low": 2}
    results.sort(key=lambda x: (_SEV.get(x["severity"], 9), -x["metrics"]["cost"]))
    return results


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
        "--output", default="index.html",
        help="Path for generated HTML output",
    )
    args = parser.parse_args()

    print("[1/5] Connecting to Google Sheets...")
    service = get_sheets_service()

    print("[2/5] Reading sheet data...")
    gads_data = load_gads_data(service)
    campaigns_data = load_campaigns_data(service)
    monthly_summary = load_monthly_summary(service)
    adgroup_data = load_adgroup_data(service)
    search_terms = load_search_terms(service)
    is_weekly = load_is_weekly(service)
    change_events = load_change_events(service)
    campaign_ids_map = load_campaign_ids(service)
    print(f"  GadsData: {len(gads_data)} rows")
    print(f"  CampaignsData (paid PPC): {len(campaigns_data)} rows")
    print(f"  MonthlySummary: {len(monthly_summary)} periods")
    print(f"  AdGroupData (paid PPC): {len(adgroup_data)} rows")
    print(f"  SearchTermsData: {len(search_terms)} rows")
    print(f"  ImpShareWeekly: {len(is_weekly)} weeks")
    print(f"  ChangeEvents: {len(change_events)} events")

    print("[3/5] Joining and processing data...")
    campaign_rows = build_campaign_rows(gads_data, campaigns_data)
    print(f"  Merged campaign rows: {len(campaign_rows)}")

    print("[4/5] Building dashboard payload...")
    optimizations = compute_optimizations(campaign_rows, adgroup_data, campaign_ids_map)
    high   = sum(1 for o in optimizations if o["severity"] == "high")
    medium = sum(1 for o in optimizations if o["severity"] == "medium")
    print(f"  Optimizations: {len(optimizations)} campaigns "
          f"({high} high, {medium} medium priority)")

    ag_optimizations = compute_adgroup_optimizations(adgroup_data)
    ag_high   = sum(1 for o in ag_optimizations if o["severity"] == "high")
    ag_medium = sum(1 for o in ag_optimizations if o["severity"] == "medium")
    print(f"  Ad Group Issues: {len(ag_optimizations)} ad groups "
          f"({ag_high} high, {ag_medium} medium priority)")

    dashboard_data = {
        "generated_at":  date.today().isoformat(),
        "campaigns":     campaign_rows,
        "monthly_kpis":  monthly_summary,
        "adgroups":      adgroup_data,
        "search_terms":  search_terms,
        "optimizations":    optimizations,
        "ag_optimizations": ag_optimizations,
        "is_weekly":        is_weekly,
        "change_events":    change_events,
    }

    print("[5/5] Rendering HTML...")
    html = render_html(args.template, dashboard_data)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")

    print(f"\nDashboard written to: {args.output}")
    print(f"Campaign rows included: {len(campaign_rows)}")
    print(f"Monthly KPI periods: {len(monthly_summary)}")
    print(f"Ad group rows included: {len(adgroup_data)}")
    print(f"Optimization campaigns: {len(optimizations)}")


if __name__ == "__main__":
    main()
