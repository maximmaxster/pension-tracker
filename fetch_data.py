"""
Pension Tracker — fetch_data.py
מושך נתוני תשואות מ-data.gov.il CKAN API (גמל נט + פנסיה נט)
מריץ יומי דרך Task Scheduler ומעדכן pension_data.json
"""

import json
import sys
import requests
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ── קוד הקופות שלך ──────────────────────────────────────────────
USER_FUNDS = {
    "menora_pension": {
        "fund_id": "2063",
        "name": "מנורה מבטחים פנסיה מניות",
        "type": "pension",
        "label": "פנסיה — מנורה מבטחים",
        "visible_tracks": ["13887", "2009", "2063", "2183", "13350", "14278"],
        # מסלולים: S&P500 / כללי / מניות / יעד 2050 / עוקב מדדי מניות / גמיש
    },
    "analista_hashtalmoat": {
        "fund_id": "963",
        "name": "אנליסט השתלמות מניות",
        "type": "gemel",
        "label": "קרן השתלמות — אנליסט",
        "visible_tracks": ["962", "963", "13853", "15311", "15312"],  # כללי / מניות / S&P500 / מסלולית גמיש / מסלולית מניות
    },
    "ami_gemel": {
        "fund_id": "14079",
        "name": "עמ\"י קופת גמל להשקעה מסלול מניות",
        "type": "gemel",
        "label": "קופת גמל — עמ\"י",
    },
    "analista_gemel": {
        "fund_id": "7843",
        "name": "אנליסט גמל להשקעה עוקב מדדים גמיש",
        "type": "gemel",
        "label": "גמל להשקעה — אנליסט",
        "visible_tracks": ["7843", "7836", "7834"],
        # מסלולים: עוקב מדדים גמיש / מניות / כללי
    },
}

# ── CKAN resource IDs ────────────────────────────────────────────
GEMELNET_RESOURCE  = "a30dcbea-a1d2-482c-ae29-8f781f5025fb"
PENSYANET_RESOURCE = "6d47d6b5-cb08-488b-b333-f1e717b1e1bd"

# משאבים היסטוריים לחישוב 10Y (לפי סדר כרונולוגי)
GEMELNET_HIST  = ["91c849ed-ddc4-472b-bd09-0f5486cea35c",   # 1999–2022
                  "2016d770-f094-4a2e-983e-797c26479720"]   # 2023
PENSYANET_HIST = ["a66926f3-e396-4984-a4db-75486751c2f7",   # 1999–2022
                  "4694d5a7-5284-4f3d-a2cb-5887f43fb55e"]   # 2023

CKAN_SEARCH = "https://data.gov.il/api/3/action/datastore_search"

OUTPUT_FILE = Path(__file__).parent / "data" / "pension_data.json"

CURRENT_YEAR = datetime.now().year
START_PERIOD = f"{CURRENT_YEAR}01"   # 202601


PAGE_SIZE = 1000  # CKAN max per request


def ckan_search(resource_id: str, filters: dict, limit: int = PAGE_SIZE) -> list[dict]:
    """מושך נתונים מ-CKAN datastore_search עם pagination אוטומטי."""
    records = []
    offset = 0
    while True:
        params = {
            "resource_id": resource_id,
            "filters":     json.dumps(filters, ensure_ascii=False),
            "limit":       limit,
            "offset":      offset,
        }
        resp = requests.get(CKAN_SEARCH, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success"):
            raise RuntimeError(f"CKAN error: {data.get('error')}")
        batch = data["result"]["records"]
        records.extend(batch)
        if len(batch) < limit:
            break
        offset += limit
    return records


def get_managing_corp(resource_id: str, fund_id: str) -> tuple[str, str]:
    """מחזיר (MANAGING_CORPORATION, FUND_CLASSIFICATION) לקוד קופה נתון."""
    rows = ckan_search(resource_id, {"FUND_ID": fund_id}, limit=1)
    if not rows:
        raise ValueError(f"Fund {fund_id} not found in resource {resource_id}")
    r = rows[0]
    return r["MANAGING_CORPORATION"], r.get("FUND_CLASSIFICATION", "")


def fetch_all_tracks(resource_id: str, managing_corp: str, fund_classification: str) -> list[dict]:
    """מושך כל המסלולים של אותה חברה מנהלת + קטגוריה (כל הזמנים)."""
    return ckan_search(resource_id, {
        "MANAGING_CORPORATION": managing_corp,
        "FUND_CLASSIFICATION":  fund_classification,
    })


def fetch_historical_monthly(hist_resources: list[str],
                             managing_corp: str,
                             fund_classification: str,
                             since_period: str) -> dict[str, dict]:
    """מושך תשואות חודשיות היסטוריות לחישוב 10Y.
    מחזיר: fund_id → period → {"monthly_yield": float}
    """
    result: dict[str, dict] = {}
    for res_id in hist_resources:
        rows = ckan_search(res_id, {
            "MANAGING_CORPORATION": managing_corp,
            "FUND_CLASSIFICATION":  fund_classification,
        })
        for row in rows:
            period = str(row.get("REPORT_PERIOD", ""))
            if period < since_period:
                continue
            fid = str(row["FUND_ID"])
            if fid not in result:
                result[fid] = {}
            result[fid][period] = {"monthly_yield": _pct(row.get("MONTHLY_YIELD"))}
    return result


def build_fund_data(user_fund: dict) -> dict:
    """בונה מבנה נתונים מלא לקופה אחת."""
    fund_id     = user_fund["fund_id"]
    resource_id = PENSYANET_RESOURCE if user_fund["type"] == "pension" else GEMELNET_RESOURCE

    print(f"  ► מושך {user_fund['label']} (קוד {fund_id})...")

    # מאתר MANAGING_CORPORATION + FUND_CLASSIFICATION
    managing_corp, fund_class = get_managing_corp(resource_id, fund_id)
    print(f"    חברה מנהלת: {managing_corp} | סוג: {fund_class}")

    # קובע משאבים היסטוריים לפי סוג
    hist_resources = PENSYANET_HIST if user_fund["type"] == "pension" else GEMELNET_HIST

    # מחשב תחילת 10 שנים (120 חודשים אחורה)
    now = datetime.now()
    y10_m = now.month - 120 % 12
    y10_y = now.year - 10 + (0 if y10_m > 0 else -1)
    y10_m = y10_m if y10_m > 0 else y10_m + 12
    since_period = f"{y10_y}{y10_m:02d}"
    print(f"    מושך היסטוריה מ-{since_period} ל-10Y...")
    hist_monthly = fetch_historical_monthly(hist_resources, managing_corp, fund_class, since_period)

    # כל המסלולים — כל הזמנים
    all_rows = fetch_all_tracks(resource_id, managing_corp, fund_class)

    # אינדקס לפי fund_id → period → data
    tracks_monthly: dict[str, dict] = {}
    tracks_meta: dict[str, str] = {}
    latest_row_per_fund: dict[str, dict] = {}  # לחישוב trailing

    for row in all_rows:
        fid    = str(row["FUND_ID"])
        fname  = _fix_name(row["FUND_NAME"])
        period = str(row["REPORT_PERIOD"])
        tracks_meta[fid] = fname
        if fid not in tracks_monthly:
            tracks_monthly[fid] = {}
        tracks_monthly[fid][period] = {
            "monthly_yield":  _pct(row.get("MONTHLY_YIELD")),
            "ytd_yield":      _pct(row.get("YEAR_TO_DATE_YIELD")),
            "total_assets":   row.get("TOTAL_ASSETS"),
            "management_fee": row.get("AVG_ANNUAL_MANAGEMENT_FEE"),
        }
        # שמור שורה אחרונה לכל מסלול (לפי REPORT_PERIOD)
        if fid not in latest_row_per_fund or period > str(latest_row_per_fund[fid]["REPORT_PERIOD"]):
            latest_row_per_fund[fid] = row

    # מיזוג נתוני היסטוריה לתוך tracks_monthly (לחישוב 10Y בלבד)
    combined_monthly: dict[str, dict] = {}
    for fid in tracks_meta:
        combined_monthly[fid] = {**hist_monthly.get(fid, {}), **tracks_monthly.get(fid, {})}

    # נתוני trailing — מהשורה האחרונה של כל מסלול
    trailing: dict[str, dict] = {}
    for fid, row in latest_row_per_fund.items():
        trailing[fid] = {
            "period":          str(row["REPORT_PERIOD"]),
            "ytd_yield":       _pct(row.get("YEAR_TO_DATE_YIELD")),
            "trailing_3yr":    _pct(row.get("YIELD_TRAILING_3_YRS")),
            "trailing_5yr":    _pct(row.get("YIELD_TRAILING_5_YRS")),
            "trailing_10yr":   _calc_10yr(combined_monthly.get(fid, {})),
            "avg_annual_3yr":  _pct(row.get("AVG_ANNUAL_YIELD_TRAILING_3YRS")),
            "avg_annual_5yr":  _pct(row.get("AVG_ANNUAL_YIELD_TRAILING_5YRS")),
            "sharpe_ratio":    row.get("SHARPE_RATIO"),
            "management_fee":  row.get("AVG_ANNUAL_MANAGEMENT_FEE"),
            "stock_exposure":  _stock_pct(row.get("STOCK_MARKET_EXPOSURE"), row.get("TOTAL_ASSETS")),
        }

    # רשימת התקופות הקיימות (ממוינות)
    all_periods = sorted({p for m in tracks_monthly.values() for p in m.keys()})

    visible = user_fund.get("visible_tracks")
    print(f"    מסלולים: {len(tracks_meta)} | תקופות: {len(all_periods)}" +
          (f" | מוצגים: {len(visible)}" if visible else ""))

    return {
        "fund_id":        fund_id,
        "label":          user_fund["label"],
        "managing_corp":  managing_corp,
        "fund_class":     fund_class,
        "periods":        all_periods,
        "tracks_meta":    tracks_meta,
        "tracks_monthly": tracks_monthly,
        "trailing":       trailing,
        "visible_tracks": visible,          # None = הצג הכל
    }


def _calc_10yr(monthly_data: dict) -> float | None:
    """מחשב תשואה מצטברת ל-10 שנים מתוך נתוני תשואה חודשית (MONTHLY_YIELD)."""
    if not monthly_data:
        return None
    periods = sorted(monthly_data.keys())
    latest = periods[-1]
    # תאריך התחלה = 120 חודשים אחורה
    y, m = int(latest[:4]), int(latest[4:])
    start_m = m - 120
    start_y = y + start_m // 12
    start_m = start_m % 12
    if start_m <= 0:
        start_m += 12
        start_y -= 1
    start_period = f"{start_y}{start_m:02d}"
    # סנן רק תקופות בין start_period ל-latest
    relevant = {p: monthly_data[p] for p in periods if start_period <= p <= latest}
    if len(relevant) < 60:      # פחות מ-5 שנים — אין מספיק היסטוריה
        return None
    # מכפלת (1 + r_monthly/100) לכל חודש
    cumulative = 1.0
    for d in relevant.values():
        r = d.get("monthly_yield")
        if r is None:
            return None
        cumulative *= (1 + r / 100)
    return round((cumulative - 1) * 100, 2)


def _stock_pct(exposure, total_assets) -> float | None:
    """מחשב אחוז חשיפה למניות: STOCK_MARKET_EXPOSURE / TOTAL_ASSETS * 100."""
    try:
        e = float(exposure)
        t = float(total_assets)
        if t > 0:
            return round(e / t * 100, 1)
    except (TypeError, ValueError, ZeroDivisionError):
        pass
    return None


def _fix_name(name: str | None) -> str:
    """מתקן ארטיפקטים של אנקודינג בשמות קופות מה-CKAN (S1;P500 → S&P500)."""
    if not name:
        return name or ""
    return name.replace("S1;P500", "S&P500").replace("&amp;", "&")


def _pct(val) -> float | None:
    """ממיר ערך לאחוזים (float), מחזיר None אם חסר."""
    if val is None or val == "" or val == "null":
        return None
    try:
        return round(float(val), 2)
    except (ValueError, TypeError):
        return None


def fetch_last_modified(resource_id: str) -> str:
    """בודק מתי עודכן המשאב לאחרונה."""
    url = f"https://data.gov.il/api/3/action/resource_show?id={resource_id}"
    r = requests.get(url, timeout=15).json()
    return r["result"].get("last_modified", "")


def main():
    print(f"Pension Tracker — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("="*55)

    output = {
        "fetched_at": datetime.now().isoformat(),
        "gemelnet_last_modified":  fetch_last_modified(GEMELNET_RESOURCE),
        "pensyanet_last_modified": fetch_last_modified(PENSYANET_RESOURCE),
        "funds": {},
    }

    for key, user_fund in USER_FUNDS.items():
        try:
            output["funds"][key] = build_fund_data(user_fund)
        except Exception as e:
            print(f"  ✗ שגיאה ב-{user_fund['label']}: {e}")
            output["funds"][key] = {"error": str(e), "label": user_fund["label"]}

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✅ נשמר: {OUTPUT_FILE}")

    # הצגת תקופה אחרונה
    for key, fund_data in output["funds"].items():
        if "periods" in fund_data:
            last = fund_data["periods"][-1] if fund_data["periods"] else "—"
            print(f"  {fund_data['label']}: תקופה אחרונה = {last}")

    # ── דחיפה ל-GitHub (מעדכן את האתר אוטומטית) ────────────────
    git_push()


def git_push():
    """מבצע git add + commit + push כדי לעדכן את GitHub Pages."""
    import subprocess
    repo_dir = Path(__file__).parent
    date_str = datetime.now().strftime("%d/%m/%Y %H:%M")

    cmds = [
        ["git", "-C", str(repo_dir), "add", "data/pension_data.json"],
        ["git", "-C", str(repo_dir), "commit", "-m", f"sync: עדכון נתונים — {date_str}"],
        ["git", "-C", str(repo_dir), "push"],
    ]
    for cmd in cmds:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0 and "nothing to commit" not in result.stdout + result.stderr:
            print(f"  git: {' '.join(cmd[3:])} — {result.stderr.strip() or result.stdout.strip()}")
        else:
            print(f"  git: {' '.join(cmd[3:])} — OK")


if __name__ == "__main__":
    main()
