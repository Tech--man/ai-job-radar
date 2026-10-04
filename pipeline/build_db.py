"""清洗与结构化：原始抓取 → 结构化岗位表（SQLite + processed JSON）。

流程：HTML 清洗 → 公司/职位/地点提取 → 薪资解析（不可解析即置空，绝不推测）
→ 技能抽取（正则字典）→ 岗位分类（标题+正文关键词，带 AI 门槛）→ 去重 → 入库。

SQL 纪律：全部语句为字面量常量，一律命名占位符（:field）+ 参数字典绑定，
不拼接、不 format、不 f-string 任何外部输入。
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import sqlite3
import time
import unicodedata
from pathlib import Path

from config import FX_TO_USD, SALARY_MAX_USD, SALARY_MIN_USD, parse_xml_safely
from roles_dict import AI_GATE, AI_GATE_RAW, AI_GATE_ZH, ROLES
from skills_dict import SKILLS
from sql_statements import (DELETE_JOBS, DELETE_META, DDL_IDX_AI, DDL_IDX_MONTH, DDL_IDX_ROLE,
                            DDL_JOBS, DDL_META, FIELDS, INSERT_SQL, META_INSERT)

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
DB_PATH = ROOT / "data" / "ai_jobs.sqlite"
PROCESSED = ROOT / "data" / "processed"

# ---------------- 文本清洗 ----------------

TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"[ \t\f\v]+")
CJK_RANGE = ("\u4e00", "\u9fff")


def has_cjk(s: str) -> bool:
    return any(CJK_RANGE[0] <= ch <= CJK_RANGE[1] for ch in s)


def cjk_ratio(s: str) -> float:
    if not s:
        return 0.0
    cjk = sum(1 for ch in s if CJK_RANGE[0] <= ch <= CJK_RANGE[1])
    return cjk / max(1, len(s))


def detect_lang(text: str) -> str:
    return "zh" if cjk_ratio(text) > 0.15 else "en"


def html_to_text(raw: str) -> str:
    txt = raw or ""
    txt = re.sub(r"(?is)<(script|style).*?</\1>", " ", txt)
    txt = re.sub(r"(?i)<br\s*/?>|</p>|</li>|</div>|</tr>", "\n", txt)
    txt = TAG_RE.sub(" ", txt)
    txt = html.unescape(txt)
    txt = unicodedata.normalize("NFKC", txt)
    lines = [WS_RE.sub(" ", ln).strip() for ln in txt.splitlines()]
    return "\n".join(ln for ln in lines if ln).strip()


def smart_truncate(text: str, limit: int = 6000) -> str:
    return text if len(text) <= limit else text[:limit] + " …[truncated]"


# ---------------- 薪资解析 ----------------

CURRENCY_SYMBOLS = {"$": "USD", "€": "EUR", "£": "GBP", "¥": "CNY", "￥": "CNY"}
CURRENCY_WORDS = {
    "usd": "USD", "eur": "EUR", "gbp": "GBP", "cad": "CAD", "aud": "AUD",
    "nzd": "NZD", "chf": "CHF", "sek": "SEK", "nok": "NOK", "dkk": "DKK",
    "sgd": "SGD", "jpy": "JPY", "inr": "INR", "cny": "CNY", "rmb": "CNY",
    "brl": "BRL", "pln": "PLN", "czk": "CZK",
}

MONEY_RE = re.compile(
    r"(?P<cur>[$€£¥￥]|\b(?:USD|EUR|GBP|CAD|AUD|NZD|CHF|SEK|NOK|DKK|SGD|JPY|INR|CNY|RMB)\b|人民币)?"
    r"\s?(?P<amt>\d{1,3}(?:[,.]\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"\s?(?P<suffix>[kKmMwW]|万)?"
)

PERIOD_PATTERNS = [
    (re.compile(r"\b(?:/|per\s+|a\s+)?hr\b|\bhourly\b|\bper\s+hour\b|\ban\s+hour\b|时薪|/小时|/时", re.I), "hourly"),
    (re.compile(r"\b(?:/|per\s+|a\s+)?day\b|\bdaily\b|日薪|/天|/日", re.I), "daily"),
    (re.compile(r"\b(?:/|per\s+|a\s+)?mo\b|\bmonthly\b|\bper\s+month\b|\ba\s+month\b|月薪|/月", re.I), "monthly"),
    (re.compile(r"\b(?:/|per\s+|a\s+)?yr\b|\bannual(?:ly)?\b|\bper\s+(?:year|annum)\b|\bsalary\b|\bcomp(?:ensation)?\b|年薪|/年|薪资|薪酬|待遇", re.I), "annual"),
]
RANGE_SEP_RE = re.compile(r"\s*(?:-|–|—|to|到|～|~)\s*")

SUFFIX_MULT = {"k": 1e3, "K": 1e3, "m": 1e6, "M": 1e6, "w": 1e4, "W": 1e4, "万": 1e4}


def _decode_amount(amt: str) -> float | None:
    if re.fullmatch(r"\d{1,3}(?:[,.]\d{3})+(?:\.\d+)?", amt):
        return float(amt.replace(",", ""))
    return float(amt)


def _annualize(value: float, period: str) -> float | None:
    if period == "hourly":
        return value * 1750  # 假设年 1750 计薪小时（方法论已记录）
    if period == "daily":
        return value * 220
    if period == "monthly":
        return value * 12
    return value


def _period_near(text: str, pos: int, window: int = 45) -> str | None:
    lo, hi = max(0, pos - window), min(len(text), pos + window)
    seg = text[lo:hi]
    for pat, name in PERIOD_PATTERNS:
        if pat.search(seg):
            return name
    return None


CURRENCY_NEAR_RE = re.compile(
    r"[$€£¥￥]|\b(?:USD|EUR|GBP|CAD|AUD|NZD|CHF|SEK|NOK|DKK|SGD|JPY|INR|CNY|RMB)\b|人民币|元",
    re.I)


def _currency_near(text: str, pos: int, window: int = 60) -> str | None:
    """在金额附近找显式货币标识（覆盖 '10K–15K CNY' 这类后置写法）。"""
    seg = text[max(0, pos - window):min(len(text), pos + window)]
    m = CURRENCY_NEAR_RE.search(seg)
    if not m:
        return None
    tok = m.group(0)
    return (CURRENCY_SYMBOLS.get(tok)
            or CURRENCY_WORDS.get(tok.lower())
            or ("CNY" if tok in ("人民币", "元") else None))


def parse_salary(text: str) -> dict | None:
    """从文本解析薪资区间；不可解析返回 None（绝不编造）。

    英文规则：带货币符号/代码才解析；裸 100–999 数值按「千」惯例（assumed-k）。
    中文规则（v0.2）：数字带 k/K/万/w/W 后缀即可解析；无显式货币但上下文为中文时
    推断为 CNY（assumed-cny）；无周期标记时按中文市场惯例视为月薪
    （assumed-monthly，K/万 = 每月）；显式 /年、年薪则按年。区间两端可共享后缀
    （"3-5万"、"25-40K"）；"·14薪" 等年终月数剔除。"面议" 无数字，自然缺失。
    """
    text = re.sub(r"[·•]\s*\d+薪", "", text)
    ctx_cjk = cjk_ratio(text) > 0.15
    tokens: list[dict] = []
    for m in MONEY_RE.finditer(text):
        cur_raw = m.group("cur")
        suffix = m.group("suffix")
        raw_val = _decode_amount(m.group("amt"))
        if raw_val is None:
            continue
        mult = SUFFIX_MULT.get(suffix) if suffix else None
        currency = None
        if cur_raw:
            currency = CURRENCY_SYMBOLS.get(cur_raw) or CURRENCY_WORDS.get(cur_raw.lower(), cur_raw.upper())
        tokens.append({
            "pos": m.start(), "end": m.end(), "raw_val": raw_val,
            "mult": mult, "currency": currency, "suffix": suffix,
        })
    if not tokens:
        return None
    ranges: list[dict] = []
    used = [False] * len(tokens)
    for i, t in enumerate(tokens):
        if used[i]:
            continue
        paired = None
        for j in range(i + 1, min(i + 3, len(tokens))):
            if used[j]:
                break
            gap = text[t["end"]:tokens[j]["pos"]]
            if RANGE_SEP_RE.fullmatch(gap.strip()) and tokens[j]["raw_val"] >= t["raw_val"] * 0.8:
                paired = j
                break
        lo_t, hi_t = (t, tokens[paired]) if paired is not None else (t, t)
        if paired is not None:
            used[paired] = True
        used[i] = True
        # 单 token：必须有货币或倍率后缀才可信；区间：允许lo 无后缀继承 hi 的
        if paired is None and t["currency"] is None and t["mult"] is None:
            continue
        mult_eff = lo_t["mult"] or (hi_t["mult"] if paired is not None else None)
        conf = "parsed"
        currency = lo_t["currency"] or (hi_t["currency"] if paired is not None else None)
        if currency is None:
            currency = _currency_near(text, lo_t["pos"])
        if currency is None:
            if ctx_cjk and mult_eff:
                currency = "CNY"
                conf = "assumed-cny"
            else:
                continue  # 无货币标识（英文语境）不解析
        lo = lo_t["raw_val"] * (mult_eff or 1)
        hi = hi_t["raw_val"] * (mult_eff or 1)
        if (mult_eff is None and currency != "CNY"
                and 100 <= lo_t["raw_val"] < 1000):
            lo *= 1_000  # "$150-200" ≈ 千元惯例（两端均无后缀时才适用）
            hi *= 1_000
            conf = "assumed-k"
        explicit_period = _period_near(text, lo_t["pos"])
        period = explicit_period
        if period is None:
            # 中文市场裸 K/万 默认月薪；英文默认年薪
            period = "monthly" if (currency == "CNY" and mult_eff) else "annual"
            if currency == "CNY" and mult_eff:
                conf += "+assumed-monthly"
        lo_usd = _annualize(lo * FX_TO_USD.get(currency, 0), period)
        hi_usd = _annualize(hi * FX_TO_USD.get(currency, 0), period)
        if lo_usd is None or not (SALARY_MIN_USD <= lo_usd <= SALARY_MAX_USD):
            continue  # 不在合理年薪域，丢弃（宁缺毋滥）
        ranges.append({
            "min_usd": round(lo_usd), "max_usd": round(hi_usd or lo_usd),
            "currency": currency, "period": period, "conf": conf,
            "raw": text[lo_t["pos"]:hi_t["end"]][:60],
        })
    if not ranges:
        return None
    ranges.sort(key=lambda r: (r["max_usd"] - r["min_usd"]) + r["max_usd"], reverse=True)
    return ranges[0]  # 取信息量最大的一处（通常即 Compensation 行）


# ---------------- 公司 / 职位 / 地点 ----------------

LEGAL_SUFFIX_RE = re.compile(
    r"\s*[,/(\s]+(?:inc|llc|ltd|limited|gmbh|bv|bvba|co|corp|corporation|company|plc|sa|sas|srl|ab|as|oy|pty|pvt)\b[.)]*\s*$", re.I)


def norm_company(name: str | None) -> str:
    if not name:
        return ""
    n = name.strip().strip("|·,.- ")
    n = LEGAL_SUFFIX_RE.sub("", n)
    n = re.sub(r"(股份)?有限公司$", "", n)  # 中文法律后缀（v0.2）
    n = re.sub(r"\s+", " ", n)
    return n.lower().strip()


TITLE_WORD_RE = re.compile(
    r"\b(engineer|developer|manager|scientist|designer|architect|analyst|lead|head|director|intern|specialist|consultant|researcher|marketer|sales|growth|recruiter|sre|devops)\b", re.I)


def extract_hn_fields(text: str) -> tuple[str, str]:
    """从 HN 帖首行启发式提取 (company, title)。"""
    first_line = text.split("\n", 1)[0]
    segs = [s.strip() for s in first_line.split("|") if s.strip()]
    company, title = "", ""
    m = re.match(r"^\s*company\s*[:：]\s*(.+)$", first_line, re.I)
    if m and segs:
        company = m.group(1).split("|")[0].strip()
        rest = first_line[m.end():].strip(" |·-")
        tsegs = [s.strip() for s in rest.split("|") if s.strip()]
        if tsegs:
            title = max(tsegs, key=lambda s: len(TITLE_WORD_RE.findall(s)))
    elif segs:
        scores = [len(TITLE_WORD_RE.findall(s)) for s in segs]
        title_idx = scores.index(max(scores)) if max(scores) > 0 else min(1, len(segs) - 1)
        title = segs[title_idx]
        company_idx = 0 if title_idx != 0 else (1 if len(segs) > 1 else -1)
        if company_idx >= 0:
            company = re.sub(r"\(.*?\)|\[.*?\]", "", segs[company_idx]).strip(" -–—")
    company = re.sub(r"^hiring\s+", "", company, flags=re.I)
    return company.strip(" |·-"), title.strip(" |·-")


CITIES = {
    "san francisco": ("San Francisco", "US"), " sf ": ("San Francisco", "US"),
    "bay area": ("San Francisco", "US"), "silicon valley": ("San Francisco", "US"),
    "new york": ("New York", "US"), "nyc": ("New York", "US"),
    "seattle": ("Seattle", "US"), "austin": ("Austin", "US"),
    "boston": ("Boston", "US"), "los angeles": ("Los Angeles", "US"),
    "chicago": ("Chicago", "US"), "denver": ("Denver", "US"),
    "toronto": ("Toronto", "CA"), "vancouver": ("Vancouver", "CA"),
    "london": ("London", "GB"), "berlin": ("Berlin", "DE"), "munich": ("Munich", "DE"),
    "amsterdam": ("Amsterdam", "NL"), "paris": ("Paris", "FR"), "dublin": ("Dublin", "IE"),
    "zurich": ("Zurich", "CH"), "stockholm": ("Stockholm", "SE"),
    "copenhagen": ("Copenhagen", "DK"), "lisbon": ("Lisbon", "PT"),
    "barcelona": ("Barcelona", "ES"), "madrid": ("Madrid", "ES"),
    "warsaw": ("Warsaw", "PL"), "tel aviv": ("Tel Aviv", "IL"),
    "singapore": ("Singapore", "SG"), "tokyo": ("Tokyo", "JP"),
    "sydney": ("Sydney", "AU"), "melbourne": ("Melbourne", "AU"),
    "hong kong": ("Hong Kong", "HK"), "dubai": ("Dubai", "AE"),
    "bangalore": ("Bangalore", "IN"), "bengaluru": ("Bangalore", "IN"),
    "hyderabad": ("Hyderabad", "IN"), "pune": ("Pune", "IN"),
    "são paulo": ("São Paulo", "BR"), "sao paulo": ("São Paulo", "BR"),
    # 中文城市（v0.2）
    "北京": ("Beijing", "CN"), "上海": ("Shanghai", "CN"), "深圳": ("Shenzhen", "CN"),
    "广州": ("Guangzhou", "CN"), "杭州": ("Hangzhou", "CN"), "成都": ("Chengdu", "CN"),
    "南京": ("Nanjing", "CN"), "武汉": ("Wuhan", "CN"), "西安": ("Xi'an", "CN"),
    "苏州": ("Suzhou", "CN"), "天津": ("Tianjin", "CN"), "合肥": ("Hefei", "CN"),
    "长沙": ("Changsha", "CN"), "重庆": ("Chongqing", "CN"), "厦门": ("Xiamen", "CN"),
    "珠海": ("Zhuhai", "CN"), "青岛": ("Qingdao", "CN"), "郑州": ("Zhengzhou", "CN"),
    "香港": ("Hong Kong", "HK"),
}

REMOTE_RE = re.compile(r"\bremote\b|远程", re.I)
HYBRID_RE = re.compile(r"\bhybrid\b|混合办公", re.I)


def extract_geo(text: str) -> tuple[str | None, str | None, int, str]:
    """返回 (city, country, is_remote, remote_kind)。"""
    probe = " " + text[:1200].lower() + " "
    city = country = None
    for alias, (c, co) in CITIES.items():
        if alias in probe:
            city, country = c, co
            break
    remote = bool(REMOTE_RE.search(probe))
    hybrid = bool(HYBRID_RE.search(probe))
    if remote and hybrid:
        kind = "remote+hybrid"
    elif remote:
        kind = "remote"
    elif hybrid:
        kind = "hybrid"
    else:
        kind = "unknown"
    return city, country, int(remote), kind


# ---------------- 技能抽取 ----------------

SKILL_COMPILED = [(sid, [re.compile(p, re.I) for p in pats])
                  for (sid, _en, _zh, _cat, pats, _core) in SKILLS]


def extract_skills(text: str) -> list[str]:
    return [sid for sid, pats in SKILL_COMPILED if any(p.search(text) for p in pats)]


# ---------------- 岗位分类 ----------------

def _kw_re(k: str) -> re.Pattern:
    """含 CJK 的关键词按子串匹配（\\b 对 CJK 无效），拉丁词加 \\b 词边界。"""
    if has_cjk(k):
        return re.compile(re.escape(k))
    return re.compile(r"\b" + re.escape(k) + r"\b", re.I)


ROLE_COMPILED = [
    {
        "id": r["id"],
        "title": [_kw_re(k) for k in r["title_keywords"] + r.get("title_keywords_zh", [])],
        "text": [_kw_re(k) for k in r["text_keywords"] + r.get("text_keywords_zh", [])]
                + [re.compile(p, re.I) for p in r.get("text_keywords_raw", [])],
    }
    for r in ROLES
]
AI_GATE_COMPILED = ([_kw_re(k) for k in AI_GATE]
                    + [re.compile(p, re.I) for p in AI_GATE_RAW]
                    + [_kw_re(k) for k in AI_GATE_ZH])
MAX_TEXT_HITS = 8  # 每类正文关键词最多计 8 次，防长文刷分


def classify(title: str, text: str) -> tuple[str, list[str], int]:
    blob = f"{title}\n{text}"
    is_ai = int(any(p.search(blob) for p in AI_GATE_COMPILED))
    scores: dict[str, float] = {}
    for role in ROLE_COMPILED:
        s = 0.0
        if title:
            s += sum(4.0 for p in role["title"] if p.search(title))
        hits = sum(min(1, sum(1 for _ in p.finditer(text))) for p in role["text"])
        s += min(hits, MAX_TEXT_HITS)
        scores[role["id"]] = s
    if not is_ai or max(scores.values()) < 3.0:
        return ("non-ai" if not is_ai else "other"), [], is_ai
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    primary = ranked[0][0]
    multi = [rid for rid, s in ranked if s >= ranked[0][1] * 0.6 and s >= 3.0][:3]
    return primary, multi, is_ai


# ---------------- 各来源解析 ----------------

def load_hn() -> list[dict]:
    out = []
    idx = json.loads((RAW / "hn" / "threads_index.json").read_text())
    for t in idx:
        f = RAW / "hn" / f"thread_{t['id']}.json"
        if not f.exists():
            continue
        if not t["title"].lower().startswith("ask hn: who is hiring? ("):
            continue  # 排除 freelance 等变体
        data = json.loads(f.read_text())
        month = t["created_at"][:7]
        for c in data["comments"]:
            text = html_to_text(c["text"])
            if len(text) < 60:
                continue
            company, title = extract_hn_fields(text)
            out.append({
                "source": "hn", "source_id": str(c["objectID"]),
                "posted_date": (c["created_at"] or "")[:10], "month": month,
                "company": company, "title": title, "text": text, "url": None,
            })
    return out


def load_remoteok() -> list[dict]:
    f = RAW / "misc" / "remoteok.json"
    if not f.exists():
        return []
    out = []
    for j in json.loads(f.read_text()):
        text = html_to_text(f"{j.get('position', '')} {j.get('description', '')}")
        if len(text) < 40:
            continue
        date = ""
        if j.get("epoch"):
            date = time.strftime("%Y-%m-%d", time.gmtime(int(j["epoch"])))
        sal = None
        try:  # RemoteOK 自带结构化薪资（USD 年薪口径），走同一合理性门槛
            smin, smax = j.get("salary_min"), j.get("salary_max")
            if smin and SALARY_MIN_USD <= float(smin) <= SALARY_MAX_USD:
                sal = {
                    "min_usd": round(float(smin)),
                    "max_usd": round(float(smax or smin)),
                    "currency": "USD", "period": "annual",
                    "conf": "remoteok-structured", "raw": f"{smin}-{smax}",
                }
        except (TypeError, ValueError):
            sal = None
        rec = {
            "source": "remoteok", "source_id": str(j.get("id") or j.get("slug") or ""),
            "posted_date": date, "month": date[:7],
            "company": j.get("company") or "", "title": j.get("position") or "",
            "text": text,
            "url": ("https://remoteok.com" + j["url"]) if j.get("url") else None,
        }
        if sal:
            rec["salary_override"] = sal
        out.append(rec)
    return out


def load_wwr() -> list[dict]:
    out = []
    for f in sorted((RAW / "misc").glob("wwr_*.xml")):
        root = parse_xml_safely(f.read_text())
        for item in root.iter("item"):

            def t(tag: str, _item=item) -> str:
                el = _item.find(tag)
                return (el.text or "") if el is not None else ""

            title = html.unescape(t("title"))
            text = html_to_text(t("description"))
            if len(text) < 40:
                continue
            date = ""
            raw_date = t("pubDate")
            if raw_date:
                try:
                    from email.utils import parsedate_to_datetime
                    date = parsedate_to_datetime(raw_date).date().isoformat()
                except Exception:  # noqa: BLE001
                    date = ""
            out.append({
                "source": "wwr",
                "source_id": hashlib.sha256(title.encode()).hexdigest()[:12],
                "posted_date": date, "month": date[:7],
                "company": html.unescape(t("company")), "title": title,
                "text": text, "url": t("url") or None,
            })
    return out


def load_v2ex() -> list[dict]:
    f = RAW / "zh" / "v2ex.json"
    if not f.exists():
        return []
    out = []
    for t in json.loads(f.read_text()):
        text = html_to_text(t.get("content") or "")
        title = html.unescape(t.get("title") or "")
        if len(text) < 40:
            continue
        date = ""
        if t.get("created"):
            date = time.strftime("%Y-%m-%d", time.gmtime(int(t["created"])))
        out.append({
            "source": "v2ex", "source_id": str(t.get("url", "")),
            "posted_date": date, "month": date[:7],
            "company": "", "title": title, "text": text,
            "url": t.get("url"), "needs_title_parse": True,
        })
    return out


def _v2ex_title_parse(title: str, text: str) -> tuple[str, str]:
    """V2EX 帖标题启发式：[城市] 公司 招职位 / 招聘｜职位｜待遇。"""
    t = re.sub(r"^\s*[\[【]([^\]】]{1,8})[\]】]\s*", "", title).strip()
    company = ""
    m = re.split(r"招(?:聘|人|募)?(?:急招)?", t, maxsplit=1)
    if m and 2 <= len(m[0].strip()) <= 16 and len(m) > 1:
        company = m[0].strip(" |-–—/·,，")
    if not company:
        parts = re.split(r"[｜|/]", title)
        if len(parts) >= 2 and 2 <= len(parts[0].strip()) <= 16:
            company = parts[0].strip()
    return company, t


def load_zh() -> list[dict]:
    """腾讯/百度官方招聘 + V2EX（v0.2 中文市场）。"""
    out = []
    f = RAW / "zh" / "tencent.json"
    if f.exists():
        for p in json.loads(f.read_text()):
            resp = (p.get("Responsibility") or "").strip()
            if len(resp) < 40:
                continue
            loc = p.get("LocationName") or ""
            title = f"{p.get('RecruitPostName', '')} {loc}".strip()
            text = f"岗位类别：{p.get('CategoryName', '')}（{p.get('BGName', '')}）\n{resp}"
            date = (p.get("LastUpdateTime") or "")[:10]
            out.append({
                "source": "tencent", "source_id": str(p.get("PostId") or ""),
                "posted_date": date, "month": date[:7],
                "company": "腾讯", "title": title, "text": text,
                "url": f"https://careers.tencent.com/jobdesc.html?postId={p.get('PostId')}",
            })
    f = RAW / "zh" / "baidu.json"
    if f.exists():
        for p in json.loads(f.read_text()):
            duty = (p.get("workContent") or "").strip()
            req = (p.get("serviceCondition") or "").strip()
            if len(duty) + len(req) < 40:
                continue
            loc = (p.get("workPlace") or "").strip()
            title = f"{p.get('name', '')} {loc}".strip()
            text = f"工作职责：\n{duty}\n任职要求：\n{req}"
            date = (p.get("updateDate") or p.get("publishDate") or "")[:10]
            out.append({
                "source": "baidu", "source_id": str(p.get("postId") or ""),
                "posted_date": date, "month": date[:7],
                "company": "百度", "title": title, "text": text, "url": None,
            })
    for r in load_v2ex():
        company, title_clean = _v2ex_title_parse(r["title"], r["text"])
        r["company"] = company
        r["title"] = title_clean
        r.pop("needs_title_parse", None)
        out.append(r)
    return out


def main() -> None:
    PROCESSED.mkdir(parents=True, exist_ok=True)
    rows = load_hn() + load_remoteok() + load_wwr() + load_zh()
    print(f"loaded raw posts: {len(rows)}")
    seen: set[str] = set()
    records: list[dict] = []
    for r in rows:
        city, country, is_remote, remote_kind = extract_geo(r["title"] + "\n" + r["text"][:800])
        role, roles_all, is_ai = classify(r["title"], r["text"])
        skills = extract_skills(r["text"])
        sal = r.get("salary_override") or parse_salary(r["text"])
        company_norm = norm_company(r["company"])
        title_norm = re.sub(r"\s+", " ", (r["title"] or "").lower()).strip()
        # 官方结构化源以 source_id 去重（同月同题不同岗很常见）；社区帖沿用 月|公司|题
        if r["source"] in ("tencent", "baidu"):
            dedup_base = f"{r['source']}|{r['source_id']}"
        else:
            dedup_base = f"{r['source']}|{r['month']}|{company_norm}|{title_norm}"
        dedup_key = hashlib.sha256(dedup_base.encode()).hexdigest()
        if dedup_key in seen:
            continue
        seen.add(dedup_key)
        rec = dict.fromkeys(FIELDS)  # SQL 列；lang 为 JSON 附加字段
        rec.update({
            **r, "company_norm": company_norm,
            "is_ai": is_ai, "role": role, "roles_all": json.dumps(roles_all),
            "skills": json.dumps(skills),
            "is_remote": is_remote, "remote_kind": remote_kind,
            "city": city, "country": country,
            "lang": detect_lang((r["title"] or "") + " " + r["text"][:500]),
            "salary_min_usd": sal["min_usd"] if sal else None,
            "salary_max_usd": sal["max_usd"] if sal else None,
            "salary_currency": sal["currency"] if sal else None,
            "salary_period": sal["period"] if sal else None,
            "salary_raw": sal["raw"] if sal else None,
            "salary_conf": sal["conf"] if sal else None,
            "text_clean": smart_truncate(r["text"]),
        })
        records.append(rec)

    conn = sqlite3.connect(DB_PATH)
    conn.execute(DDL_JOBS)
    conn.execute(DDL_IDX_ROLE)
    conn.execute(DDL_IDX_AI)
    conn.execute(DDL_IDX_MONTH)
    conn.execute(DDL_META)
    conn.execute(DELETE_JOBS)
    conn.execute(DELETE_META)
    conn.executemany(INSERT_SQL, [dict.fromkeys(FIELDS) | {k: rec[k] for k in FIELDS} for rec in records])
    conn.executemany(META_INSERT, [
        {"key": "built_at", "value": time.strftime("%Y-%m-%dT%H:%M:%S%z")},
        {"key": "fx_note", "value": "static FX snapshot for coarse normalization only"},
    ])
    conn.commit()

    ai_rows = [x for x in records if x["is_ai"]]
    sal_rows = [x for x in ai_rows if x["salary_min_usd"]]
    print(f"total={len(records)} ai={len(ai_rows)} with_salary={len(sal_rows)}")
    from collections import Counter
    print("roles:", Counter(x["role"] for x in ai_rows).most_common())
    print("salary conf:", Counter(x["salary_conf"] for x in sal_rows).most_common())
    (PROCESSED / "jobs.json").write_text(json.dumps(
        [{k: v for k, v in x.items() if k != "text_clean"} for x in records],
        ensure_ascii=False))
    conn.close()


if __name__ == "__main__":
    main()
