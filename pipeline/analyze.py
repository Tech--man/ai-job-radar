"""分析层：读取结构化岗位表，产出网站与报告所需的全部统计 JSON。

产出（data/processed/analysis/）：
- overview.json   总览 KPI、岗位分布、月度趋势、远程比例、Top 技能
- profiles/*.json 每个画像岗位的技能/薪资/城市/公司/样本标题/重合度
- skills.json     技能全集：频次、分类、溢价（含样本量）、特异性、共现 Top
- salary.json     薪资：按岗位/技能/城市/远程/公司类型，缺失显式标注
- companies.json  公司热度榜
- aux.json        GitHub/arXiv/HF 辅助信号透传

统计纪律：
- 薪资一律基于真实解析出的区间（mid = (min+max)/2），样本不足显式标 null。
- 溢价 = 有该技能岗位的薪资中位数 − 同池无该技能岗位的薪资中位数（含 n）。
- 画像岗位成员 = 主标签或 roles_all 多标签命中（RAG 等组合型岗位依赖多标签口径）。
"""

from __future__ import annotations

import json
import math
import statistics as st
from collections import Counter, defaultdict
from pathlib import Path

from roles_dict import ROLES, ROLE_PROFILES
from skills_dict import SKILL_BY_ID, skill_dicts

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
OUT = PROCESSED / "analysis"
MIN_SALARY_SAMPLES = 8  # 溢价/中位数计算的最小样本
BIG_TECH = {
    "google", "meta", "microsoft", "amazon", "apple", "netflix", "openai", "anthropic",
    "nvidia", "tesla", "stripe", "shopify", "datadog", "cloudflare", "figma", "notion",
    "databricks", "snowflake", "salesforce", "ibm", "oracle", "adobe", "uber", "airbnb",
    "linkedin", "tiktok", "bytedance", "tencent", "alibaba", "deepmind", "xai",
    "mistral ai", "mistral", "cohere", "hugging face", "huggingface",
}
STAGE_RE_HINTS = ["seed", "series a", "series b", "series c", "series a+", "pre-seed", "bootstrapped"]


def pct(a: float, b: float) -> float:
    return round(a / b * 100, 1) if b else 0.0


def median_or_none(xs: list[float]) -> float | None:
    return round(st.median(xs)) if len(xs) >= MIN_SALARY_SAMPLES else None


def load_jobs() -> list[dict]:
    rows = json.loads((PROCESSED / "jobs.json").read_text())
    for r in rows:
        r["skills"] = json.loads(r["skills"] or "[]")
        r["roles_all"] = json.loads(r["roles_all"] or "[]")
    return rows


def membership(job: dict, rid: str) -> bool:
    return job["is_ai"] == 1 and (job["role"] == rid or rid in job["roles_all"])


def skill_counts(jobs: list[dict]) -> Counter:
    c: Counter = Counter()
    for j in jobs:
        c.update(j["skills"])
    return c


def salary_pool(jobs: list[dict]) -> list[tuple[dict, float]]:
    out = []
    for j in jobs:
        if j["salary_min_usd"] and j["salary_max_usd"]:
            out.append((j, (j["salary_min_usd"] + j["salary_max_usd"]) / 2))
    return out


def sal_stats(pool: list[tuple[dict, float]]) -> dict:
    if not pool:
        return {"n": 0, "median_min": None, "median_max": None, "median_mid": None,
                "p25_mid": None, "p75_mid": None}
    mids = sorted(m for _, m in pool)
    mins = sorted(j["salary_min_usd"] for j, _ in pool)
    maxs = sorted(j["salary_max_usd"] for j, _ in pool)

    def q(xs: list[float], f: float) -> float:
        i = min(len(xs) - 1, max(0, int(f * (len(xs) - 1))))
        return round(xs[i])
    return {
        "n": len(pool),
        "median_min": round(st.median(mins)),
        "median_max": round(st.median(maxs)),
        "median_mid": round(st.median(mids)),
        "p25_mid": q(mids, 0.25),
        "p75_mid": q(mids, 0.75),
    }


def skill_premium(pool: list[tuple[dict, float]]) -> list[dict]:
    if len(pool) < MIN_SALARY_SAMPLES * 2:
        return []
    all_mids = [m for _, m in pool]
    base = st.median(all_mids)
    out = []
    have = skill_counts([j for j, _ in pool])
    for sid, cnt in have.most_common():
        if cnt < MIN_SALARY_SAMPLES:
            continue
        with_mids = [m for j, m in pool if sid in j["skills"]]
        without_mids = [m for j, m in pool if sid not in j["skills"]]
        if len(without_mids) < MIN_SALARY_SAMPLES:
            continue
        med_with, med_without = st.median(with_mids), st.median(without_mids)
        delta = med_with - med_without
        out.append({
            "skill": sid,
            "n_with": len(with_mids),
            "median_with": round(med_with),
            "median_without": round(med_without),
            "delta_usd": round(delta),
            "delta_pct": round(delta / med_without * 100, 1) if med_without else None,
            "confidence": "low" if cnt < 20 else ("medium" if cnt < 40 else "high"),
        })
    out.sort(key=lambda d: (d["delta_usd"] or 0), reverse=True)
    return out


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return round(len(a & b) / len(a | b), 3)


def main() -> None:
    (OUT / "profiles").mkdir(parents=True, exist_ok=True)
    jobs = load_jobs()
    ai_jobs = [j for j in jobs if j["is_ai"] == 1]
    sal_ai = salary_pool(ai_jobs)

    # ---- 分组成员与技能 ----
    groups: dict[str, list[dict]] = {}
    for rid in [r["id"] for r in ROLES] + ["other"]:
        groups[rid] = [j for j in ai_jobs if membership(j, rid)] if rid != "other" \
            else [j for j in ai_jobs if j["role"] == "other"]

    overall_counts = skill_counts(ai_jobs)

    # ---- 溢价（全池） ----
    premium = skill_premium(sal_ai)

    # ---- 特异性（技能在各岗位组的分布熵）----
    spec_groups = {g: js for g, js in groups.items() if len(js) >= 15}
    spec: dict[str, float] = {}
    for sid in overall_counts:
        shares = []
        for g, js in spec_groups.items():
            k = sum(1 for j in js if sid in j["skills"])
            shares.append(k / len(js))
        tot = sum(shares)
        if tot <= 0:
            spec[sid] = 0.0
            continue
        p = [s / tot for s in shares if s > 0]
        h = -sum(x * math.log(x) for x in p)
        spec[sid] = round(1 - h / math.log(len(p)) if len(p) > 1 else 0.0, 3)

    # ---- 噪音技能候选：高频 + 低溢价 + 低特异性 ----
    prem_by_skill = {d["skill"]: d for d in premium}
    noise = []
    for sid, cnt in overall_counts.most_common(40):
        freq = pct(cnt, len(ai_jobs))
        if freq < 5:
            continue
        d = prem_by_skill.get(sid)
        delta_pct = d["delta_pct"] if d else None
        entry = {
            "skill": sid, "freq_pct": freq,
            "delta_pct": delta_pct,
            "n_with": d["n_with"] if d else 0,
            "specificity": spec.get(sid, 0.0),
        }
        if delta_pct is not None and delta_pct <= 3 and entry["specificity"] <= 0.35:
            entry["verdict"] = "噪音候选：高频、溢价≈0、岗位区分度低"
        elif delta_pct is None:
            entry["verdict"] = "溢价样本不足，无法判定"
        else:
            entry["verdict"] = "有区分度" if delta_pct > 8 else "中性"
        noise.append(entry)

    # ---- skills.json ----
    cooc: Counter = Counter()
    for j in ai_jobs:
        ss = sorted(set(j["skills"]))
        for i in range(len(ss)):
            for k in range(i + 1, len(ss)):
                cooc[(ss[i], ss[k])] += 1
    top_pairs = [{"a": a, "b": b, "n": n} for (a, b), n in cooc.most_common(120) if n >= 5]
    sdicts = {s["id"]: s for s in skill_dicts()}
    skills_payload = []
    for sid, cnt in overall_counts.most_common():
        meta = sdicts.get(sid, {})
        d = prem_by_skill.get(sid)
        skills_payload.append({
            "id": sid, "name_en": meta.get("name_en", sid), "name_zh": meta.get("name_zh", sid),
            "category": meta.get("category", ""),
            "count": cnt, "freq_pct": pct(cnt, len(ai_jobs)),
            "delta_pct": d["delta_pct"] if d else None,
            "n_with": d["n_with"] if d else 0,
            "confidence": d["confidence"] if d else "insufficient",
            "specificity": spec.get(sid, 0.0),
            "core_for": meta.get("core_for", []),
        })
    (OUT / "skills.json").write_text(json.dumps({
        "total_ai_jobs": len(ai_jobs),
        "skills": skills_payload,
        "cooccurrence_top": top_pairs,
        "noise_candidates": noise,
    }, ensure_ascii=False))

    # ---- profiles ----
    role_meta = {r["id"]: r for r in ROLES}
    profile_ids = ROLE_PROFILES
    overlap_sets = {rid: {s for s, c in skill_counts(groups[rid]).items()
                          if pct(c, len(groups[rid])) >= 10} for rid in profile_ids}
    for rid in profile_ids:
        js = groups[rid]
        sc = skill_counts(js)
        pool = salary_pool(js)
        cities = Counter(j["city"] for j in js if j["city"]).most_common(10)
        companies = Counter(j["company_norm"] for j in js if j["company_norm"]).most_common(15)
        titles = []
        seen_t = set()
        for j in js:
            t = (j["title"] or "").strip()
            if 12 <= len(t) <= 90 and t.lower() not in seen_t:
                titles.append({"title": t, "company": j["company"] or "", "source": j["source"]})
                seen_t.add(t.lower())
            if len(titles) >= 8:
                break
        remote_n = sum(1 for j in js if j["is_remote"])
        payload = {
            "id": rid, "name_zh": role_meta[rid]["name_zh"], "name_en": role_meta[rid]["name_en"],
            "n_posts": len(js),
            "share_of_ai": pct(len(js), len(ai_jobs)),
            "top_skills": [{"skill": s, "name_zh": sdicts.get(s, {}).get("name_zh", s),
                            "count": c, "freq_pct": pct(c, len(js))}
                           for s, c in sc.most_common(25)],
            "salary": {**sal_stats(pool), "salary_available_share": pct(len(pool), len(js))},
            "cities": cities,
            "remote_ratio": pct(remote_n, len(js)),
            "top_companies": [{"company": c, "n": n} for c, n in companies if n >= 2][:12],
            "sample_titles": titles,
            "overlap": {other: jaccard(overlap_sets[rid], overlap_sets[other])
                        for other in profile_ids if other != rid},
        }
        (OUT / "profiles" / f"{rid}.json").write_text(json.dumps(payload, ensure_ascii=False))

    # ---- salary.json ----
    by_role = {}
    for rid, js in groups.items():
        pool = salary_pool(js)
        by_role[rid] = {**sal_stats(pool), "salary_available_share": pct(len(pool), len(js)),
                        "n_posts": len(js)}
    by_skill = []
    for d in premium:
        by_skill.append(d)
    by_city = {}
    city_jobs: dict[str, list[dict]] = defaultdict(list)
    for j in ai_jobs:
        if j["city"]:
            city_jobs[j["city"]].append(j)
    for city, js in sorted(city_jobs.items(), key=lambda kv: -len(kv[1]))[:15]:
        pool = salary_pool(js)
        by_city[city] = {**sal_stats(pool), "n_posts": len(js)}
    by_remote = {}
    for kind in ["remote", "hybrid", "unknown"]:
        js = [j for j in ai_jobs if (j["remote_kind"].startswith("remote") if kind == "remote"
                                     else j["remote_kind"] == kind)]
        pool = salary_pool(js)
        if js:
            by_remote[kind] = {**sal_stats(pool), "n_posts": len(js)}
    by_stage = {}
    for label, keys in [("bigtech", None), ("startup_stated", STAGE_RE_HINTS)]:
        if label == "bigtech":
            js = [j for j in ai_jobs if j["company_norm"] in BIG_TECH]
        else:
            def has_stage(j, keys=keys):
                blob = (j["title"] + " " + j["company"]).lower()
                return any(k in blob for k in keys)
            js = [j for j in ai_jobs if has_stage(j)]
        pool = salary_pool(js)
        by_stage[label] = {**sal_stats(pool), "n_posts": len(js)}
    (OUT / "salary.json").write_text(json.dumps({
        "pool_size": len(sal_ai),
        "pool_share": pct(len(sal_ai), len(ai_jobs)),
        "by_role": by_role, "by_skill_top": by_skill[:30],
        "by_city": by_city, "by_remote": by_remote, "by_stage": by_stage,
        "method_note": "mid=(min+max)/2，基于真实解析区间；n<8 显示为 null；缺失不插补",
    }, ensure_ascii=False))

    # ---- companies.json ----
    comp_counter: Counter = Counter()
    comp_display: dict[str, Counter] = defaultdict(Counter)
    comp_roles: dict[str, Counter] = defaultdict(Counter)
    for j in ai_jobs:
        cn = j["company_norm"]
        if not cn or len(cn) < 2:
            continue
        comp_counter[cn] += 1
        comp_display[cn][j["company"]] += 1
        comp_roles[cn][j["role"]] += 1
    companies_payload = []
    for cn, n in comp_counter.most_common(60):
        if n < 3:
            break
        companies_payload.append({
            "company": comp_display[cn].most_common(1)[0][0],
            "norm": cn, "n": n,
            "top_roles": comp_roles[cn].most_common(3),
            "is_bigtech_listed": cn in BIG_TECH,
        })
    (OUT / "companies.json").write_text(json.dumps({
        "note": "公司名来自帖子自述的启发式抽取与归一，可能有残余噪声；n=出现帖次数（含跨月重复招聘）",
        "companies": companies_payload,
    }, ensure_ascii=False))

    # ---- trend.json（仅 HN 月度帖口径）----
    months = sorted({j["month"] for j in jobs if j["source"] == "hn" and j["month"]})
    trend = []
    for m in months:
        mjobs = [j for j in jobs if j["source"] == "hn" and j["month"] == m]
        mai = [j for j in mjobs if j["is_ai"] == 1]
        trend.append({
            "month": m, "posts": len(mjobs), "ai_posts": len(mai),
            "ai_share": pct(len(mai), len(mjobs)),
            "by_role": {rid: len([j for j in mai if membership(j, rid)]) for rid in profile_ids},
            "with_salary": len([j for j in mai if j["salary_min_usd"]]),
        })
    (OUT / "trend.json").write_text(json.dumps(trend, ensure_ascii=False))

    # ---- overview.json ----
    aux = {}
    auxf = ROOT / "data" / "raw" / "misc" / "aux_signals.json"
    if auxf.exists():
        aux = json.loads(auxf.read_text())
    (OUT / "overview.json").write_text(json.dumps({
        "built_from": {"total_posts": len(jobs), "ai_posts": len(ai_jobs),
                       "salary_posts": len(sal_ai),
                       "sources": dict(Counter(j["source"] for j in jobs)),
                       "months": [months[0], months[-1]] if months else []},
        "role_distribution": [{"role": rid, "name_zh": role_meta.get(rid, {}).get("name_zh",
                               "通用 AI / 其他"), "n": len(js), "share": pct(len(js), len(ai_jobs))}
                              for rid, js in groups.items()],
        "top_skills": skills_payload[:25],
        "aux": aux,
    }, ensure_ascii=False))

    print(f"analysis done: ai={len(ai_jobs)} salary_pool={len(sal_ai)} "
          f"skills={len(skills_payload)} premium_entries={len(premium)}")
    print("top premium:", [(d['skill'], d['delta_pct'], d['n_with']) for d in premium[:8]])
    print("bottom premium:", [(d['skill'], d['delta_pct'], d['n_with']) for d in premium[-5:]])


if __name__ == "__main__":
    main()
