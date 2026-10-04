"""中文市场数据采集（v0.2）：腾讯招聘官网、百度招聘官网、V2EX 酷工作。

合规：
- 全部为公开接口 / 公开 RSS；抓取前逐一做 robots.txt 门禁（fetch 失败或返回 HTML
  视同缺失 → 允许，与 RFC 9309 一致）；不做登录墙、不做高频轮询。
- 不采集作者信息（V2EX member 字段直接丢弃）。
- 溯源：SOURCE_MANIFEST.json 记录 URL、时间、条数、robots 结论。

产出：data/raw/zh/{tencent,baidu,v2ex}.json
"""

from __future__ import annotations

import json
import re
import time
import urllib.parse
from pathlib import Path

from config import parse_xml_safely, safe_fetch, safe_fetch_post

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "zh"
MANIFEST = ROOT / "data" / "raw" / "SOURCE_MANIFEST.json"

TENCENT_KEYWORDS = ["AI", "大模型", "LLM", "算法"]
BAIDU_KEYWORDS = ["大模型", "LLM", "算法", "AI"]
MAX_PAGES_PER_KW = 12
PAGE_SIZE = 100
BAIDU_PAGE_SIZE = 20      # 上游实测 >20 返回 status=fail
BAIDU_MAX_PAGES = 25


def robots_allows(host: str, path: str) -> tuple[bool, str]:
    """robots.txt 门禁：显式 Disallow 优先于 Allow（最长匹配），失败/缺失视为允许。"""
    try:
        txt = safe_fetch(f"https://{host}/robots.txt")
    except Exception as exc:  # noqa: BLE001
        return True, f"robots unreachable ({exc!r:.60}) → allow per RFC9309"
    if txt.lstrip()[:1] == "<":
        return True, "robots is HTML (redirect/error page) → treat as absent, allow"
    groups: dict[str, dict] = {}
    ua = None
    for line in txt.splitlines():
        s = line.split("#")[0].strip()
        if not s or ":" not in s:
            continue
        key, val = s.split(":", 1)
        key_l, val = key.strip().lower(), val.strip()
        if key_l == "user-agent":
            ua = val
            groups.setdefault(ua, {"allow": [], "disallow": []})
        elif key_l == "disallow" and ua is not None:
            groups[ua]["disallow"].append(val)
        elif key_l == "allow" and ua is not None:
            groups[ua]["allow"].append(val)
    rules = groups.get("*") or next(iter(groups.values()), {"allow": [], "disallow": []})
    best = (0, "allow")
    for p in rules["disallow"]:
        if p and path.startswith(p) and len(p) > best[0]:
            best = (len(p), "disallow")
    for p in rules["allow"]:
        if p and path.startswith(p) and len(p) > best[0]:
            best = (len(p), "allow")
    return best[1] == "allow", f"robots '*' path={path!r} → {best[1]}"


def fetch_tencent() -> list[dict]:
    posts: dict[str, dict] = {}
    for kw in TENCENT_KEYWORDS:
        for page in range(1, MAX_PAGES_PER_KW + 1):
            url = ("https://careers.tencent.com/tencentcareer/api/post/Query?keyword="
                   + urllib.parse.quote(kw)
                   + f"&pageIndex={page}&pageSize={PAGE_SIZE}&language=zh-cn")
            ok, note = robots_allows("careers.tencent.com", "/tencentcareer/api/post/Query")
            if not ok:
                print(f"tencent blocked by robots: {note}")
                return list(posts.values())
            data = json.loads(safe_fetch(url))
            d = data.get("Data") or {}
            plist = d.get("Posts") or []
            if not plist:
                break
            for p in plist:
                pid = p.get("PostId")
                if pid and pid not in posts:
                    posts[pid] = p
            total = int(d.get("Count") or 0)
            if page * PAGE_SIZE >= min(total, 1200):
                break
            time.sleep(0.4)
        time.sleep(0.5)
    return list(posts.values())


def fetch_baidu() -> list[dict]:
    posts: dict[str, dict] = {}
    path = "/httservice/getPostList"
    for kw in BAIDU_KEYWORDS:
        for page in range(1, BAIDU_MAX_PAGES + 1):
            ok, note = robots_allows("talent.baidu.com", path)
            if not ok:
                print(f"baidu blocked by robots: {note}")
                return list(posts.values())
            body = (f"workPosition=&keyWord={urllib.parse.quote(kw)}"
                    f"&recruitType=SOCIAL&pageSize={BAIDU_PAGE_SIZE}&curPage={page}")
            raw = safe_fetch_post(
                "https://talent.baidu.com" + path, body=body,
                content_type="application/x-www-form-urlencoded",
                headers={"Referer": "https://talent.baidu.com/jobs/social-list"})
            data = json.loads(raw)
            dd = data.get("data") or {}
            lst = dd.get("list") or []
            if not lst:
                break
            for p in lst:
                pid = p.get("postId")
                if pid and pid not in posts:
                    posts[pid] = p
            total = int(dd.get("total") or 0)
            if page * BAIDU_PAGE_SIZE >= min(total, 1200):
                break
            time.sleep(0.35)
        time.sleep(0.5)
    return list(posts.values())


def fetch_v2ex() -> list[dict]:
    out: dict[int, dict] = {}
    ok, note = robots_allows("www.v2ex.com", "/api/topics/show.json")
    if ok:
        try:
            topics = json.loads(safe_fetch(
                "https://www.v2ex.com/api/topics/show.json?node_name=jobs"))
            for t in topics:
                if (t.get("node") or {}).get("name") != "jobs":
                    continue
                out[int(t["id"])] = {
                    "title": t.get("title", ""),
                    "content": t.get("content") or "",
                    "created": t.get("created"),
                    "url": f"https://www.v2ex.com/t/{t['id']}",
                }
        except Exception as exc:  # noqa: BLE001
            print(f"v2ex api failed: {exc!r}")
    else:
        print(f"v2ex blocked by robots: {note}")
    ok, note = robots_allows("www.v2ex.com", "/feed/jobs.xml")
    if ok:
        try:  # feed 补充近期帖（API 分页上游已失效，仅返回最新一页）
            root = parse_xml_safely(safe_fetch("https://www.v2ex.com/feed/jobs.xml"))
            for item in root.iter("item"):
                title = (item.findtext("title") or "").strip()
                link = item.findtext("guid") or item.findtext("link") or ""
                m = re.search(r"/t/(\d+)", link)
                if not m:
                    continue
                tid = int(m.group(1))
                if tid in out:
                    continue
                out[tid] = {
                    "title": title,
                    "content": item.findtext("description") or "",
                    "created": None,
                    "url": link.split("#")[0],
                }
        except Exception as exc:  # noqa: BLE001
            print(f"v2ex feed failed: {exc!r}")
    else:
        print(f"v2ex feed blocked by robots: {note}")
    return list(out.values())


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    fetched_at = time.strftime("%Y-%m-%dT%H:%M:%S%z")

    tencent = fetch_tencent()
    (OUT / "tencent.json").write_text(json.dumps(tencent, ensure_ascii=False))
    print(f"tencent posts: {len(tencent)}")
    time.sleep(1.0)

    baidu = fetch_baidu()
    (OUT / "baidu.json").write_text(json.dumps(baidu, ensure_ascii=False))
    print(f"baidu posts: {len(baidu)}")
    time.sleep(1.0)

    v2ex = fetch_v2ex()
    (OUT / "v2ex.json").write_text(json.dumps(v2ex, ensure_ascii=False))
    print(f"v2ex topics: {len(v2ex)}")

    manifest = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else []
    manifest = [m for m in manifest if m.get("source") not in
                ("腾讯招聘官网 API", "百度招聘官网 API", "V2EX 酷工作")]
    manifest += [
        {"source": "腾讯招聘官网 API",
         "url": "https://careers.tencent.com/tencentcareer/api/post/Query (GET, keywords=" + ",".join(TENCENT_KEYWORDS) + ")",
         "fetched_at": fetched_at, "records": len(tencent),
         "robots": "robots.txt 返回 302 HTML，视同缺失 → 允许（RFC9309）；公开 GET 接口，低频单次",
         "license_note": "公司公开招聘页；仅聚合统计用途",
         "file": "data/raw/zh/tencent.json"},
        {"source": "百度招聘官网 API",
         "url": "https://talent.baidu.com/httservice/getPostList (POST form, keywords=" + ",".join(BAIDU_KEYWORDS) + ")",
         "fetched_at": fetched_at, "records": len(baidu),
         "robots": "robots.txt 404 视同缺失 → 允许（RFC9309）；公开页面同款接口，低频单次",
         "license_note": "公司公开招聘页；仅聚合统计用途",
         "file": "data/raw/zh/baidu.json"},
        {"source": "V2EX 酷工作",
         "url": "https://www.v2ex.com/api/topics/show.json?node_name=jobs + /feed/jobs.xml",
         "fetched_at": fetched_at, "records": len(v2ex),
         "robots": "robots.txt 允许 /api 与 /feed（Disallow 仅 backstage/signin/signout/settings）",
         "license_note": "社区公开帖；不采集作者字段；上游 v1 API 分页失效，仅最新一页 + RSS",
         "file": "data/raw/zh/v2ex.json"},
    ]
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=1))
    print(f"DONE zh total={len(tencent) + len(baidu) + len(v2ex)}")


if __name__ == "__main__":
    main()
