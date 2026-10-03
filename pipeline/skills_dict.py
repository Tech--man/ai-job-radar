"""技能字典：85+ 技能，含抽取正则。

- 抽取在 lowercased 文本上进行，patterns 为不区分大小写正则。
- 每条 pattern 可溯源；误报控制策略见 docs/methodology.md。
- core_for: 该技能是哪些目标岗位的核心技能（用于路线生成器缺口分析），["*"] 表示通用基础。
"""

CATEGORIES = {
    "lang": "语言与通用",
    "ml-core": "机器学习核心",
    "llm-framework": "LLM 应用框架",
    "rag": "RAG 与检索",
    "agent": "Agent 与工具调用",
    "serving": "推理服务与性能",
    "training": "训练与微调",
    "cloud": "云与 DevOps",
    "data": "数据工程",
    "eval": "评估与质量",
    "security": "安全与合规",
    "multimodal": "多模态",
    "product": "产品与业务",
    "frontend": "前端与原型",
}

# (id, en, zh, category, patterns, core_for)
SKILLS = [
    # ---------- 语言与通用 ----------
    ("python", "Python", "Python", "lang", [r"\bpython\b"], ["*"]),
    ("typescript", "TypeScript", "TypeScript", "lang", [r"\btypescript\b"], ["llm-app", "agent"]),
    ("javascript", "JavaScript", "JavaScript", "lang", [r"\bjavascript\b"], ["llm-app"]),
    ("golang", "Go", "Go", "lang", [r"\bgolang\b"], ["mlops", "data-eng"]),
    ("rust", "Rust", "Rust", "lang", [r"\brust\b"], ["mlops"]),
    ("java", "Java", "Java", "lang", [r"\bjava\b(?!\s*script)"], ["data-eng", "ai-solutions"]),
    ("cpp", "C++", "C++", "lang", [r"\bc\+\+\b"], ["mlops", "ml-research"]),
    ("csharp", "C#/.NET", "C#/.NET", "lang", [r"\bc#\b|\b\.net\b"], ["ai-solutions"]),
    ("sql", "SQL", "SQL", "lang", [r"\bsql\b"], ["data-eng", "rag", "ai-pm"]),
    ("bash", "Bash/Shell", "Bash/Shell", "lang", [r"\bbash\b|\bshell script"], ["*"]),
    # ---------- 机器学习核心 ----------
    ("pytorch", "PyTorch", "PyTorch", "ml-core", [r"\bpytorch\b"], ["ml-research", "llm-app"]),
    ("tensorflow", "TensorFlow/Keras", "TensorFlow/Keras", "ml-core", [r"\btensorflow\b|\bkeras\b"], ["ml-research"]),
    ("jax", "JAX", "JAX", "ml-core", [r"\bjax\b"], ["ml-research"]),
    ("scikit-learn", "scikit-learn", "scikit-learn", "ml-core", [r"\bscikit[- ]learn\b|\bsklearn\b"], ["llm-app", "data-eng"]),
    ("numpy", "NumPy", "NumPy", "ml-core", [r"\bnumpy\b"], ["llm-app"]),
    ("pandas", "pandas", "pandas", "ml-core", [r"\bpandas\b"], ["data-eng", "llm-app"]),
    ("hf-transformers", "Hugging Face Transformers", "Hugging Face Transformers", "ml-core",
     [r"\bhugging ?face\b|\bhf transformers\b|\btransformers\b"], ["llm-app", "rag", "ml-research"]),
    ("ml-fundamentals", "ML/DL 基础", "机器学习/深度学习基础", "ml-core",
     [r"\bmachine learning\b|\bdeep learning\b|\bneural network"], ["*"]),
    ("llm-fundamentals", "LLM 原理", "LLM 原理", "ml-core",
     [r"\bllms?\b|\blarge language model"], ["*"]),
    ("transformer-arch", "Transformer 架构", "Transformer 架构", "ml-core", [r"\btransformer architecture\b|\battention mechanism\b"], ["ml-research"]),
    # ---------- LLM 应用框架 ----------
    ("langchain", "LangChain", "LangChain", "llm-framework", [r"\blangchain\b"], ["llm-app", "rag"]),
    ("langgraph", "LangGraph", "LangGraph", "llm-framework", [r"\blanggraph\b"], ["agent", "llm-app"]),
    ("llama-index", "LlamaIndex", "LlamaIndex", "llm-framework", [r"\bllama ?index\b|\bllamaindex\b"], ["rag", "llm-app"]),
    ("dspy", "DSPy", "DSPy", "llm-framework", [r"\bdspy\b"], ["llm-app"]),
    ("haystack", "Haystack", "Haystack", "llm-framework", [r"\bhaystack\b"], ["rag"]),
    ("semantic-kernel", "Semantic Kernel", "Semantic Kernel", "llm-framework", [r"\bsemantic kernel\b"], ["llm-app"]),
    ("autogen", "AutoGen", "AutoGen", "llm-framework", [r"\bautogen\b"], ["agent"]),
    ("crewai", "CrewAI", "CrewAI", "llm-framework", [r"\bcrew ?ai\b"], ["agent"]),
    ("openai-api", "OpenAI API", "OpenAI API", "llm-framework", [r"\bopenai\b"], ["llm-app", "agent", "rag"]),
    ("anthropic-api", "Anthropic/Claude API", "Anthropic/Claude API", "llm-framework", [r"\banthropic\b|\bclaude api\b"], ["llm-app", "agent"]),
    ("litellm", "LiteLLM", "LiteLLM", "llm-framework", [r"\blitellm\b"], ["llm-app", "mlops"]),
    ("ai-sdk", "Vercel AI SDK", "Vercel AI SDK", "llm-framework", [r"\bvercel ai\b|\bai sdk\b"], ["llm-app"]),
    # ---------- RAG 与检索 ----------
    ("rag", "RAG", "RAG（检索增强生成）", "rag", [r"\brag\b|\bretrieval[- ]augmented\b"], ["rag", "llm-app"]),
    ("vector-db", "向量数据库", "向量数据库（概念）", "rag", [r"\bvector (?:database|databases|db|store|search)\b"], ["rag", "llm-app"]),
    ("embeddings", "Embeddings", "Embeddings/向量化", "rag", [r"\bembedding"], ["rag", "llm-app"]),
    ("semantic-search", "语义检索", "语义检索", "rag", [r"\bsemantic search\b|\bhybrid search\b|\bsparse[- ]dense\b"], ["rag"]),
    ("reranking", "Reranking", "重排序/Rerank", "rag", [r"\brerank"], ["rag"]),
    ("chunking", "Chunking", "文档切分", "rag", [r"\bchunk(?:ing|s| sizes?)\b"], ["rag"]),
    ("pinecone", "Pinecone", "Pinecone", "rag", [r"\bpinecone\b"], ["rag"]),
    ("weaviate", "Weaviate", "Weaviate", "rag", [r"\bweaviate\b"], ["rag"]),
    ("qdrant", "Qdrant", "Qdrant", "rag", [r"\bqdrant\b"], ["rag"]),
    ("milvus", "Milvus", "Milvus", "rag", [r"\bmilvus\b|\bzilliz\b"], ["rag"]),
    ("pgvector", "pgvector", "pgvector", "rag", [r"\bpgvector\b|\bpostgres.*vector|vector.*postgres"], ["rag"]),
    ("elasticsearch", "Elasticsearch/OpenSearch", "Elasticsearch/OpenSearch", "rag", [r"\belastic ?search\b|\bopensearch\b"], ["rag", "data-eng"]),
    ("faiss", "FAISS", "FAISS", "rag", [r"\bfaiss\b"], ["rag"]),
    ("chromadb", "ChromaDB", "ChromaDB", "rag", [r"\bchroma ?db\b"], ["rag"]),
    ("doc-pipeline", "文档处理管线", "文档处理/解析管线", "rag", [r"\bdocument (?:processing|parsing|ingestion|understanding)\b|\bocr\b|\bunstructured\b"], ["rag"]),
    # ---------- Agent 与工具调用 ----------
    ("mcp", "MCP", "MCP（模型上下文协议）", "agent", [r"\bmcp\b|model context protocol"], ["agent", "llm-app"]),
    ("function-calling", "Function/Tool Calling", "函数/工具调用", "agent", [r"\bfunction (?:calling|calls?)\b|\btool (?:calling|calls?|use)\b"], ["agent", "llm-app"]),
    ("multi-agent", "Multi-Agent", "多智能体系统", "agent", [r"\bmulti[- ]agent\b|\bswarm\b"], ["agent"]),
    ("agent-workflow", "Agent 编排", "Agent 编排/工作流", "agent", [r"\bagent(?:ic)? (?:workflow|orchestrat|systems?|frameworks?)\b|\bworkflow (?:orchestrat|engine|automation)\b"], ["agent", "llm-app"]),
    ("prompt-engineering", "Prompt Engineering", "提示词工程", "agent", [r"\bprompt engineering\b|\bprompt design\b|\bprompting\b"], ["llm-app", "agent"]),
    ("structured-output", "Structured Output", "结构化输出/JSON mode", "agent", [r"\bstructured (?:output|json)\b|\bjson mode\b|\bschema[- ]constrained\b"], ["llm-app", "agent"]),
    ("llm-observability", "LLM 可观测", "LLM 可观测（LangSmith/Langfuse 等）", "agent", [r"\blangsmith\b|\blangfuse\b|\bllm (?:observability|tracing)\b|\bopentelemetry\b"], ["llm-app", "agent"]),
    ("guardrails", "Guardrails", "输出护栏/校验", "agent", [r"\bguardrails?\b|\boutput (?:validation|parsing)\b|\bpydantic\b"], ["llm-app", "agent"]),
    ("agent-memory", "Memory 系统", "Agent 记忆系统", "agent", [r"\bmemory (?:management|system|layer)\b|\blong[- ]term memory\b"], ["agent"]),
    # ---------- 推理服务与性能 ----------
    ("docker", "Docker", "Docker/容器化", "serving", [r"\bdocker\b|\bcontaineri[sz]"], ["*"]),
    ("kubernetes", "Kubernetes", "Kubernetes", "serving", [r"\bkubernetes\b|\bk8s\b"], ["mlops"]),
    ("vllm", "vLLM", "vLLM", "serving", [r"\bvllm\b"], ["mlops"]),
    ("sglang", "SGLang", "SGLang", "serving", [r"\bsglang\b"], ["mlops"]),
    ("triton-server", "Triton Inference Server", "Triton Inference Server", "serving", [r"\btriton (?:inference )?server\b"], ["mlops"]),
    ("tensorrt", "TensorRT", "TensorRT/TensorRT-LLM", "serving", [r"\btensor[- ]?rt\b"], ["mlops"]),
    ("onnx", "ONNX", "ONNX", "serving", [r"\bonnx\b"], ["mlops"]),
    ("python-web", "FastAPI/Flask", "FastAPI/Flask 等 Web 框架", "serving", [r"\bfastapi\b|\bflask\b|\bdjango\b"], ["llm-app"]),
    ("grpc", "gRPC", "gRPC", "serving", [r"\bgrpc\b"], ["mlops"]),
    ("inference-opt", "推理优化", "推理优化/降本", "serving", [r"\binference (?:optimi[sz]ation|latency|performance|cost|speed)\b|\bmodel serving\b|\blow[- ]latency serving\b"], ["mlops"]),
    ("quantization", "量化", "模型量化", "serving", [r"\bquantiz"], ["mlops", "ml-research"]),
    ("gpu", "GPU", "GPU 工程", "serving", [r"\bgpus?\b"], ["mlops"]),
    # ---------- 训练与微调 ----------
    ("fine-tuning", "Fine-tuning", "微调", "training", [r"\bfine[- ]?tun"], ["llm-app", "ml-research"]),
    ("lora", "LoRA/PEFT", "LoRA/QLoRA/PEFT", "training", [r"\b(?:q)?lora\b|\bpeft\b"], ["llm-app", "ml-research"]),
    ("rlhf", "RLHF/DPO", "RLHF/DPO/对齐", "training", [r"\brlhf\b|\bdpo\b|\bgrpo\b|\bpreference (?:optimization|learning)\b|\breinforcement learning from human"], ["ml-research"]),
    ("distributed-training", "分布式训练", "分布式训练（DeepSpeed/FSDP）", "training", [r"\bdeepspeed\b|\bfsdp\b|\bdistributed training\b|\bmegatron\b"], ["ml-research", "mlops"]),
    ("cuda", "CUDA", "CUDA", "training", [r"\bcuda\b"], ["mlops", "ml-research"]),
    ("triton-lang", "Triton(语言)", "Triton（GPU 编程语言）", "training", [r"\btriton\b(?!\s*(?:inference\s+)?server)"], ["mlops", "ml-research"]),
    ("pretraining", "预训练", "预训练/继续训练", "training", [r"\bpre[- ]?train|\bcontinued pre[- ]training\b|\btraining (?:large )?(?:language |foundation )?models?\b|\bmodel training\b"], ["ml-research"]),
    ("data-curation", "数据标注/清洗", "训练数据清洗与标注", "training", [r"\bdata (?:curation|annotation|labeling)\b|\binstruction tuning\b|\bsynthetic data\b"], ["ml-research"]),
    # ---------- 云与 DevOps ----------
    ("aws", "AWS", "AWS", "cloud", [r"\baws\b|amazon web services"], ["*"]),
    ("gcp", "GCP", "Google Cloud", "cloud", [r"\bgcp\b|google cloud"], ["*"]),
    ("azure", "Azure", "Azure", "cloud", [r"\bazure\b"], ["*"]),
    ("terraform", "Terraform/IaC", "Terraform/IaC", "cloud", [r"\bterraform\b|\biac\b|\bpulumi\b"], ["mlops"]),
    ("ci-cd", "CI/CD", "CI/CD", "cloud", [r"\bci/?cd\b"], ["mlops", "llm-app"]),
    ("linux", "Linux", "Linux", "cloud", [r"\blinux\b"], ["mlops"]),
    ("observability", "监控可观测", "监控/可观测性", "cloud", [r"\bmonitoring\b|\bobservability\b|\bdatadog\b|\bprometheus\b|\bgrafana\b"], ["mlops"]),
    # ---------- 数据工程 ----------
    ("spark", "Spark", "Spark", "data", [r"\b(?:apache )?spark\b|\bpyspark\b"], ["data-eng"]),
    ("airflow", "Airflow/Dagster", "Airflow/Dagster/Prefect", "data", [r"\bairflow\b|\bdagster\b|\bprefect\b"], ["data-eng"]),
    ("kafka", "Kafka/Flink", "Kafka/Flink 流处理", "data", [r"\bkafka\b|\bflink\b"], ["data-eng"]),
    ("dbt", "dbt", "dbt", "data", [r"\bdbt\b"], ["data-eng"]),
    ("etl", "ETL/数据管线", "ETL/数据管线", "data", [r"\betl\b|\belt\b|\bdata pipeline"], ["data-eng"]),
    ("warehouse", "数仓", "Snowflake/BigQuery/Databricks/数仓", "data", [r"\bsnowflake\b|\bbigquery\b|\bdatabricks\b|\bdata warehouse\b|\bduckdb\b"], ["data-eng"]),
    # ---------- 评估与质量 ----------
    ("llm-eval", "LLM 评估", "LLM 评估/Evals", "eval", [r"\b(?:llm |model |gen[- ]?ai |ai )?(?:evals?\b|evaluation framework|evaluation pipeline|benchmark)"], ["llm-app", "agent", "rag"]),
    ("rag-eval", "RAG 评估", "RAG 评估（RAGAS 等）", "eval", [r"\bragas\b|\bdeep[- ]?eval\b|\bbraintrust\b|\brag evaluation\b"], ["rag"]),
    ("ab-testing", "A/B 测试", "A/B 测试", "eval", [r"\ba/?b test|\bexperimentation platform\b"], ["ai-pm", "ai-growth"]),
    # ---------- 安全与合规 ----------
    ("ai-security", "AI 安全", "AI 安全/模型安全", "security", [r"\bai security\b|\bllm security\b|\bai safety\b|\bmodel safety\b|\bresponsible ai\b"], ["ai-security"]),
    ("prompt-injection", "Prompt 注入防护", "Prompt 注入/越狱防护", "security", [r"\bprompt injection\b|\bjailbreak|\bred[- ]?team"], ["ai-security"]),
    ("privacy-compliance", "隐私合规", "隐私/合规（GDPR/SOC2）", "security", [r"\bgdpr\b|\bdata privacy\b|\bsoc ?2\b|\bhipaa\b|\bcompliance\b"], ["ai-security", "ai-solutions"]),
    # ---------- 多模态 ----------
    ("multimodal", "多模态", "多模态/VLM", "multimodal", [r"\bmultimodal\b|\bmulti[- ]modal\b|\bvlms?\b|\bvision[- ]language\b"], ["llm-app", "ml-research"]),
    ("image-gen", "图像生成", "图像生成/Diffusion", "multimodal", [r"\bdiffusion\b|\bimage generation\b|\bmidjourney\b|\bcomfyui\b|\bcontrolnet\b"], ["llm-app"]),
    ("speech", "语音", "语音（ASR/TTS）", "multimodal", [r"\bwhisper\b|\basr\b|\bspeech[- ](?:to[- ]text|recognition)\b|\btts\b|\bvoice (?:agent|assistant|ai)\b"], ["llm-app"]),
    # ---------- 产品与业务 ----------
    ("product-management", "产品管理", "产品管理", "product", [r"\bproduct management\b|\bproduct manager\b|\broadmap|\bprd\b|\bprioriti[sz]"], ["ai-pm"]),
    ("user-research", "用户研究", "用户研究/客户访谈", "product", [r"\buser research\b|\bcustomer (?:research|interview|discovery)\b|\bdiscovery\b"], ["ai-pm"]),
    ("analytics", "数据分析", "数据分析/埋点", "product", [r"\banalytics\b|\bamplitude\b|\bmixpanel\b|\bsql\b"], ["ai-pm", "ai-growth"]),
    ("gtm", "GTM", "GTM/市场进入", "product", [r"\bgtm\b|go[- ]to[- ]market"], ["ai-growth", "ai-solutions"]),
    ("solution-arch", "解决方案架构", "解决方案架构/售前", "product", [r"\bsolutions? (?:architect|engineering|engineer)\b|\bforward[- ]deployed\b|\bpre[- ]?sales\b|\bsales engineer\b|\bimplementation engineer\b"], ["ai-solutions"]),
    ("customer-facing", "客户沟通", "客户沟通/企业交付", "product", [r"\bcustomers?\b|\benterprise (?:customers?|clients?)\b|\bstakeholder"], ["ai-solutions", "ai-pm", "ai-growth"]),
    # ---------- 前端与原型 ----------
    ("react", "React/Next.js", "React/Next.js", "frontend", [r"\breact\b|\bnext\.?js\b"], ["llm-app"]),
    ("prototyping", "原型工具", "Streamlit/Gradio 快速原型", "frontend", [r"\bstreamlit\b|\bgradio\b"], ["llm-app", "ai-pm"]),
]

SKILL_BY_ID = {s[0]: s for s in SKILLS}


def skill_dicts():
    """导出为纯 dict 列表。"""
    return [
        {
            "id": sid, "name_en": en, "name_zh": zh, "category": cat,
            "patterns": pats, "core_for": core,
        }
        for (sid, en, zh, cat, pats, core) in SKILLS
    ]
