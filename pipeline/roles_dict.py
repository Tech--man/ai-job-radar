"""岗位分类体系：9 个目标岗位 + ml-research 兜底 + other。

分类逻辑（build_db.classify_job）：
1. 标题命中 title_keywords → 权重 4.0/词
2. 正文命中 text_keywords → 权重 1.0/词（按「命中不同关键词数」计，防长文刷分）
3. 主岗位 = 得分最高且 ≥ 阈值；多标签 = 得分 ≥ 主得分 × 0.6
4. AI 相关性门槛：必须命中 ai_gate（标题或正文），否则标记 non-ai

关键词默认按整词匹配（\\b 包裹）；需要前后缀通配的写进 *_raw（原样正则）。
"""

ROLES = [
    {
        "id": "llm-app",
        "name_en": "LLM Application Engineer",
        "name_zh": "LLM 应用工程师",
        "title_keywords": ["llm engineer", "llm developer", "ai engineer", "ai developer",
                           "generative ai engineer", "genai engineer", "ai application engineer",
                           "applied ai engineer", "gen ai engineer", "ai software engineer",
                           "ai programmer", "llm ops"],
        "text_keywords": ["llm", "llms", "generative ai", "genai", "gen ai", "chatbot",
                          "gpt-4", "gpt-5", "gpt-4o", "claude", "gemini", "copilot",
                          "ai features", "ai product", "openai api", "prompt",
                          "conversational ai", "ai assistant", "foundation model"],
        "text_keywords_raw": [r"\bai[- ](?:powered|first|native|driven|enabled)\b"],
        "gate": True,
    },
    {
        "id": "agent",
        "name_en": "Agent Engineer",
        "name_zh": "Agent 工程师",
        "title_keywords": ["agent engineer", "ai agent", "agentic", "autonomous agents",
                           "agent developer"],
        "text_keywords": ["agent", "agents", "agentic", "multi-agent", "tool use",
                          "function calling", "mcp", "langgraph", "crewai", "autogen",
                          "agent orchestration", "autonomous", "computer use"],
        "text_keywords_raw": [],
        "gate": True,
    },
    {
        "id": "rag",
        "name_en": "RAG / Search Engineer",
        "name_zh": "RAG 工程师",
        "title_keywords": ["rag engineer", "search engineer", "retrieval engineer",
                           "knowledge engineer", "search relevance"],
        "text_keywords": ["rag", "retrieval augmented", "vector database", "vector db",
                          "embeddings", "semantic search", "knowledge base", "knowledge graph",
                          "rerank", "hybrid search", "chunking", "document processing",
                          "pinecone", "qdrant", "weaviate", "milvus", "pgvector"],
        "text_keywords_raw": [],
        "gate": True,
    },
    {
        "id": "mlops",
        "name_en": "AI Infra / MLOps",
        "name_zh": "AI Infra / MLOps 工程师",
        "title_keywords": ["mlops", "ml infrastructure", "ml platform", "ai infrastructure",
                           "ai infra", "inference engineer", "ml ops", "platform engineer",
                           "gpu engineer", "ml sre", "performance engineer"],
        "text_keywords": ["kubernetes", "gpu", "gpus", "vllm", "inference", "model serving",
                          "distributed training", "tensorrt", "cuda", "triton", "ray",
                          "latency", "throughput", "cluster", "terraform", "infrastructure"],
        "text_keywords_raw": [],
        "gate": True,
    },
    {
        "id": "ai-pm",
        "name_en": "AI Product Manager",
        "name_zh": "AI 产品经理",
        "title_keywords": ["product manager", "product management", "technical product",
                           "product owner", "head of product", "product lead"],
        "text_keywords": ["roadmap", "user research", "stakeholders", "product strategy",
                          "prd", "prioritization", "product metrics", "user experience",
                          "customer feedback", "discovery", "wireframe", "usability"],
        "text_keywords_raw": [r"\bproduct managers?\b"],
        "gate": True,
    },
    {
        "id": "ai-security",
        "name_en": "AI Security / Safety",
        "name_zh": "AI 安全工程师",
        "title_keywords": ["ai security", "llm security", "ai safety", "security engineer",
                           "safety engineer", "red team", "trust and safety", "adversarial"],
        "text_keywords": ["prompt injection", "jailbreak", "red teaming", "threat model",
                          "adversarial", "guardrails", "ai safety", "model safety",
                          "abuse", "misuse", "penetration testing", "vulnerability"],
        "text_keywords_raw": [],
        "gate": True,
    },
    {
        "id": "data-eng",
        "name_en": "Data Engineer (AI)",
        "name_zh": "数据工程师（AI 方向）",
        "title_keywords": ["data engineer", "data engineering", "analytics engineer",
                           "data platform"],
        "text_keywords": ["etl", "data pipeline", "pipelines", "warehouse", "dbt", "airflow",
                          "spark", "kafka", "data quality", "data modeling", "ingestion",
                          "snowflake", "databricks", "data platform"],
        "text_keywords_raw": [],
        "gate": True,
    },
    {
        "id": "ai-solutions",
        "name_en": "AI Solutions Engineer",
        "name_zh": "AI 解决方案工程师",
        "title_keywords": ["solutions architect", "solutions engineer", "solution engineer",
                           "forward deployed", "customer engineer", "implementation engineer",
                           "field engineer", "solutions consultant"],
        "text_keywords": ["proof of concept", "poc", "customer success", "onboarding",
                          "technical account", "solutions", "integrations", "consulting",
                          "implementation"],
        "text_keywords_raw": [r"\bforward[- ]deployed\b"],
        "gate": True,
    },
    {
        "id": "ai-growth",
        "name_en": "AI Sales / Growth",
        "name_zh": "AI 销售 / 增长",
        "title_keywords": ["sales engineer", "account executive", "growth", "business development",
                           "revenue", "gtm", "sales development", "demand generation",
                           "partnerships", "head of sales", "account manager"],
        "text_keywords": ["quota", "arr", "outbound", "prospects", "closing", "crm",
                          "hubspot", "salesforce", "cold outreach", "book meetings",
                          "revenue targets", "pipeline generation", "lead generation"],
        "text_keywords_raw": [],
        "gate": True,
    },
    {
        "id": "ml-research",
        "name_en": "ML Research / Applied Scientist",
        "name_zh": "ML 研究 / 算法工程师",
        "title_keywords": ["research scientist", "research engineer", "applied scientist",
                           "ml scientist", "algorithm engineer", "research intern",
                           "machine learning scientist", "research lead"],
        "text_keywords": ["papers", "publications", "arxiv", "state-of-the-art", "sota",
                          "phd", "benchmarks", "pretraining", "post-training",
                          "reinforcement learning", "research"],
        "text_keywords_raw": [r"\bnovel (?:methods?|approaches?|architectures?)\b"],
        "gate": True,
    },
]

ROLE_BY_ID = {r["id"]: r for r in ROLES}

# AI 相关性门槛：命中任一才视为 AI 岗位（整词匹配 + raw 正则）
AI_GATE = [
    "ai", "artificial intelligence", "llm", "llms", "gpt", "ml", "machine learning",
    "deep learning", "genai", "generative", "gen ai", "agent", "agents", "agentic", "rag",
    "nlp", "computer vision", "prompt", "chatbot", "copilot", "openai", "anthropic",
    "claude", "gemini", "foundation model", "diffusion", "transformer", "neural",
    "embedding", "embeddings", "vector", "inference", "autonomous", "voice ai",
    "conversational", "multimodal", "reinforcement learning", "ai assistant",
]
AI_GATE_RAW = [r"\bfine[- ]?tun", r"\bai[- ](?:powered|first|native|driven|enabled)\b"]

ROLE_PROFILES = ["llm-app", "agent", "rag", "mlops", "ai-pm", "data-eng"]  # 建站画像岗位
