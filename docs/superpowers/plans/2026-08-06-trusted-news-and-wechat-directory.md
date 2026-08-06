# 可信新板块与企业微信目录化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增可信文娱、财会审计法律板块，并将企业微信日报改为链接到网页版的简洁目录。

**Architecture:** `main.py` 保持单文件结构，在来源配置与抓取层增加官方列表页来源，并在 `NewsItem` 上保留来源可信类型。既有 AI 筛选、HTML 生成与企业微信推送共用扩展后的板块顺序；企业微信只生成目录链接，网页保留全文内容。

**Tech Stack:** Python 3.11、requests、feedparser、BeautifulSoup/newspaper3k、DeepSeek API、pytest。

## Global Constraints

- 新增文娱板块每天最多 3 条，财会审计与法律更新每天最多 4 条。
- 文娱只允许主流媒体报道的可核验公开事件；传闻、营销号与隐私猜测必须过滤。
- 财会法律只允许政府、司法机关、审计机关、税务机关或中注协的一手内容；官方案例必须标注为官方案例。
- 可靠候选不足时网页显示无可靠更新，企业微信不发送空板块。
- 企业微信保留地缘政治简报和 B 站新闻视频入口；其他板块只显示分类和标题链接，继续使用 4096 字符拆分。

---

### Task 1: 扩展来源配置与官方列表页抓取

**Files:**
- Modify: `daily-news-bot/main.py:28-60,127-149,890-902`
- Modify: `daily-news-bot/tests/test_main.py`

**Interfaces:**
- Consumes: `requests.Session`、来源配置和网页响应文本。
- Produces: `fetch_official_list_source(session, source, url, section, source_type) -> list[NewsItem]`，以及带 `source_type` 的 `NewsItem`。

- [ ] **Step 1: 写出失败测试**

```python
def test_official_list_source_keeps_title_url_date_and_source_type():
    html = '<a href="/law/1">法规更新</a><time>2026-08-06</time>'
    items = fetch_official_list_source(FakeTextSession(html), "国家法律法规数据库", "https://example.com", "财会审计与法律更新", "官方法规")
    assert [(item.title, item.url, item.section, item.source_type)] == [
        ("法规更新", "https://example.com/law/1", "财会审计与法律更新", "官方法规")
    ]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `& 'C:\\Users\\PC\\.cache\\codex-runtimes\\codex-primary-runtime\\dependencies\\python\\python.exe' -m pytest tests/test_main.py::test_official_list_source_keeps_title_url_date_and_source_type -q`

Expected: FAIL，因为 `fetch_official_list_source` 和 `source_type` 尚不存在。

- [ ] **Step 3: 最小实现**

```python
@dataclass
class NewsItem:
    # 保留既有字段
    source_type: str = ""

def fetch_official_list_source(session, source, url, section, source_type):
    response = session.get(url, timeout=20)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    return [NewsItem(title, source, absolute_url, title, "", section=section, source_type=source_type)
            for title, absolute_url in extract_list_links(soup, url)]
```

配置全国人大法律法规数据库、司法部行政法规库、最高法司法解释、财政部会计司、审计署、中注协、税务总局；文娱配置澎湃有戏与中新网文娱。每个来源失败时记录 warning 并返回空列表。

- [ ] **Step 4: 运行单测确认通过**

Run: `& 'C:\\Users\\PC\\.cache\\codex-runtimes\\codex-primary-runtime\\dependencies\\python\\python.exe' -m pytest tests/test_main.py::test_official_list_source_keeps_title_url_date_and_source_type -q`

Expected: PASS。

- [ ] **Step 5: 提交本任务**

```bash
git add daily-news-bot/main.py daily-news-bot/tests/test_main.py
git commit -m "feat: add trusted news source collectors"
```

### Task 2: 扩展分类、限额与 AI 可信筛选规则

**Files:**
- Modify: `daily-news-bot/main.py:36,492-573,655-705`
- Modify: `daily-news-bot/tests/test_main.py`

**Interfaces:**
- Consumes: 具有 `section`、`source_type` 的 `NewsItem`。
- Produces: 包含六个新闻板块的 `dict[str, list[NewsItem]]`，由 `ai_select()` 生成。

- [ ] **Step 1: 写出失败测试**

```python
def test_section_limits_include_trusted_entertainment_and_professional_news():
    assert SECTION_LIMITS["文娱人物与行业"] == 3
    assert SECTION_LIMITS["财会审计与法律更新"] == 4

def test_ai_selection_prompt_requires_verifiable_entertainment_and_official_legal_sources():
    prompt = build_selection_prompt()
    assert "未经证实" in prompt
    assert "官方法规" in prompt
    assert "财会审计与法律更新" in prompt
```

- [ ] **Step 2: 运行测试确认失败**

Run: `& 'C:\\Users\\PC\\.cache\\codex-runtimes\\codex-primary-runtime\\dependencies\\python\\python.exe' -m pytest tests/test_main.py::test_section_limits_include_trusted_entertainment_and_professional_news tests/test_main.py::test_ai_selection_prompt_requires_verifiable_entertainment_and_official_legal_sources -q`

Expected: FAIL，因为新板块与 `build_selection_prompt()` 尚不存在。

- [ ] **Step 3: 最小实现**

```python
SECTION_LIMITS = {"国内外要闻": 8, "科技": 4, "金融财经": 4, "娱乐体育": 4,
                  "文娱人物与行业": 3, "财会审计与法律更新": 4}

def build_selection_prompt() -> str:
    return """文娱人物与行业仅选可核验公开事件，排除未经证实传闻。
    财会审计与法律更新只选官方法规、官方监管、官方案例或可回链一手文件。"""
```

将 `ai_select()` 改为调用 `build_selection_prompt()`，并把 `source_type` 放入目录载荷；`ai_enrich()` 的提示词要求财会类写明发布机构与影响对象、案例标明官方案例，文娱类避免夸张措辞。

- [ ] **Step 4: 运行板块与全文测试**

Run: `& 'C:\\Users\\PC\\.cache\\codex-runtimes\\codex-primary-runtime\\dependencies\\python\\python.exe' -m pytest tests/test_main.py -q`

Expected: PASS。

- [ ] **Step 5: 提交本任务**

```bash
git add daily-news-bot/main.py daily-news-bot/tests/test_main.py
git commit -m "feat: classify trusted news categories"
```

### Task 3: 网页空板块与企业微信目录消息

**Files:**
- Modify: `daily-news-bot/main.py:758-875`
- Modify: `daily-news-bot/tests/test_main.py`

**Interfaces:**
- Consumes: `render_html(date_text, sections, hot_words, page_url, geo_briefs, bilibili_videos)` 与 `build_wechat_messages(...)`。
- Produces: 网页包含所有六个板块；企业微信消息包含地缘入口、B 站入口和各非空新闻板块的标题锚点。

- [ ] **Step 1: 写出失败测试**

```python
def test_wechat_news_section_is_title_only_directory():
    message = build_wechat_messages("2026-08-06", {"科技": [make_item("科技标题", summary="不应出现的摘要")]}, {}, "https://pages.example")
    joined = "\n".join(message)
    assert "[科技标题](https://pages.example/news/2026-08-06.html#news-1)" in joined
    assert "不应出现的摘要" not in joined

def test_html_shows_empty_trusted_section_message():
    html = render_html("2026-08-06", empty_sections(), {}, "https://pages.example")
    assert "文娱人物与行业" in html
    assert "今日暂无符合筛选规则的可靠更新" in html
```

- [ ] **Step 2: 运行测试确认失败**

Run: `& 'C:\\Users\\PC\\.cache\\codex-runtimes\\codex-primary-runtime\\dependencies\\python\\python.exe' -m pytest tests/test_main.py::test_wechat_news_section_is_title_only_directory tests/test_main.py::test_html_shows_empty_trusted_section_message -q`

Expected: FAIL，因为当前企业微信仍带摘要，网页使用旧的空板块提示。

- [ ] **Step 3: 最小实现**

```python
for section in SECTION_LIMITS:
    if not sections.get(section):
        continue
    lines = [f"## {section}｜{date_text}"]
    for item in sections[section]:
        number += 1
        lines.append(f"- [{truncate_title(item.title)}]({page_url}/news/{date_text}.html#news-{number})")
```

地缘消息只保留“打开地缘政治简报”链接；B 站消息只保留视频标题及网页版视频区链接；热搜仅保留关键词。网页对两个新板块的空状态使用“今日暂无符合筛选规则的可靠更新”。

- [ ] **Step 4: 运行消息与网页测试**

Run: `& 'C:\\Users\\PC\\.cache\\codex-runtimes\\codex-primary-runtime\\dependencies\\python\\python.exe' -m pytest tests/test_main.py -q`

Expected: PASS。

- [ ] **Step 5: 提交本任务**

```bash
git add daily-news-bot/main.py daily-news-bot/tests/test_main.py
git commit -m "feat: make WeChat digest a news directory"
```

### Task 4: 端到端回归与来源声明

**Files:**
- Modify: `daily-news-bot/main.py:874,897-922`
- Modify: `daily-news-bot/tests/test_main.py`

**Interfaces:**
- Consumes: 全部抓取候选、AI 选择结果和 `build_wechat_messages()`。
- Produces: 新候选被合并进日报，来源声明包含新增可信来源，推送不发送空新闻板块。

- [ ] **Step 1: 写出失败测试**

```python
def test_main_candidate_assembly_includes_new_trusted_collectors(monkeypatch):
    collected = [
        make_item("官宣新片", section="文娱人物与行业"),
        make_item("会计准则问答", section="财会审计与法律更新"),
    ]
    assert {item.section for item in collected} == {"文娱人物与行业", "财会审计与法律更新"}

def test_wechat_skips_empty_news_section():
    messages = build_wechat_messages("2026-08-06", empty_sections(), {}, "https://pages.example")
    assert not any("文娱人物与行业" in message for message in messages)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `& 'C:\\Users\\PC\\.cache\\codex-runtimes\\codex-primary-runtime\\dependencies\\python\\python.exe' -m pytest tests/test_main.py::test_main_candidate_assembly_includes_new_trusted_collectors tests/test_main.py::test_wechat_skips_empty_news_section -q`

Expected: FAIL，直至 `main()` 组装新来源并跳过空消息。

- [ ] **Step 3: 最小实现**

在 `main()` 中调用两类新抓取器并合并到 `items`；更新来源声明为“公开 RSS、主流媒体文娱栏目及政府和行业机构公开页面”。保留所有既有错误日志、网页发布与 B 站已推送记录逻辑。

- [ ] **Step 4: 运行全量验证**

Run: `& 'C:\\Users\\PC\\.cache\\codex-runtimes\\codex-primary-runtime\\dependencies\\python\\python.exe' -m pytest -q -p no:cacheprovider --basetemp .test-tmp-trusted-news`

Expected: PASS，且没有失败或跳过的新增测试。

- [ ] **Step 5: 提交本任务**

```bash
git add daily-news-bot/main.py daily-news-bot/tests/test_main.py
git commit -m "feat: publish trusted daily news categories"
```

## Plan self-review

- 覆盖范围：任务 1 处理来源与可信类型；任务 2 处理限额和 AI 规则；任务 3 处理网页和企业微信目录；任务 4 处理日报组装、来源声明和回归。
- 一致性：所有任务都使用 `NewsItem.source_type`、`SECTION_LIMITS` 和既有 `build_wechat_messages()` 接口；消息锚点继续与 `render_html()` 的 `news-{number}` 顺序一致。
- 范围控制：不增加未验证的营销号、论坛或匿名爆料来源，不改动现有 B 站抓取和图片缓存策略。
