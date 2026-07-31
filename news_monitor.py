"""
news_monitor.py — סריקת כתבות יומית בנושאי פנסיה/גמל/השתלמות
שולח כתבות חדשות לטלגרם, מונע כפולות עם news_history.json
"""

import json
import os
import sys
import hashlib
import html
import requests
from datetime import datetime, timedelta
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = Path(__file__).parent
HISTORY_FILE = BASE_DIR / "data" / "news_history.json"
MAX_HISTORY_DAYS = 30   # שומר היסטוריה 30 יום
MAX_ARTICLES_PER_RUN = 8  # מקסימום כתבות להודעה אחת

# ── Env ──────────────────────────────────────────────────────────────
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

TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
FIRECRAWL_KEY    = os.getenv("FIRECRAWL_API_KEY", "")

# ── חיפושים ──────────────────────────────────────────────────────────
QUERIES = [
    ('קרן פנסיה site:calcalist.co.il',     "calcalist.co.il"),
    ('קרן השתלמות site:calcalist.co.il',   "calcalist.co.il"),
    ('קרן פנסיה site:globes.co.il',        "globes.co.il"),
    ('גמל השתלמות site:globes.co.il',      "globes.co.il"),
    ('פנסיה השתלמות site:funder.co.il',    "funder.co.il"),
    ('קרן פנסיה site:bizportal.co.il',     "bizportal.co.il"),
    ('גמל השתלמות site:bizportal.co.il',   "bizportal.co.il"),
    ('פנסיה דמי ניהול site:ynet.co.il',    "ynet.co.il"),
    ('קרן פנסיה תשואה site:mako.co.il',    "mako.co.il"),
]

# ── Firecrawl search ─────────────────────────────────────────────────
def firecrawl_search(query: str, limit: int = 5) -> list[dict]:
    if not FIRECRAWL_KEY:
        print("⚠️  FIRECRAWL_API_KEY חסר")
        return []
    try:
        r = requests.post(
            "https://api.firecrawl.dev/v1/search",
            headers={"Authorization": f"Bearer {FIRECRAWL_KEY}"},
            json={"query": query, "limit": limit, "lang": "he", "tbs": "qdr:w"},
            timeout=20,
        )
        r.raise_for_status()
        return r.json().get("data", [])
    except Exception as e:
        print(f"  firecrawl error [{query[:30]}]: {e}")
        return []

# ── היסטוריה ─────────────────────────────────────────────────────────
def load_history() -> dict:
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}

def save_history(history: dict):
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    # נקה רשומות ישנות
    cutoff = (datetime.now() - timedelta(days=MAX_HISTORY_DAYS)).isoformat()
    history = {k: v for k, v in history.items() if v >= cutoff}
    HISTORY_FILE.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")

def article_id(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()[:12]

def already_sent(url: str, history: dict) -> bool:
    return article_id(url) in history

def mark_sent(url: str, history: dict):
    history[article_id(url)] = datetime.now().isoformat()

# ── Telegram ─────────────────────────────────────────────────────────
def send_telegram(text: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️  Telegram credentials חסרים")
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML",
                  "disable_web_page_preview": True},
            timeout=15,
        )
    except Exception as e:
        print(f"Telegram error: {e}")

# ── סינון כתבות רלוונטיות ────────────────────────────────────────────
KEYWORDS = ["פנסיה", "השתלמות", "גמל", "דמי ניהול", "תשואה", "קרן", "חיסכון"]
TAG_SEGMENTS = ["/tags/", "/tag/", "/topic/", "/Tagit/", "/list/tags", "/subjects/"]

def is_relevant(item: dict) -> bool:
    url   = item.get("url", "")
    title = item.get("title", "")
    if any(seg in url for seg in TAG_SEGMENTS):
        return False
    # סינון עמודות מחשבון/השוואה — לא כתבות
    if any(x in url for x in ["supermarker.", "mivzakon.", "calculat"]):
        return False
    return any(kw in title for kw in KEYWORDS)

# ── Main ─────────────────────────────────────────────────────────────
def main():
    print(f"News Monitor — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    history = load_history()
    new_articles = []

    for query, source in QUERIES:
        print(f"  🔍 {query[:50]}")
        results = firecrawl_search(query, limit=5)
        for item in results:
            url   = item.get("url", "")
            title = item.get("title", "").strip()
            desc  = (item.get("description") or item.get("markdown") or "")[:200].strip()

            if not url or not title:
                continue
            if not is_relevant(item):
                continue
            if already_sent(url, history):
                continue

            new_articles.append({
                "url":    url,
                "title":  title,
                "desc":   desc,
                "source": source,
            })
            mark_sent(url, history)

    # הסר כפולות (אותו URL ממקורות שונים)
    seen_urls = set()
    unique = []
    for a in new_articles:
        if a["url"] not in seen_urls:
            seen_urls.add(a["url"])
            unique.append(a)

    save_history(history)

    if not unique:
        print("✅ אין כתבות חדשות")
        return

    to_send = unique[:MAX_ARTICLES_PER_RUN]
    print(f"📨 שולח {len(to_send)} כתבות חדשות:")
    for a in to_send:
        print(f"  • {a['source']} | {a['title'][:60]}")

    date_str = datetime.now().strftime("%d/%m/%Y")
    lines = [f"📰 <b>חדשות פנסיה — {date_str}</b>", ""]

    for a in to_send:
        title = a["title"][:80]
        desc  = a["desc"][:120].replace("\n", " ").strip()
        src   = a["source"]
        url   = a["url"]

        lines.append(f'• <a href="{url}"><b>{html.escape(title)}</b></a>')
        lines.append(f'  <i>{src}</i>')
        if desc:
            lines.append(f'  {desc}')
        lines.append("")

    send_telegram("\n".join(lines))
    print(f"✅ נשלחו {len(to_send)} כתבות")


if __name__ == "__main__":
    main()
