"""
Shared CKAN client for data.gov.il datastore_search API.
Used by both fetch_data.py and fetch_comparison.py.
"""

import json
import time
import requests

CKAN_SEARCH = "https://data.gov.il/api/3/action/datastore_search"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

PAGE_SIZE = 1000


def ckan_search(resource_id: str, filters: dict, limit: int = PAGE_SIZE) -> list[dict]:
    """מושך נתונים מ-CKAN datastore_search עם pagination ו-retry אוטומטיים."""
    records: list[dict] = []
    offset = 0
    while True:
        params = {
            "resource_id": resource_id,
            "filters":     json.dumps(filters, ensure_ascii=False),
            "limit":       limit,
            "offset":      offset,
        }
        for attempt in range(4):
            try:
                resp = requests.get(CKAN_SEARCH, params=params,
                                    headers=HEADERS, timeout=30)
                if resp.status_code == 403:
                    wait = 15 * (attempt + 1)
                    print(f"    ⏳ 403 — ממתין {wait}ש׳ לפני ניסיון {attempt + 2}...")
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
