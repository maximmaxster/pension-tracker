"""
Pension Tracker — fetch_comparison.py
מושך נתוני השוואה לכל החברות מאותה קטגוריה מ-data.gov.il
מריץ פעם אחת ביום (אחרי fetch_data.py)
"""

import json
import re
import sys
import time
import requests
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

GEMELNET_RESOURCE  = "a30dcbea-a1d2-482c-ae29-8f781f5025fb"
PENSYANET_RESOURCE = "6d47d6b5-cb08-488b-b333-f1e717b1e1bd"

CKAN_SEARCH = "https://data.gov.il/api/3/action/datastore_search"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

DATA_DIR    = Path(__file__).parent / "data"
OUTPUT_FILE = DATA_DIR / "comparison_data.json"
MAIN_DATA   = DATA_DIR / "pension_data.json"

# ── קטגוריות מסלול — מיפוי לפי מילות מפתח ──────────────────────
CATEGORIES = [
    ("sp500",     re.compile(r"s&?p\s*500|sp500",                    re.I)),
    ("stocks",    re.compile(r"מניות|מנייתי|equity",                  re.I)),
    ("general",   re.compile(r"כלל[יי]",                              re.I)),
    ("index",     re.compile(r"עוקב.?מד[די]|index",                  re.I)),
    ("flexible",  re.compile(r"גמיש|flexible",                        re.I)),
    ("bonds",     re.compile(r"שמרני|אג\"?ח|סולידי|bond",            re.I)),
    ("world",     re.compile(r"עולמי|world|global",                   re.I)),
    ("lifecycle", re.compile(r"לבני\s*\d|גילאי\s*\d|לגיל\s*\d",     re.I)),
]

CATEGORY_LABELS = {
    "sp500":     "S&P 500",
    "stocks":    "מסלול מניות",
    "general":   "מסלול כללי",
    "index":     "עוקב מדדים",
    "flexible":  "מסלול גמיש",
    "bonds":     "מסלול שמרני / אג\"ח",
    "world":     "מסלול עולמי",
    "lifecycle": "מסלול גיל חיים",
    "other":     "אחר",
}


def classify_track(name: str) -> str:
    for cat, pattern in CATEGORIES:
        if pattern.search(name):
            return cat
    return "other"


def ckan_fetch(resource_id: str, filters: dict, limit: int = 1000) -> list[dict]:
    records, offset = [], 0
    while True:
        params = {
            "resource_id": resource_id,
            "filters": json.dumps(filters, ensure_ascii=False),
            "limit": limit,
            "offset": offset,
        }
        for attempt in range(4):
            try:
                resp = requests.get(CKAN_SEARCH, params=params,
                                    headers=HEADERS, timeout=30)
                if resp.status_code == 403:
                    wait = 15 * (attempt + 1)
                    print(f"  ⏳ 403 — ממתין {wait}ש׳...")
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                break
            except requests.exceptions.RequestException:
                if attempt == 3:
                    raise
                time.sleep(10 * (attempt + 1))
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


def _pct(val) -> float | None:
    if val is None or val == "":
        return None
    try:
        return round(float(val), 2)
    except (TypeError, ValueError):
        return None


def fetch_fund_class_comparison(resource_id: str, fund_class: str,
                                 latest_period: str) -> dict:
    """מושך את כל המסלולים של כל החברות מאותה קטגוריה בפריודה האחרונה."""
    print(f"  שואל: {fund_class} | פריודה: {latest_period}")

    rows = ckan_fetch(resource_id, {
        "FUND_CLASSIFICATION": fund_class,
        "REPORT_PERIOD": int(latest_period),
    })
    print(f"    קיבלנו {len(rows)} שורות")

    # קיבוץ לפי קטגוריה
    categories: dict[str, list] = {}
    for row in rows:
        name  = str(row.get("FUND_NAME", ""))
        corp  = str(row.get("MANAGING_CORPORATION", ""))
        fid   = str(row.get("FUND_ID", ""))
        cat   = classify_track(name)

        entry = {
            "fund_id":       fid,
            "name":          name,
            "corp":          corp,
            "ytd":           _pct(row.get("YEAR_TO_DATE_YIELD")),
            "trailing_3yr":  _pct(row.get("YIELD_TRAILING_3_YRS")),
            "trailing_5yr":  _pct(row.get("YIELD_TRAILING_5_YRS")),
            "avg_ann_3yr":   _pct(row.get("AVG_ANNUAL_YIELD_TRAILING_3YRS")),
            "avg_ann_5yr":   _pct(row.get("AVG_ANNUAL_YIELD_TRAILING_5YRS")),
            "mgmt_fee":      _pct(row.get("AVG_ANNUAL_MANAGEMENT_FEE")),
            "total_assets":  row.get("TOTAL_ASSETS"),
        }
        categories.setdefault(cat, []).append(entry)

    # מיון כל קטגוריה לפי YTD (הגבוה ראשון), null בסוף
    for cat in categories:
        categories[cat].sort(
            key=lambda x: (x["ytd"] is None, -(x["ytd"] or 0))
        )

    return categories


def main():
    print(f"\nComparison Fetch — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 55)

    # קרא נתוני משתמש קיימים כדי לדעת אילו fund_class ופריודות יש
    with open(MAIN_DATA, encoding="utf-8") as f:
        main_data = json.load(f)

    # מיפוי fund_class → resource_id (לפי סוג הקרן)
    CLASS_RESOURCE = {
        "קרנות חדשות":      PENSYANET_RESOURCE,
        "קרנות השתלמות":    GEMELNET_RESOURCE,
        "קופת גמל להשקעה":  GEMELNET_RESOURCE,
    }

    # צור מיפוי: (resource_id, fund_class) → latest_period
    fund_class_map: dict[tuple, str] = {}
    for key, fd in main_data["funds"].items():
        if fd.get("error"):
            continue
        fund_class = fd.get("fund_class", "")
        res_id     = CLASS_RESOURCE.get(fund_class, GEMELNET_RESOURCE)
        latest     = max(fd.get("periods", ["202601"]))
        fund_class_map[(res_id, fund_class)] = latest

    output = {
        "fetched_at": datetime.now().isoformat(),
        "period":     "",
        "by_class":   {},
    }

    all_periods = []
    for (res_id, fund_class), latest_period in fund_class_map.items():
        all_periods.append(latest_period)
        key = f"{res_id}|{fund_class}"
        try:
            categories = fetch_fund_class_comparison(res_id, fund_class, latest_period)
            output["by_class"][fund_class] = {
                "fund_class":   fund_class,
                "period":       latest_period,
                "categories":   categories,
            }
        except Exception as e:
            print(f"  ❌ שגיאה ב-{fund_class}: {e}")
            output["by_class"][fund_class] = {"error": str(e)}

        time.sleep(5)  # נימוס ל-API

    output["period"] = max(all_periods) if all_periods else ""

    # שמור
    DATA_DIR.mkdir(exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n✅ נשמר: {OUTPUT_FILE}")

    # גיט
    import subprocess
    subprocess.run(["git", "add", "data/comparison_data.json"],
                   cwd=Path(__file__).parent, capture_output=True)
    r = subprocess.run(
        ["git", "commit", "-m",
         f"sync: comparison data — {datetime.now().strftime('%d/%m/%Y %H:%M')}"],
        cwd=Path(__file__).parent, capture_output=True, text=True, encoding="utf-8"
    )
    if "nothing to commit" not in r.stdout:
        subprocess.run(["git", "push", "origin", "main"],
                       cwd=Path(__file__).parent, capture_output=True)
        print("  git: push — OK")


if __name__ == "__main__":
    main()
