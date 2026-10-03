# 执行日志 / Progress Log

项目：AI 职业行情雷达 + 转型路线生成器（AI Job Radar）
T+0 = 2026-10-04 00:05 (+0800)

## 日志约定
- 每完成一个阶段追加一条：时间戳、阶段、已完成、遇到问题、下一步。
- checkpoint 快照存 `logs/checkpoints/CKPT-*.md`。
- 数据溯源记录在 `data/raw/SOURCE_MANIFEST.json`（来源 URL、抓取时间、许可证/条款）。

## T+0 00:05 环境检查与项目骨架
- 已完成：环境确认（Python 3.14.7 / Node 22.22.3 / npm 10.9.8 / git 2.54 / gh 已登录 Tech--man）；三个核心数据源连通性验证（hn.algolia.com 200，remoteok.com/api 200，weworkremotely.com RSS 200）；目录骨架创建；git init。
- 遇到问题：无。
- 下一步：写入技能字典（≥50 技能）与 9 类岗位分类体系、数据字典，随后开始数据采集。

## T+0:28 数据采集完成（00:33）
- 已完成：
  - HN Who is Hiring：13 个正式月度帖（2025-10 → 2026-10）+ 1 个自由职业版帖（0 评论，入库时过滤），共 3998 条顶层岗位帖，原文落盘 data/raw/hn/。
  - RemoteOK API：99 条（其中约 89 条 AI 相关）。
  - WeWorkRemotely RSS：4 类目共 81 条（programming 25 / devops 17 / product 16 / design 23）。
  - 辅助源：GitHub 21 个 AI 生态仓库 star 数；arXiv 3 主题论文总量（RAG 6041 / LLM+Agent 13776 / RLHF-DPO 2050；带日期过滤的查询被 arXiv 网关 500 拒绝，仅记录总量）；HF 按 filter 抽样。
  - SOURCE_MANIFEST.json 记录全部来源 URL/时间/条款。
- 遇到问题（均已解决或记录）：
  1. 本机 TUN 代理 fake-IP（198.18.0.0/15）触发私网拦截 → config.safe_fetch 单独识别该段放行，回环/链路本地（含云元数据）仍硬拒绝。
  2. Mimosa 拦截 ElementTree 解析不可信 XML → 增加 parse_xml_safely（拒 DOCTYPE/ENTITY+限大小）；拦截裸 urllib SSRF 面 → 出站统一收敛到 safe_fetch（禁重定向+固定 IP 建连）。
  3. RemoteOK API 现仅返回约 100 条（上游行为），记录在案。
  4. arXiv 带日期过滤查询 500（curl 可复现成功，我们的客户端稳定 500），放弃分片，仅用总量。
- 下一步：build_db.py 清洗/技能抽取/薪资解析/分类/去重 → SQLite。

## T+0:41 清洗与分析完成（00:46）
- 已完成：4142 条结构化岗位（去重后）入库 SQLite；AI 岗 2619、含真实薪资 658（25%）；技能字典命中 101 项、其中 51 项有溢价数据；分析产物 7 类 JSON 落盘 data/processed/analysis/。
- 关键读数（初步）：溢价 Top = javascript +13.9%(n=23) / kafka +12.5% / vector-db +12.4% / solution-arch +11.9% / RAG +11.1% / anthropic-api +11.1% / pytorch +11.1%；负溢价 = python-web -14% / speech / doc-pipeline / linux / gpu（解释：通用基建技能出现在低价应用岗）。岗位分布：agent 202 / llm-app 188 / mlops 128 / data-eng 107 / ai-pm 85 / solutions 62 / security 28；RAG 作主标签仅 3，改用多标签口径建画像（已实现）。
- 遇到问题：关键词无词边界导致首轮分类失真（ai 命中 email 等）→ 全部加 \b 边界 + raw 正则列表后重跑，is_ai 从 3696 修正到 2619。
- 下一步：编写转型路线内容库（6 岗位 × 8 周计划/作品集/简历关键词/面试题）与画像叙述，然后建站。

## T+1:01 建站与测试完成（01:06）
- 已完成：Astro 5 + Tailwind 4 + ECharts 5 静态站 14 页全部构建通过；本地 8155 端口全页面 200；Playwright 实测路线生成器端到端可用（后端工程师→Agent 工程师→生成：缺口 3/11、第 0 周补差、8 周计划、MD 下载）；控制台 0 错误 0 警告；桌面+移动（390px）截图查验通过（logs/shots/）。
- 修复的 bug：① Astro BASE_URL 无尾斜杠导致全部内链错路径（10 文件统一归一化）；② 技能页共现图空白（内联脚本在 #pair-names 解析前同步执行，挪入 DOMContentLoaded）。
- 遇到问题：无新增。
- 下一步：git 提交 → GitHub Pages 部署 → 收尾文档。

## T+1:10 部署与交付完成（01:16）
- 已完成：GitHub 仓库 Tech--man/ai-job-radar 创建并推送（noreply 邮箱身份）；Pages workflow 部署成功；线上 https://tech--man.github.io/ai-job-radar/ 全页面 200（首页/画像/生成器/报告/简报/方法页）；线上浏览器控制台 0 错误；性能实测 HTML 16.7KB/~1s、echarts gzip 339KB（defer 并行加载，首屏内容先行渲染，满足移动端 <3s）；README/数据字典/免责声明/晨间简报交付；项目记忆已存档。
- 遇到问题：无新增。
- 验收对照：数据集 4142≥500 ✓；技能 101≥50 ✓；画像 6≥5 ✓；路线生成器可用（实测）✓；来源可追溯（SOURCE_MANIFEST + salary_raw）✓；溢价有计算逻辑（analyze.skill_premium）✓；薪资缺失显式标注 ✓；代码可运行（全链路刚执行过）✓。
