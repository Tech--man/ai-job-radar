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
from roles_dict import AI_GATE, AI_GATE_RAW, ROLES
from skills_dict import SKILLS

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
DB_PATH = ROOT / "data" / "ai_jobs.sqlite"
PROCESSED = ROOT / "data" / "processed"

INSERT_SQL = (
    "INSERT INTO jobs (source, source_id, posted_date, month, company, company_norm, title,"
    " is_ai, role, roles_all, skills, is_remote, remote_kind, city, country,"
    " salary_min_usd, salary_max_usd, salary_currency, salary_period, salary_raw, salary_conf,"
    " text_clean, url, dedup_key)"
    " VALUES (:source, :source_id, :posted_date, :month, :company, :company_norm, :title,"
    " :is_ai, :role, :roles_all, :skills, :is_remote, :remote_kind, :city, :country,"
    " :salary_min_usd, :salary_max_usd, :salary_currency, :salary_period, :salary_raw,"
    " :salary_conf, :text_clean, :url, :dedup_key)"
)

# ---------------- 文本清洗 ----------------

TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"[ \t\f\v]+")


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

CURRENCY_SYMBOLS = {"$": "USD", "€": "EUR", "£": "GBP", "¥": "JPY"}
CURRENCY_WORDS = {
    "usd": "USD", "eur": "EUR", "gbp": "GBP", "cad": "CAD", "aud": "AUD",
    "nzd": "NZD", "chf": "CHF", "sek": "SEK", "nok": "NOK", "dkk": "DKK",
    "sgd": "SGD", "jpy": "JPY", "inr": "INR", "cny": "CNY", "rmb": "CNY",
    "brl": "BRL", "pln": "PLN", "czk": "CZK",
}

MONEY_RE = re.compile(
    r"(?P<cur>[$€£¥]|\b(?:USD|EUR|GBP|CAD|AUD|NZD|CHF|SEK|NOK|DKK|SGD|JPY|INR|CNY|BRL|PLN|CZK)\b)?"
    r"\s?(?P<amt>\d{1,3}(?:[,.]\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"\s?(?P<suffix>[kKmM])?"
)

PERIOD_PATTERNS = [
    (re.compile(r"\b(?:/|per\s+|a\s+)?hr\b|\bhourly\b|\bper\s+hour\b|\ban\s+hour\b", re.I), "hourly"),
    (re.compile(r"\b(?:/|per\s+|a\s+)?day\b|\bdaily\b", re.I), "daily"),
    (re.compile(r"\b(?:/|per\s+|a\s+)?mo\b|\bmonthly\b|\bper\s+month\b|\ba\s+month\b", re.I), "monthly"),
    (re.compile(r"\b(?:/|per\s+|a\s+)?yr\b|\bannual(?:ly)?\b|\bper\s+(?:year|annum)\b|\bsalary\b|\bcomp(?:ensation)?\b", re.I), "annual"),
]
RANGE_SEP_RE = re.compile(r"\s*(?:-|–|—|to)\s*")


def _decode_amount(amt: str, suffix: str | None) -> float | None:
    if re.fullmatch(r"\d{1,3}(?:[,.]\d{3})+(?:\.\d+)?", amt):
        return float(amt.replace(",", ""))
    val = float(amt)
    if suffix and suffix.lower() == "k":
        return val * 1_000
    if suffix and suffix.lower() == "m":
        return val * 1_000_000
    return val


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


def parse_salary(text: str) -> dict | None:
    """从文本解析薪资区间；失败返回 None（绝不编造）。

    约定：带货币符号/代码才解析；纯数字不带货币（如 "150-180"）不解析。
    100–999 且带货币符号的裸数值按「千」解释（HN 惯例），标记 conf=assumed-k。
    """
    tokens: list[dict] = []
    for m in MONEY_RE.finditer(text):
        cur = m.group("cur")
        if not cur:
            continue  # 无货币标识不解析
        currency = CURRENCY_SYMBOLS.get(cur) or CURRENCY_WORDS.get(cur.lower(), cur.upper())
        amt = _decode_amount(m.group("amt"), m.group("suffix"))
        if amt is None:
            continue
        tokens.append({
            "pos": m.start(), "end": m.end(), "value": amt, "currency": currency,
            "suffix": m.group("suffix"), "raw": m.group(0).strip(),
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
            if RANGE_SEP_RE.fullmatch(gap.strip()) and tokens[j]["value"] >= t["value"] * 0.8:
                paired = j
                break
        lo_t, hi_t = (t, tokens[paired]) if paired is not None else (t, t)
        if paired is not None:
            used[paired] = True
        used[i] = True
        conf = "parsed"

        def _scale(x: dict, inherit: float | None) -> float:
            v = x["value"]
            if x["suffix"]:
                return v
            if inherit is not None:
                return v * inherit
            if 100 <= v < 1000:
                return v * 1_000  # "$150-200" ≈ 千元惯例
            return v

        inherit_scale = 1_000 if (lo_t["suffix"] and not hi_t["suffix"]) else None
        lo = _scale(lo_t, None)
        hi = _scale(hi_t, inherit_scale)
        if lo_t["suffix"] is None and 100 <= lo_t["value"] < 1000:
            conf = "assumed-k"
        period = _period_near(text, lo_t["pos"]) or "annual"
        cur = lo_t["currency"]
        lo_usd = _annualize(lo * FX_TO_USD.get(cur, 0), period)
        hi_usd = _annualize(hi * FX_TO_USD.get(cur, 0), period)
        if lo_usd is None or not (SALARY_MIN_USD <= lo_usd <= SALARY_MAX_USD):
            continue  # 明显不是年薪，丢弃（宁缺毋滥）
        ranges.append({
            "min_usd": round(lo_usd), "max_usd": round(hi_usd or lo_usd),
            "currency": cur, "period": period, "conf": conf,
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
}

REMOTE_RE = re.compile(r"\bremote\b", re.I)
HYBRID_RE = re.compile(r"\bhybrid\b", re.I)


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

ROLE_COMPILED = [
    {
        "id": r["id"],
        "title": [re.compile(r"\b" + re.escape(k) + r"\b", re.I) for k in r["title_keywords"]],
        "text": [re.compile(r"\b" + re.escape(k) + r"\b", re.I) for k in r["text_keywords"]]
                + [re.compile(p, re.I) for p in r.get("text_keywords_raw", [])],
    }
    for r in ROLES
]
AI_GATE_COMPILED = ([re.compile(r"\b" + re.escape(k) + r"\b", re.I) for k in AI_GATE]
                    + [re.compile(p, re.I) for p in AI_GATE_RAW])
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


# ---------------- 入库 ----------------

DDL_JOBS = "CREATE TABLE IF NOT EXISTS jobs (id INTEGER PRIMARY KEY, source TEXT NOT NULL, source_id TEXT, posted_date TEXT, month TEXT, company TEXT, company_norm TEXT, title TEXT, is_ai INTEGER, role TEXT, roles_all TEXT, skills TEXT, is_remote INTEGER, remote_kind TEXT, city TEXT, country TEXT, salary_min_usd REAL, salary_max_usd REAL, salary_currency TEXT, salary_period TEXT, salary_raw TEXT, salary_conf TEXT, text_clean TEXT, url TEXT, dedup_key TEXT)"
DDL_IDX_ROLE = "CREATE INDEX IF NOT EXISTS idx_jobs_role ON jobs(role)"
DDL_IDX_AI = "CREATE INDEX IF NOT EXISTS idx_jobs_ai ON jobs(is_ai)"
DDL_IDX_MONTH = "CREATE INDEX IF NOT EXISTS idx_jobs_month ON jobs(month)"
DDL_META = "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)"
DELETE_JOBS = "DELETE FROM jobs"
DELETE_META = "DELETE FROM meta"
META_INSERT = "INSERT INTO meta (key, value) VALUES (:key, :value)"

FIELDS = ["source", "source_id", "posted_date", "month", "company", "company_norm", "title",
          "is_ai", "role", "roles_all", "skills", "is_remote", "remote_kind", "city", "country",
          "salary_min_usd", "salary_max_usd", "salary_currency", "salary_period", "salary_raw",
          "salary_conf", "text_clean", "url", "dedup_key"]


def main() -> None:
    PROCESSED.mkdir(parents=True, exist_ok=True)
    rows = load_hn() + load_remoteok() + load_wwr()
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
        dedup_key = hashlib.sha256(
            f"{r['source']}|{r['month']}|{company_norm}|{title_norm}".encode()).hexdigest()
        if dedup_key in seen:
            continue
        seen.add(dedup_key)
        rec = dict.fromkeys(FIELDS)
        rec.update({
            **r, "company_norm": company_norm,
            "is_ai": is_ai, "role": role, "roles_all": json.dumps(roles_all),
            "skills": json.dumps(skills),
            "is_remote": is_remote, "remote_kind": remote_kind,
            "city": city, "country": country,
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
