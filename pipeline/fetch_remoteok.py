"""抓取 RemoteOK 公开 API（https://remoteok.com/api）。

- 单次抓取全量列表；首元素为其法律声明，保留在 manifest 供溯源。
- 不抓取页面 HTML、不做高频轮询，遵守其 API 使用惯例。
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from config import safe_fetch

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "misc" / "remoteok.json"
MANIFEST = ROOT / "data" / "raw" / "SOURCE_MANIFEST.json"


def main() -> None:
    text = safe_fetch("https://remoteok.com/api")
    data = json.loads(text)
    legal = None
    jobs = data
    if data and isinstance(data[0], dict) and "legal" in data[0]:
        legal = data[0]
        jobs = data[1:]
    OUT.write_text(json.dumps(jobs, ensure_ascii=False))
    manifest = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else []
    manifest = [m for m in manifest if m["source"] != "RemoteOK API"]
    manifest.append({
        "source": "RemoteOK API",
        "url": "https://remoteok.com/api",
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "records": len(jobs),
        "license_note": (legal or {}).get("legal", "public API; comply with remoteok.com terms"),
        "file": "data/raw/misc/remoteok.json",
    })
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=1))
    print(f"DONE remoteok jobs={len(jobs)}")


if __name__ == "__main__":
    main()
