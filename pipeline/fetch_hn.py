"""抓取 Hacker News 「Ask HN: Who is hiring?」月度帖（Algolia 公开 API）。

- 明细窗口：最近 14 期，逐帖拉取完整评论树（每条顶层评论 = 一个岗位帖）。
- 趋势窗口：最近 30 期，仅记录期次与评论数。
- 不存作者字段（最小化个人数据）。
"""

from __future__ import annotations

import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from config import safe_fetch

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "hn"
API = "https://hn.algolia.com/api/v1"

DETAIL_THREADS = 14
TREND_THREADS = 30


def list_threads() -> list[dict]:
    url = f"{API}/search_by_date?" + "&".join([
        "tags=story",
        'query="Ask HN%3A Who is hiring%3F"',
        f"hitsPerPage={TREND_THREADS}",
    ])
    # Algolia query 需要对引号转义；直接用原始串
    url = f"{API}/search_by_date?tags=story&query=%22Ask%20HN%3A%20Who%20is%20hiring%3F%22&hitsPerPage={TREND_THREADS}"
    data = json.loads(safe_fetch(url))
    threads = []
    for hit in data.get("hits", []):
        title = hit.get("title", "")
        if not title.lower().startswith("ask hn: who is hiring"):
            continue
        threads.append({
            "id": hit["objectID"],
            "title": title,
            "created_at": hit.get("created_at", ""),
            "n_comments": hit.get("num_comments", 0),
            "points": hit.get("points", 0),
        })
    threads.sort(key=lambda t: t["created_at"], reverse=True)
    return threads


def fetch_thread(tid: str) -> dict:
    data = json.loads(safe_fetch(f"{API}/items/{tid}"))
    return {"id": tid, "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "tree": data}


def extract_top_comments(tree: dict) -> list[dict]:
    """取 parent_id == story id 的顶层评论。"""
    sid = tree.get("id")
    out = []
    def walk(node):
        for child in node.get("children", []) or []:
            if child.get("type") == "comment" and child.get("parent_id") == sid:
                out.append({
                    "objectID": child.get("id"),
                    "created_at": child.get("created_at"),
                    "text": child.get("text") or "",
                    # 忽略 author 字段，最小化个人数据
                })
    walk(tree)
    return out


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    threads = list_threads()
    if len(threads) < 3:
        print("FATAL: threads found =", len(threads))
        sys.exit(1)
    (RAW / "threads_index.json").write_text(json.dumps(threads, ensure_ascii=False, indent=1))
    print(f"threads listed: {len(threads)} (detail on top {DETAIL_THREADS})")

    detail = threads[:DETAIL_THREADS]
    results, errors = {}, []
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(fetch_thread, t["id"]): t["id"] for t in detail}
        for fut in as_completed(futs):
            tid = futs[fut]
            try:
                results[tid] = fut.result()
            except Exception as exc:  # noqa: BLE001
                errors.append({"thread": tid, "error": repr(exc)})
    for tid, payload in results.items():
        top = extract_top_comments(payload["tree"])
        slim = {"id": tid, "fetched_at": payload["fetched_at"], "comments": top}
        (RAW / f"thread_{tid}.json").write_text(json.dumps(slim, ensure_ascii=False))
        payload["comments"] = len(top)
        print(f"thread {tid}: {len(top)} top-level comments")
    (RAW / "fetch_errors.json").write_text(json.dumps(errors, ensure_ascii=False, indent=1))
    total = sum(payload.get("comments", 0) for payload in results.values())
    print(f"DONE detail_threads={len(results)} failed={len(errors)} total_top_comments={total}")


if __name__ == "__main__":
    main()
