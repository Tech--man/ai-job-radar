"""BOSS 直聘原始数据接入（v0.3，用户本人账号授权采集）。

两种来源，统一为 data/raw/zh/boss.json：
- A. 浏览器自动化提取的卡片 JSON（/tmp/boss_*.json，字段见 ingest 函数）
- B. 用户手动保存的搜索页 HTML（/tmp/boss_html/*.html，解析 job-card-wrapper）

纪律：
- 不存招聘者（HR）姓名/头像等个人信息；仅聚合统计所需的岗位字段。
- SOURCE_MANIFEST 如实记录：robots 禁止 ?query= 与详情页，本次为用户本人授权、
  低频（SPA 内翻页 + 4s+ 间隔）、仅首页列表数据；来源方可随时要求移除。
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

CARD_TEXT_SPLIT = re.compile(r"\s*[·|]\s*")


class BossCardParser(HTMLParser):
    """从保存的搜索页 HTML 中提取职位卡片（基于 BOSS 搜索页稳定 class）。"""

    def __init__(self) -> None:
        super().__init__()
        self.cards: list[dict] = []
        self.cur: dict | None = None
        self.buf: list[str] = []
        self.capture: str | None = None  # 当前捕获字段
        self.depth_in_card = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = a.get("class", "")
        if "job-card-wrapper" in cls or ("job-card-left" in cls and self.cur is None):
            if "job-card-wrapper" in cls:
                self.cur = {"href": a.get("href", "")}
                self.depth_in_card = 1
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
        elif "tag-list" in cls and tag == "li":
            self.capture = "@tag"
        elif "job-info" in cls and "filter-labels" in cls:
            pass

    def handle_endtag(self, tag):
        if self.cur is None:
            return
        if self.capture == "@tag" and tag == "li":
            self.cur.setdefault("tags", []).append("".join(self.buf).strip())
            self.buf, self.capture = [], None
        elif self.capture and tag in ("a", "span", "h3", "p", "li"):
            key = self.capture if self.capture != "@tag" else "tags"
            val = "".join(self.buf).strip()
            if key == "tags":
                self.cur.setdefault("tags", []).append(val)
            else:
                self.cur[key] = val
            self.buf, self.capture = [], None

    def handle_data(self, data):
        if self.cur is not None and self.capture:
            self.buf.append(data)


def strip_hr_info(card: dict) -> dict:
    """去个人信息：丢弃 job-card-footer（含 HR 姓名/头像/在线状态）。"""
    return {k: v for k, v in card.items()
            if k not in ("boss_name", "boss_title", "brand_avatar", "hr")}


def parse_salary_text(s: str) -> str:
    return (s or "").strip()


def ingest() -> int:
    RAW.mkdir(parents=True, exist_ok=True)
    jobs: dict[str, dict] = {}

    # 来源 A：自动化提取的卡片 JSON
    for f in sorted(Path("/tmp").glob("boss_cards_*.json")):
        try:
            arr = json.loads(f.read_text())
        except Exception:
            continue
        for c in arr:
            jid = c.get("lid") or c.get("href") or ""
            if not jid:
                continue
            key = hashlib.sha256(str(jid).encode()).hexdigest()[:16]
            jobs[key] = {
                "title": (c.get("title") or "").strip(),
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
            }

    # 来源 B：用户手动保存的 HTML
    html_dir = Path("/tmp/boss_html")
    if html_dir.exists():
        for f in sorted(html_dir.glob("*.html")):
            p = BossCardParser()
            p.feed(f.read_text(errors="replace"))
            for c in p.cards:
                c = strip_hr_info(c)
                if not c.get("title"):
                    continue
                key = hashlib.sha256((c.get("href") or c["title"]).encode()).hexdigest()[:16]
                jobs[key] = {
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
                }

    out = list(jobs.values())
    (RAW / "boss.json").write_text(json.dumps(out, ensure_ascii=False))
    manifest = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else []
    manifest = [m for m in manifest if m["source"] != "BOSS直聘（用户授权采集）"]
    if out:
        manifest.append({
            "source": "BOSS直聘（用户授权采集）",
            "url": "https://www.zhipin.com/web/geek/job?query=<关键词>（列表页）",
            "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "records": len(out),
            "robots": "robots.txt 禁止 /*?query=* 与 /job_detail/ —— 针对爬虫；本次为用户本人账号手动登录授权、SPA 内低频翻页、仅列表聚合字段，不含 HR 个人信息；来源方可随时要求移除",
            "license_note": "仅聚合统计用途；不转载原文",
            "file": "data/raw/zh/boss.json",
        })
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=1))
    print(f"boss jobs ingested: {len(out)} (auto+saved-html)")
    return len(out)


if __name__ == "__main__":
    ingest()
