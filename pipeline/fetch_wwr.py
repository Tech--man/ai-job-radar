"""抓取 We Work Remotely 公开 RSS（多个类目）。

XML 解析走 config.parse_xml_safely（拒绝 DOCTYPE/ENTITY、限制大小）。
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from config import parse_xml_safely, safe_fetch

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "misc"
MANIFEST = ROOT / "data" / "raw" / "SOURCE_MANIFEST.json"

CATEGORIES = {
    "programming": "https://weworkremotely.com/categories/remote-programming-jobs.rss",
    "devops-sysadmin": "https://weworkremotely.com/categories/remote-devops-sysadmin-jobs.rss",
    "product": "https://weworkremotely.com/categories/remote-product-jobs.rss",
    "design": "https://weworkremotely.com/categories/remote-design-jobs.rss",
}


def parse_rss(xml_text: str) -> list[dict]:
    root = parse_xml_safely(xml_text)
    items = []
    for item in root.iter("item"):
        def t(tag: str) -> str:
            el = item.find(tag)
            return (el.text or "").strip() if el is not None else ""
        items.append({
            "title": t("title"),
            "company": t("company"),
            "url": t("url"),
            "location": t("location"),
            "category": t("category"),
            "job_type": t("job_type"),
            "published": t("pubDate"),
            "description_html": t("description"),
        })
    return items


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    fetched_at = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    counts = {}
    for cat, url in CATEGORIES.items():
        try:
            xml_text = safe_fetch(url)
            items = parse_rss(xml_text)
            (RAW / f"wwr_{cat}.xml").write_text(xml_text)
            counts[cat] = len(items)
            print(f"{cat}: {len(items)} items")
        except Exception as exc:  # noqa: BLE001
            counts[cat] = 0
            print(f"{cat}: FAILED {exc!r}")
        time.sleep(1.0)

    manifest = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else []
    manifest = [m for m in manifest if m["source"] != "WeWorkRemotely RSS"]
    for cat, url in CATEGORIES.items():
        if counts.get(cat):
            manifest.append({
                "source": "WeWorkRemotely RSS",
                "category": cat,
                "url": url,
                "fetched_at": fetched_at,
                "records": counts[cat],
                "license_note": "public RSS feed; comply with weworkremotely.com terms",
                "file": f"data/raw/misc/wwr_{cat}.xml",
            })
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=1))
    print(f"DONE wwr counts={counts}")


if __name__ == "__main__":
    main()
