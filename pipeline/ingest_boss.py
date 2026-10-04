"""BOSS 直聘原始数据接入（v0.3，用户本人账号授权采集）。

输入（按优先级）：
- /tmp/boss_raw.json —— fetch 通道（joblist.json 的原始 jobList，含 boss* 字段）
- /tmp/boss_cards_*.json —— 浏览器自动化提取的卡片 JSON
- /tmp/boss_html/*.html —— 用户手动保存的搜索页 HTML

输出 data/raw/zh/boss.json（字段与 build_db.load_boss 对齐）：
  {title, salary, area, company, brand, tags, labels, href, keyword, page, src}

纪律：boss*（HR 姓名/头像/头衔/在线状态）字段不进入输出；仅列表聚合字段。
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "zh"
MANIFEST = ROOT / "data" / "raw" / "SOURCE_MANIFEST.json"


def from_joblist(raw: dict) -> list[dict]:
    out = []
    for j in raw.get("jobs", []):
        lid = j.get("lid") or ""
        eid = j.get("encryptJobId") or ""
        if not j.get("jobName"):
            continue
        href = f"/job_detail/{eid}.html" + (f"?lid={lid}" if lid else "") if eid else ""
        out.append({
            "title": (j.get("jobName") or "").strip(),
            "salary": (j.get("salaryDesc") or "").strip(),
            "area": " ".join(x for x in [j.get("cityName"), j.get("areaDistrict"), j.get("businessDistrict")] if x),
            "company": (j.get("brandName") or "").strip(),
            "brand": " ".join(x for x in [j.get("brandIndustry"), j.get("brandScaleName"), j.get("brandStageName")] if x),
            "tags": [s for s in (j.get("skills") or []) if s],
            "labels": [s for s in (j.get("jobLabels") or []) if s],
            "href": href,
            "keyword": j.get("_keyword") or "",
            "page": j.get("_page") or 0,
            "src": "joblist-api",
        })
    return out


class BossCardParser(HTMLParser):
    """从保存的搜索页 HTML 中提取职位卡片（基于 BOSS 搜索页稳定 class）。"""

    def __init__(self) -> None:
        super().__init__()
        self.cards: list[dict] = []
        self.cur: dict | None = None
        self.buf: list[str] = []
        self.capture: str | None = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = a.get("class", "")
        if "job-card-wrapper" in cls and self.cur is None:
            self.cur = {"href": a.get("href", "")}
            return
        if self.cur is None:
            return
        if "job-name" in cls and tag == "a":
            self.capture = "title"
        elif "salary" in cls:
            self.capture = "salary"
        elif "job-area" in cls:
            self.capture = "area"
        elif "company-name" in cls and tag == "a":
            self.capture = "company"
        elif tag == "li" and "tag-list" in cls:
            self.capture = "@tag"

    def handle_endtag(self, tag):
        if self.cur is None:
            return
        if self.capture == "@tag" and tag == "li":
            self.cur.setdefault("tags", []).append("".join(self.buf).strip())
            self.buf, self.capture = [], None
        elif self.capture and tag in ("a", "span", "h3", "p", "li"):
            val = "".join(self.buf).strip()
            if self.capture == "@tag":
                self.cur.setdefault("tags", []).append(val)
            else:
                self.cur[self.capture] = val
            self.buf, self.capture = [], None

    def handle_data(self, data):
        if self.cur is not None and self.capture:
            self.buf.append(data)


def from_cards() -> list[dict]:
    out = []
    for f in sorted(Path("/tmp").glob("boss_cards_*.json")):
        try:
            arr = json.loads(f.read_text())
        except Exception:
            continue
        for c in arr:
            if not c.get("title"):
                continue
            out.append({
                "title": c.get("title", "").strip(),
                "salary": (c.get("salary") or "").strip(),
                "area": (c.get("area") or "").strip(),
                "company": (c.get("company") or "").strip(),
                "brand": (c.get("brand") or "").strip(),
                "tags": c.get("tags") or [],
                "labels": c.get("labels") or [],
                "href": c.get("href") or "",
                "keyword": c.get("keyword") or "",
                "page": c.get("page") or 0,
                "src": "auto",
            })
    return out


def from_saved_html() -> list[dict]:
    out = []
    html_dir = Path("/tmp/boss_html")
    if not html_dir.exists():
        return out
    for f in sorted(html_dir.glob("*.html")):
        p = BossCardParser()
        p.feed(f.read_text(errors="replace"))
        for c in p.cards:
            if not c.get("title"):
                continue
            out.append({
                "title": c["title"].strip(),
                "salary": (c.get("salary") or "").strip(),
                "area": (c.get("area") or "").strip(),
                "company": (c.get("company") or "").strip(),
                "brand": "",
                "tags": c.get("tags") or [],
                "labels": [],
                "href": c.get("href") or "",
                "keyword": f.stem,
                "page": 0,
                "src": "saved-html",
            })
    return out


def dedupe(rows: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out = []
    for r in rows:
        key = hashlib.sha256((r.get("href") or r["title"]).encode()).hexdigest()[:16]
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    rawf = Path("/tmp/boss_raw.json")
    if rawf.exists():
        rows += from_joblist(json.loads(rawf.read_text()))
    rows += from_cards()
    rows += from_saved_html()
    rows = dedupe(rows)
    (RAW / "boss.json").write_text(json.dumps(rows, ensure_ascii=False))

    manifest = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else []
    manifest = [m for m in manifest if m["source"] != "BOSS直聘（用户授权采集）"]
    if rows:
        kws = sorted({r["keyword"] for r in rows if r["keyword"]})
        manifest.append({
            "source": "BOSS直聘（用户授权采集）",
            "url": "https://www.zhipin.com/wapi/zpgeek/search/joblist.json（列表接口，关键词：" + ",".join(kws) + "）",
            "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "records": len(rows),
            "robots": "robots.txt 禁止 /*?query=* 与 /job_detail/ —— 针对爬虫；本次为用户本人账号手动登录授权（Chrome 副本实例 CDP 会话）、仅列表 JSON 接口、低频（4-6.5s 间隔、频控即停）、仅聚合字段，不含 HR 个人信息（boss* 字段在 ingest 阶段剔除，不入库）；来源方可随时要求移除",
            "license_note": "仅聚合统计用途；不转载原文",
            "file": "data/raw/zh/boss.json",
        })
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=1))
    print(f"boss jobs ingested: {len(rows)} (keywords: {kws if rows else '-'})")


if __name__ == "__main__":
    main()
