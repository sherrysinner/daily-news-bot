# 每日新闻推送系统 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建每日抓取新闻、DeepSeek 两轮整理、企业微信推送并发布 GitHub Pages 日报的 Python 工具。

**Architecture:** 单文件 Python 程序由可测试的纯函数组成，HTTP 请求采用 requests。模型输出严格要求 JSON，失败时保留 RSS 数据并用本地规则生成保守日报。

**Tech Stack:** Python 3.11、feedparser、requests、newspaper3k、pytest、GitHub Actions、GitHub Pages。

## Global Constraints

- 只读取 `DEEPSEEK_API_KEY`、`WECHAT_WEBHOOK_URL`、`PAGE_URL`。
- 输出 `news/YYYY-MM-DD.html`，手机正文不小于 16px，新闻正文使用 `details/summary` 折叠。
- 四个板块分别最多 8、4、4、4 条；企业微信按 6 类消息推送，单条最大 4096 字符。
- 每个远程失败均记录中文日志并继续；不虚构新闻事实。

---

### Task 1: 建立新闻模型、转义 HTML 与消息拆分

**Files:**
- Create: `daily-news-bot/main.py`
- Create: `daily-news-bot/tests/test_main.py`

**Interfaces:** `NewsItem`，`render_html(date_text, sections, hot_words, page_url)`，`split_markdown(text, limit=4096)`。

- [ ] 先写测试：HTML 含 `<details>`、会转义 `<script>`、新闻有锚点；5000 行短文本被拆成长度不超过 4096 的片段。
- [ ] 运行 `python -m pytest tests/test_main.py -v`，预期因模块不存在失败。
- [ ] 实现 dataclass、`html.escape` 渲染、移动端 CSS 和按换行优先的拆分算法。
- [ ] 重跑同一命令，预期全部通过。
- [ ] 提交：`git add daily-news-bot && git commit -m "feat: add news rendering helpers"`。

### Task 2: 抓取 RSS、正文、热搜与本地限额保底

**Files:**
- Modify: `daily-news-bot/main.py`
- Modify: `daily-news-bot/tests/test_main.py`

**Interfaces:** `fetch_rss_sources(session)`，`extract_article(item)`，`fetch_hot_words(session, url)`，`fallback_select(items)`。

- [ ] 先写测试：12 条国内外要闻输入后本地选择仅返回 8 条，空热搜返回空列表。
- [ ] 运行对应 pytest 用例，预期因函数不存在失败。
- [ ] 实现五个 RSS 常量、链接/标题去重、newspaper3k 正文提取、两个热搜端点的前五个关键词；每次异常使用 `logging.warning` 并返回可用部分。
- [ ] 重跑测试，预期通过；提交 `feat: fetch news with safe fallback`。

### Task 3: 实现 DeepSeek 两轮 JSON 编辑和企业微信消息

**Files:**
- Modify: `daily-news-bot/main.py`
- Modify: `daily-news-bot/tests/test_main.py`

**Interfaces:** `call_deepseek(session, messages, api_key)`，`ai_select(items, session, key)`，`ai_enrich(sections, session, key)`，`build_wechat_messages(...)`。

- [ ] 先写测试：无效 JSON 返回 `None`；模型选择的 URL 不在输入集合时被丢弃；生成消息保持四板块、热搜、入口六组并调用拆分。
- [ ] 运行 pytest，预期失败。
- [ ] 实现 `https://api.deepseek.com/chat/completions` 请求和两轮提示词：第一轮只可返回输入 URL，第二轮返回 `summary` 与 `article`。校验摘要 50–80 字、整理 300–500 字，不合格时由原文截取生成保底内容。
- [ ] 重跑测试，预期通过；提交 `feat: add DeepSeek editorial pipeline`。

### Task 4: 编排主流程、工作流与发布配置

**Files:**
- Modify: `daily-news-bot/main.py`
- Create: `daily-news-bot/requirements.txt`
- Create: `daily-news-bot/.github/workflows/daily.yml`
- Create: `daily-news-bot/news/.gitkeep`
- Modify: `daily-news-bot/tests/test_main.py`

**Interfaces:** `load_config()`、`main()`；产生 HTML 并 POST 企业微信 webhook。

- [ ] 先写测试：缺少任一环境变量时 `load_config()` 返回 `None`；模拟 webhook 失败不抛异常。
- [ ] 运行 pytest，预期失败。
- [ ] 实现 `main()`、UTF-8 写入、Webhook Markdown 请求与汇总日志。requirements 固定 `feedparser`、`requests`、`newspaper3k`、`lxml_html_clean`、`pytest`。workflow 使用 UTC `0 0 * * *`、手动触发、Python 3.11、三个 Secrets，并以 `upload-pages-artifact`/`deploy-pages` 发布 `daily-news-bot`。
- [ ] 运行 `python -m pytest -v` 和 `python -m py_compile main.py`，预期全部通过；用 YAML 解析验证工作流结构。
- [ ] 提交并推送：`git add daily-news-bot && git commit -m "feat: automate daily news delivery" && git push`。

## Self-review

- 需求映射：RSS、正文、热搜、两轮 AI、四板块数量、摘要/整理、来源、6 条消息、长度拆分、移动网页、日志、环境变量与 Pages 均有任务。
- 失败路径：每个网络操作与 JSON 解析都有本地保底或跳过策略。
- 无 TBD、TODO 或未命名接口。
