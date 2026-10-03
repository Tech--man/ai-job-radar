# 数据字典

## jobs 表（data/ai_jobs.sqlite）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER | 行主键 |
| source | TEXT | 来源：hn / remoteok / wwr |
| source_id | TEXT | 来源内标识（HN 评论 objectID 等） |
| posted_date | TEXT | YYYY-MM-DD（HN 取评论时间；WWR 取 pubDate） |
| month | TEXT | YYYY-MM（月度帖归属，用于趋势） |
| company / company_norm | TEXT | 自述公司名 / 归一名（去法律后缀、小写） |
| title | TEXT | 启发式抽取的职位名（HN 无标题字段，取首行分段） |
| is_ai | INTEGER | 1=命中 AI 门槛关键词 |
| role | TEXT | 主分类（10 类之一，见 roles_dict.py） |
| roles_all | TEXT(JSON) | 多标签（得分 ≥ 主得分 60% 的岗位族） |
| skills | TEXT(JSON) | 命中技能 id 列表（字典见 skills_dict.py） |
| is_remote / remote_kind | INTEGER / TEXT | 远程提及 / remote·hybrid·remote+hybrid·unknown |
| city / country | TEXT | 命中 40 城市词典的首个城市 |
| salary_min_usd / salary_max_usd | REAL | 归一化年薪区间（USD）；**NULL = 未披露，不插补** |
| salary_currency / salary_period | TEXT | 原始币种 / hourly·daily·monthly·annual |
| salary_raw | TEXT | 命中的原文片段（溯源用） |
| salary_conf | TEXT | parsed / assumed-k / remoteok-structured |
| text_clean | TEXT | 清洗后正文（≤6000 字符） |
| url | TEXT | 原帖链接（HN 帖可由 source_id 拼出） |
| dedup_key | TEXT | SHA-256(source·month·company_norm·title_norm) |

## analysis 产物（data/processed/analysis/）

- `overview.json`：KPI、岗位分布、Top 技能、辅助信号（GitHub/arXiv/HF）
- `profiles/{role}.json`：画像岗位的技能/薪资/城市/公司/标题样本/重合度
- `skills.json`：技能全集 + 共现 Top + 噪音候选（freq_pct、delta_pct、n_with、confidence、specificity）
- `salary.json`：by_role / by_skill_top / by_city / by_remote / by_stage（n<8 → median=null）
- `companies.json`：帖次数 ≥3 的公司榜
- `trend.json`：月度帖数、AI 占比、分岗位计数、含薪样本数

## 置信度标签

- premium `confidence`：low（n<20）/ medium（20–39）/ high（≥40）/ insufficient（n<8，不计算）
- `salary_conf=assumed-k`："$150-200" 这类裸数值按「千」解释的口径标记
