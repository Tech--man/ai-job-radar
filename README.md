# 📡 AI 职业行情雷达 + 转型路线生成器（AI Job Radar）

一个纯公开数据驱动的研究型 MVP：回答四个问题——

1. **AI 相关岗位到底在招什么？**
2. **哪些技能溢价最高、哪些是噪音？**
3. **哪些公司在密集招 AI 岗？**
4. **从当前背景转到目标 AI 岗位，最短学习路径和作品集是什么？**

**在线访问**：`https://tech--man.github.io/ai-job-radar/`（GitHub Pages，静态站点）
**本地运行**：

```bash
# 仅看站点（已构建产物）
cd site && npm run preview          # 或: python3 -m http.server -d dist 8155

# 完整复现（抓取 → 清洗 → 分析 → 建站）
cd pipeline
python3 fetch_hn.py && python3 fetch_remoteok.py && python3 fetch_wwr.py && python3 fetch_aux.py && python3 fetch_echarts.py
python3 build_db.py && python3 analyze.py && python3 export_web.py
cd ../site && npm install && npm run build
```

## 数据快照（2026-10-04 抓取）

| 指标 | 数值 |
|---|---|
| 岗位帖（去重后） | 4,142 条（HN 3,965 / RemoteOK 98 / WWR 79） |
| AI 相关岗位 | 2,619 条（整词关键词门槛 + 分类得分 ≥3） |
| 含可解析薪资 | 658 条（25.1%；其余**显式标注缺失，不插补**） |
| 技能字典 | 101 项（正则别名可溯源），51 项有溢价数据 |
| 覆盖月份 | 2025-10 → 2026-10（HN 13 期月度帖） |
| 目标岗位画像 | 6 个（LLM 应用 / Agent / RAG / Infra-MLOps / AI 产品 / 数据工程） |

## 网站功能

- **总览**：岗位分布、月度趋势（AI 帖占比 57.8% → 72.5%）、溢价 Top/垫底、薪资中位速览
- **岗位画像 ×6**：技能要求频率、薪资区间（含样本量与覆盖率）、城市、远程比例、公司、样本标题、岗位重合度（Jaccard）
- **技能图谱**：101 项技能全表（分类/出现率/溢价/置信度）、共现 Top 15、噪音技能候选
- **薪资雷达**：按岗位/技能/城市/办公形态/公司类型；**缺失即标注「样本不足」，绝不编造**
- **公司热度**：帖次数 ≥3 的公司榜 + 主要招聘方向
- **路线生成器**：8 种当前背景 × 6 目标岗位 → 缺口分析、8 周学习计划、3 个作品集项目、简历关键词、面试题库，一键下载 Markdown
- **研究报告 / 晨间简报 / 方法与来源**：完整口径、局限与免责声明

## 仓库结构

```
pipeline/          # 数据管线（Python 标准库，零第三方依赖）
  config.py        #   受限出站请求（https-only、host 白名单、公网 IP 校验、禁重定向、防 DNS rebinding）
  skills_dict.py   #   101 项技能字典（含正则别名与分类）
  roles_dict.py    #   10 类岗位分类体系 + AI 相关性门槛
  fetch_*.py       #   采集：HN Algolia / RemoteOK / WWR RSS / GitHub+arXiv+HF / ECharts
  build_db.py      #   清洗、薪资解析、技能抽取、分类、去重 → SQLite（参数绑定）
  analyze.py       #   频次/共现/溢价/重合度/公司热度/趋势 → analysis/*.json
  roadmaps.py      #   转型路线内容库（6 岗位 × 8 周计划/作品集/关键词/面试题）
  export_web.py    #   导出站点数据
site/              # Astro 5 + Tailwind 4 + ECharts 5 静态站（14 页，移动端适配）
data/
  raw/             # 原始抓取物 + SOURCE_MANIFEST.json（来源 URL/时间/条款）
  ai_jobs.sqlite   # 结构化岗位库
  processed/       # jobs.json + analysis/*.json
logs/progress.md   # 执行日志与 checkpoint
docs/              # 数据字典、方法论（见站内「方法与来源」页）
```

## 核心口径（详见站内「方法与来源」）

- **技能溢价** = 同池（AI 岗且有解析薪资）内，含该技能帖薪资中位数 − 不含帖中位数；n<8 不计算；相关 ≠ 因果。
- **薪资解析**：仅解析带货币标识的自述区间；静态汇率粗折；时薪×1750h、月薪×12；超出 $25k–$900k/年 丢弃。
- **画像成员** = 主分类或多标签命中（RAG 等组合岗位依赖多标签口径）。
- **「噪音技能」** = 高频（≥5%）∧ 溢价 ≤3% ∧ 岗位区分度低（分布熵）。指「不构成差异化」，**不等于不需要**。

## 已知局限

样本偏英文技术社区（HN 为主）；薪资自选择偏差；规则分类有「通用 AI 工程」大桶（59.7%）；RemoteOK 本期 API 仅返回约百条；转型路线为策划内容（技能排序数据驱动，计划本身非统计）。完整列表见站内方法页。

## 免责声明

研究性 MVP，仅供学习参考，不构成求职/招聘/投资建议。岗位内容版权归原作者与平台；仅聚合统计、不存作者身份信息；来源方可提 issue 退出数据集。软件按现状提供。

## License

代码 MIT；数据集 CC BY-SA 4.0（聚合统计，含来源清单）。
