"""辅助信号源（尽力而为，失败不阻塞主线）：

- GitHub：AI 技能生态仓库的 star 数（生态热度参考）。
- arXiv：三个主题的论文总量与年初以来增量（研究热度参考）。
- Hugging Face：按 filter 抽样模型数（HF 未提供计数头，仅作抽样参考）。

所有出站请求走 config.safe_fetch（https-only、host 白名单、公网 IP 校验、
固定连接、不跟随重定向）。凭据仅从环境变量读取。
"""

from __future__ import annotations

import json
import os
import time
import urllib.parse
from pathlib import Path

from config import parse_xml_safely, safe_fetch

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "misc" / "aux_signals.json"
MANIFEST = ROOT / "data" / "raw" / "SOURCE_MANIFEST.json"

REPOS = [
    "langchain-ai/langchain", "langchain-ai/langgraph", "run-llama/llama_index",
    "vllm-project/vllm", "sgl-project/sglang", "microsoft/autogen", "crewAIInc/crewAI",
    "stanfordnlp/dspy", "huggingface/transformers", "huggingface/peft", "huggingface/trl",
    "QwenLM/Qwen", "ggml-org/llama.cpp", "modelcontextprotocol/servers",
    "openai/openai-cookbook", "chroma-core/chroma",
    "qdrant/qdrant", "milvus-io/milvus", "ray-project/ray", "apache/airflow",
    "langfuse/langfuse", "ragas-io/ragas",
]

ARXIV_TOPICS = {
    "rag": 'all:"retrieval augmented generation"',
    "llm_agents": 'all:"large language model" AND all:agent',
    "rlhf_alignment": 'all:"reinforcement learning from human feedback" OR all:"direct preference optimization"',
}


def fetch_github() -> dict:
    tok = os.environ.get("GITHUB_TOKEN", "").strip()  # 只从环境变量读取
    headers = {"Authorization": f"Bearer {tok}"} if tok else None
    out: dict = {}
    pending = list(REPOS)
    for attempt in range(2):  # 失败重试一轮
        nxt = []
        for repo in pending:
            # repo 来自代码内静态白名单；host 仍由 safe_fetch 白名单校验
            url = "https://api.github.com/repos/" + repo
            try:
                data = json.loads(safe_fetch(url, headers=headers))
                out[repo] = {"stars": data.get("stargazers_count"), "updated": data.get("pushed_at")}
            except Exception as exc:  # noqa: BLE001
                out[repo] = {"error": repr(exc)}
                nxt.append(repo)
            time.sleep(0.3)
        if not nxt:
            break
        pending = nxt
        time.sleep(2.0)
    return out


def arxiv_count(query: str, start: str | None = None) -> int | None:
    q = f"({query})"  # 先括住原查询，再追加日期过滤
    if start:
        q += f" AND submittedDate:[{start}0000 TO 999912312359]"
    url = "https://export.arxiv.org/api/query?" + urllib.parse.urlencode({
        "search_query": q, "max_results": 1,
    })
    last_err: Exception | None = None
    for _ in range(3):  # arXiv 偶发 500，重试 + 3s 间隔
        try:
            root = parse_xml_safely(safe_fetch(url))
            ns = {"os": "http://a9.com/-/spec/opensearch/1.1/"}
            total = root.find("os:totalResults", ns)
            return int(total.text) if total is not None else None
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            time.sleep(3.0)
    raise last_err if last_err else RuntimeError("arxiv unknown error")


def fetch_arxiv() -> dict:
    out = {}
    ytd = time.strftime("%Y-01-01")
    for topic, q in ARXIV_TOPICS.items():
        entry: dict = {}
        for key, start in (("total", None), ("since_jan", ytd)):
            try:
                entry[key] = arxiv_count(q, start=start)
            except Exception as exc:  # noqa: BLE001
                entry[key] = None
                entry[key + "_error"] = repr(exc)
            time.sleep(3.5)  # arXiv 要求请求间隔
        out[topic] = entry
    return out


def fetch_hf() -> dict:
    out = {}
    for tag in ["text-generation", "feature-extraction", "text-to-image"]:
        try:
            url = ("https://huggingface.co/api/models?filter=" + urllib.parse.quote(tag)
                   + "&limit=1000&full=false&config=false")
            out[tag] = {"sampled": len(json.loads(safe_fetch(url)))}
        except Exception as exc:  # noqa: BLE001
            out[tag] = {"error": repr(exc)}
        time.sleep(0.5)
    return out


def main() -> None:
    result = {"fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    # arXiv 限流敏感，放在最前、加大间隔
    try:
        result["arxiv"] = fetch_arxiv()
    except Exception as exc:  # noqa: BLE001
        result["arxiv"] = {"error": repr(exc)}
    result["github"] = fetch_github()
    try:
        result["huggingface"] = fetch_hf()
    except Exception as exc:  # noqa: BLE001
        result["huggingface"] = {"error": repr(exc)}
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=1))
    manifest = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else []
    manifest = [m for m in manifest if m["source"] != "Aux signals (GitHub/arXiv/HF)"]
    manifest.append({
        "source": "Aux signals (GitHub/arXiv/HF)",
        "url": "https://api.github.com, https://export.arxiv.org/api, https://huggingface.co/api",
        "fetched_at": result["fetched_at"],
        "license_note": "public APIs; GitHub data under each repo's license; arXiv metadata under arXiv ToS",
        "file": "data/raw/misc/aux_signals.json",
    })
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=1))
    ok_gh = sum(1 for v in result["github"].values() if "stars" in v)
    arxiv_part = result.get("arxiv", {})
    print(f"DONE aux github_ok={ok_gh}/{len(REPOS)} arxiv={list(arxiv_part) if isinstance(arxiv_part, dict) else 'err'}")


if __name__ == "__main__":
    main()
