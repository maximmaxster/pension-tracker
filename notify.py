"""
notify.py — שולח הודעת Telegram חודשית כשיש עדכון נתונים חדש
נקרא מ-fetch_data.py אחרי שמירת pension_data.json
"""

import json
import os
import requests
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent


def _load_env():
    for name in ["pension.env", ".env"]:
        p = BASE_DIR / name
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())


_load_env()

TOKEN   = os.getenv("TELEGRAM_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

CKAN_SEARCH = "https://data.gov.il/api/3/action/datastore_search"
GEMELNET_RESOURCE  = "a30dcbea-a1d2-482c-ae29-8f781f5025fb"
PENSYANET_RESOURCE = "6d47d6b5-cb08-488b-b333-f1e717b1e1bd"

HEBREW_MONTHS = {
    "01": "ינואר", "02": "פברואר", "03": "מרץ",    "04": "אפריל",
    "05": "מאי",   "06": "יוני",   "07": "יולי",   "08": "אוגוסט",
    "09": "ספטמבר","10": "אוקטובר","11": "נובמבר", "12": "דצמבר",
}

# ── קופות המשתמש ────────────────────────────────────────────────────
USER_FUNDS_ORDER = [
    "menora_pension",
    "analista_hashtalmoat",
    "ami_gemel",
    "analista_gemel",
]

FUND_LABELS = {
    "menora_pension":        "מנורה פנסיה מניות",
    "analista_hashtalmoat":  "אנליסט השתלמות",
    "ami_gemel":             "עמ\"י גמל מניות",
    "analista_gemel":        "אנליסט גמל גמיש",
}

# קטגוריות לחיפוש Top 7 (לפי FUND_CLASSIFICATION + resource)
CATEGORY_MAP = {
    "menora_pension":       ("pension", "קופות פנסיה"),
    "analista_hashtalmoat": ("gemel",   "קרנות השתלמות"),
    "ami_gemel":            ("gemel",   "קופות גמל"),
    "analista_gemel":       ("gemel",   "קופות גמל"),
}


# ── Telegram ─────────────────────────────────────────────────────────
def send(text: str):
    if not TOKEN or not CHAT_ID:
        print("⚠️  Telegram credentials חסרים")
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            data={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"},
            timeout=15,
        )
    except Exception as e:
        print(f"Telegram error: {e}")


# ── period label ─────────────────────────────────────────────────────
def period_label(p: str) -> str:
    y, m = p[:4], p[4:6]
    return f"{HEBREW_MONTHS.get(m, m)} {y}"


# ── Top 7 מאותו resource + fund_class ────────────────────────────────
def fetch_top7(resource_id: str, fund_classification: str, period: str) -> list[dict]:
    """מחזיר 7 המסלולים עם התשואה החודשית הגבוהה ביותר לתקופה נתונה."""
    try:
        params = {
            "resource_id": resource_id,
            "filters": json.dumps({"FUND_CLASSIFICATION": fund_classification,
                                   "REPORT_PERIOD": period}),
            "limit": 1000,
        }
        r = requests.get(CKAN_SEARCH, params=params, timeout=30)
        r.raise_for_status()
        records = r.json()["result"]["records"]
        # סנן רק מסלולים עם נתון חודשי
        valid = [
            rec for rec in records
            if rec.get("MONTHLY_YIELD") not in (None, "", "null")
        ]
        valid.sort(key=lambda x: float(x["MONTHLY_YIELD"]), reverse=True)
        return valid[:7]
    except Exception as e:
        print(f"fetch_top7 error: {e}")
        return []


def _fix_name(name: str) -> str:
    if not name:
        return ""
    return name.replace("S1;P500", "S&P500").replace("&amp;", "&")


# ── בניית הודעת Telegram ─────────────────────────────────────────────
def build_message(data: dict) -> str:
    funds = data.get("funds", {})

    # מצא את התקופה האחרונה
    latest_period = ""
    for fd in funds.values():
        if fd.get("periods"):
            lp = fd["periods"][-1]
            if lp > latest_period:
                latest_period = lp

    if not latest_period:
        return "⚠️ לא נמצאה תקופה בנתונים"

    plabel = period_label(latest_period)
    lines = [f"📊 <b>עדכון חודשי — {plabel}</b>", "━━━━━━━━━━━━━━━━━━━━"]

    # ── קופות המשתמש ────────────────────────────────────────────────
    for key in USER_FUNDS_ORDER:
        fd = funds.get(key)
        if not fd or fd.get("error"):
            continue
        fund_id = fd["fund_id"]
        monthly_data = fd.get("tracks_monthly", {}).get(fund_id, {})
        period_data  = monthly_data.get(latest_period, {})
        trailing     = fd.get("trailing", {}).get(fund_id, {})

        m_yield = period_data.get("monthly_yield")
        ytd     = period_data.get("ytd_yield") or trailing.get("ytd_yield")

        def fmt(v, prefix=""):
            if v is None:
                return "—"
            sign = "+" if v > 0 else ""
            return f"{prefix}{sign}{v:.1f}%"

        label = FUND_LABELS.get(key, key)
        lines.append(f"  <b>{label}</b>")
        lines.append(f"  חודש: {fmt(m_yield)}  |  YTD: {fmt(ytd)}")

    # ── Top 7 — לפי קטגוריה ראשונה (פנסיה מניות) ───────────────────
    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━")

    # pension top 7
    pension_fd = funds.get("menora_pension", {})
    if pension_fd and not pension_fd.get("error"):
        fund_class = pension_fd.get("fund_class", "")
        top7 = fetch_top7(PENSYANET_RESOURCE, fund_class, latest_period)
        if top7:
            lines.append(f"🏆 <b>Top 7 — פנסיה ({plabel})</b>")
            user_fund_id = pension_fd["fund_id"]
            user_rank = None
            for i, rec in enumerate(top7, 1):
                name  = _fix_name(rec.get("FUND_NAME", ""))[:28]
                yld   = float(rec["MONTHLY_YIELD"])
                sign  = "+" if yld > 0 else ""
                star  = " ⭐" if str(rec["FUND_ID"]) == str(user_fund_id) else ""
                if str(rec["FUND_ID"]) == str(user_fund_id):
                    user_rank = i
                lines.append(f"  {i}. {name}{star}  {sign}{yld:.1f}%")
            if user_rank:
                lines.append(f"  → המסלול שלך: מקום <b>{user_rank}</b> מתוך 7")

    # gemel השתלמות top 7
    lines.append("")
    hashtalmoat_fd = funds.get("analista_hashtalmoat", {})
    if hashtalmoat_fd and not hashtalmoat_fd.get("error"):
        fund_class = hashtalmoat_fd.get("fund_class", "")
        top7 = fetch_top7(GEMELNET_RESOURCE, fund_class, latest_period)
        if top7:
            lines.append(f"🏆 <b>Top 7 — השתלמות ({plabel})</b>")
            user_fund_id = hashtalmoat_fd["fund_id"]
            for i, rec in enumerate(top7, 1):
                name = _fix_name(rec.get("FUND_NAME", ""))[:28]
                yld  = float(rec["MONTHLY_YIELD"])
                sign = "+" if yld > 0 else ""
                star = " ⭐" if str(rec["FUND_ID"]) == str(user_fund_id) else ""
                lines.append(f"  {i}. {name}{star}  {sign}{yld:.1f}%")

    lines.append("")
    lines.append(f"🔗 <a href='https://maximmaxster.github.io/pension-tracker'>פתח אתר</a>")

    return "\n".join(lines)


# ── בדיקת תקופה חדשה ─────────────────────────────────────────────────
LAST_NOTIFIED_FILE = BASE_DIR / "data" / "last_notified_period.txt"


def already_notified(period: str) -> bool:
    if LAST_NOTIFIED_FILE.exists():
        return LAST_NOTIFIED_FILE.read_text().strip() == period
    return False


def mark_notified(period: str):
    LAST_NOTIFIED_FILE.parent.mkdir(parents=True, exist_ok=True)
    LAST_NOTIFIED_FILE.write_text(period)


# ── נקודת כניסה ─────────────────────────────────────────────────────
def notify_if_new(data_path: Path = BASE_DIR / "data" / "pension_data.json"):
    if not data_path.exists():
        print("notify: קובץ נתונים לא נמצא")
        return

    data = json.loads(data_path.read_text(encoding="utf-8"))
    funds = data.get("funds", {})

    latest_period = ""
    for fd in funds.values():
        if fd.get("periods"):
            lp = fd["periods"][-1]
            if lp > latest_period:
                latest_period = lp

    if not latest_period:
        print("notify: לא נמצאה תקופה")
        return

    if already_notified(latest_period):
        print(f"notify: תקופה {latest_period} כבר נשלחה — מדלג")
        return

    print(f"notify: תקופה חדשה {latest_period} — שולח Telegram...")
    msg = build_message(data)
    send(msg)
    mark_notified(latest_period)
    print("notify: נשלח ✅")


if __name__ == "__main__":
    notify_if_new()
