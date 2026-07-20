# NewsNow 数据接入与日报质量修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不增加账号或 API Key 的情况下，用 NewsNow 补充热点与财经来源，并修复图片、摘要和正文段落质量问题。

**Architecture:** `main.py` 新增一个小型 NewsNow 适配层，读取微博、华尔街见闻与财联社的公开热点数据，经过 HTTPS 与域名校验后转成 `NewsItem`。新闻选择、DeepSeek 整理和 HTML 渲染增加独立的质量校验：来源分散、图片去重、摘要完整、正文保留段落。现有 GitHub Actions 只获得一个可选环境变量，不改变 Secrets 或部署流程。

**Tech Stack:** Python 3.11、requests、pytest、DeepSeek Chat Completions、GitHub Actions。

## Global Constraints

- 不新增 GitHub Secret、账号或 API Key；NewsNow 默认地址为 `https://newsnow.busiyi.world/api/s`。
- 任一外部来源失败时，日报仍必须生成、部署并推送。
- 微博热搜最多显示 5 条；小红书无可靠数据时显示明确的中文缺失说明。
- 每个新闻板块中，同一来源最多保留 3 条。
- 仅展示未重复且来自正文解析的图片；无法确认的图片不显示。
- AI 摘要为 50 至 80 字的完整中文句；AI 正文为 3 至 5 段、300 至 500 字；质量失败时必须记录日志并安全降级。

---

### Task 1: 接入经过域名校验的 NewsNow 热点数据

**Files:**
- Modify: `daily-news-bot/main.py: RSS_SOURCES 至 fetch_hot_words`
- Modify: `daily-news-bot/tests/test_main.py`

**Interfaces:**
- Consumes: `requests.Session`、可选环境变量 `NEWSNOW_BASE_URL`。
- Produces: `fetch_newsnow_platform(session, platform_id, source, domain, section) -> list[NewsItem]` 与 `fetch_newsnow_hot_words(session, platform_id) -> list[str]`。

- [ ] **Step 1: 写出 NewsNow 新闻与热搜的失败测试**

```python
from main import fetch_newsnow_hot_words, fetch_newsnow_platform


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, payload):
        self.payload = payload

    def get(self, *_args, **_kwargs):
        return FakeResponse(self.payload)


def test_newsnow_converts_wallstreetcn_items_to_finance_news():
    session = FakeSession({"status": "success", "items": [{"title": "市场早报", "url": "https://wallstreetcn.com/articles/1", "mobileUrl": ""}]})
    items = fetch_newsnow_platform(session, "wallstreetcn-hot", "华尔街见闻", "wallstreetcn.com", "金融财经")
    assert [(item.title, item.source, item.section) for item in items] == [("市场早报", "华尔街见闻", "金融财经")]


def test_newsnow_rejects_an_item_from_an_unexpected_domain():
    session = FakeSession({"status": "success", "items": [{"title": "错误链接", "url": "https://evil.example/a", "mobileUrl": ""}]})
    assert fetch_newsnow_platform(session, "weibo", "微博", "weibo.com", "") == []


def test_newsnow_weibo_hot_words_uses_the_first_five_titles():
    rows = [{"title": f"热词{i}", "url": "https://s.weibo.com/weibo?q=x", "mobileUrl": ""} for i in range(8)]
    assert fetch_newsnow_hot_words(FakeSession({"status": "success", "items": rows}), "weibo") == ["热词0", "热词1", "热词2", "热词3", "热词4"]
```

- [ ] **Step 2: 运行测试，确认它因函数尚不存在而失败**

Run: `pytest tests/test_main.py -k newsnow -v`  
Expected: `ImportError`，指出 `fetch_newsnow_platform` 尚未定义。

- [ ] **Step 3: 在 `main.py` 实现最小 NewsNow 适配层**

```python
NEWSNOW_DEFAULT_BASE_URL = "https://newsnow.busiyi.world/api/s"


def newsnow_base_url() -> str:
    return os.getenv("NEWSNOW_BASE_URL", NEWSNOW_DEFAULT_BASE_URL).strip().rstrip("/")


def fetch_newsnow_payload(session: requests.Session, platform_id: str) -> list[dict[str, Any]]:
    response = session.get(
        newsnow_base_url(), params={"id": platform_id, "latest": ""}, timeout=20,
        headers={"User-Agent": "daily-news-bot/1.0", "Accept": "application/json"},
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("status") not in {"success", "cache"}:
        raise ValueError(f"NewsNow 返回状态异常：{payload.get('status')}")
    return payload.get("items", []) if isinstance(payload.get("items", []), list) else []


def is_expected_url(url: str, expected_domain: str) -> bool:
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    return parsed.scheme == "https" and (host == expected_domain or host.endswith(f".{expected_domain}"))


def fetch_newsnow_platform(session, platform_id, source, expected_domain, section) -> list[NewsItem]:
    try:
        rows = fetch_newsnow_payload(session, platform_id)
        items = []
        for row in rows:
            title = to_simplified(plain_text(str(row.get("title", ""))))
            url = str(row.get("mobileUrl") or row.get("url") or "").strip()
            if title and is_expected_url(url, expected_domain):
                items.append(NewsItem(title, source, url, title, title, section=section))
        logging.info("NewsNow 成功：%s，共 %d 条", source, len(items))
        return items
    except Exception as exc:  # noqa: BLE001
        logging.warning("NewsNow 抓取失败：%s，%s", source, exc)
        return []


def fetch_newsnow_hot_words(session: requests.Session, platform_id: str) -> list[str]:
    return [item.title for item in fetch_newsnow_platform(session, platform_id, "微博", "weibo.com", "")[:5]]
```

- [ ] **Step 4: 运行 NewsNow 测试，确认通过**

Run: `pytest tests/test_main.py -k newsnow -v`  
Expected: 3 passed。

- [ ] **Step 5: 提交本任务**

```bash
git add daily-news-bot/main.py daily-news-bot/tests/test_main.py
git commit -m "feat: add NewsNow news and hot word adapter"
```

### Task 2: 将新财经候选、微博热搜与来源均衡接入日报

**Files:**
- Modify: `daily-news-bot/main.py: fallback_select、ai_select、main`
- Modify: `daily-news-bot/tests/test_main.py`

**Interfaces:**
- Consumes: `fetch_newsnow_platform`、`fetch_newsnow_hot_words`、`NewsItem`。
- Produces: `apply_source_limits(sections) -> dict[str, list[NewsItem]]`，以及含华尔街见闻、财联社候选和微博热搜的 `main()` 数据流。

- [ ] **Step 1: 写出来源上限与热搜回退测试**

```python
from main import NewsItem, apply_source_limits, build_hot_words


def test_source_limit_keeps_at_most_three_items_per_source_in_one_section():
    items = [NewsItem(f"标题{i}", "中新网", "https://example.test/" + str(i), "", "", section="金融财经") for i in range(4)]
    items.append(NewsItem("财联社标题", "财联社", "https://www.cls.cn/detail/1", "", "", section="金融财经"))
    selected = apply_source_limits({"金融财经": items})
    assert [item.source for item in selected["金融财经"]].count("中新网") == 3
    assert selected["金融财经"][-1].source == "财联社"


def test_hot_words_marks_missing_xiaohongshu_data_in_chinese():
    assert build_hot_words(["热词一"], []) == {"微博热搜": ["热词一"], "小红书热搜": ["今日未获取到小红书热搜"]}
```

- [ ] **Step 2: 运行测试，确认缺少新函数而失败**

Run: `pytest tests/test_main.py -k 'source_limit or hot_words_marks' -v`  
Expected: `ImportError`，指出 `apply_source_limits` 与 `build_hot_words` 尚未定义。

- [ ] **Step 3: 实现来源限制并替换失效热搜调用**

```python
MAX_ITEMS_PER_SOURCE = 3


def apply_source_limits(sections: dict[str, list[NewsItem]]) -> dict[str, list[NewsItem]]:
    limited = {name: [] for name in SECTION_LIMITS}
    for section, items in sections.items():
        counts: dict[str, int] = {}
        for item in items:
            if section in limited and counts.get(item.source, 0) < MAX_ITEMS_PER_SOURCE:
                limited[section].append(item)
                counts[item.source] = counts.get(item.source, 0) + 1
    return limited


def build_hot_words(weibo_words: list[str], xiaohongshu_words: list[str]) -> dict[str, list[str]]:
    return {
        "微博热搜": weibo_words[:5] or ["今日未获取到微博热搜"],
        "小红书热搜": xiaohongshu_words[:5] or ["今日未获取到小红书热搜"],
    }
```

Update `ai_select` to return `apply_source_limits(selected)` in both the AI and fallback paths. In `main`, append `fetch_newsnow_platform` results for `wallstreetcn-hot` and `cls-hot`, use `fetch_newsnow_hot_words(session, "weibo")`, and pass an empty list as the current Xiaohongshu source until a tested provider exists.

- [ ] **Step 4: 运行目标测试及全部测试**

Run: `pytest -q`  
Expected: 全部通过。

- [ ] **Step 5: 提交本任务**

```bash
git add daily-news-bot/main.py daily-news-bot/tests/test_main.py
git commit -m "feat: merge NewsNow finance and hot lists into daily news"
```

### Task 3: 防止错误或重复新闻图片

**Files:**
- Modify: `daily-news-bot/main.py: extract_article、render_html`
- Modify: `daily-news-bot/tests/test_main.py`

**Interfaces:**
- Consumes: `NewsItem.image_url`。
- Produces: `render_html` 仅为当天首次出现的有效图片输出 `<img>`。

- [ ] **Step 1: 写出图片去重和不使用通用元图的测试**

```python
def test_html_shows_a_duplicate_image_only_once():
    first = NewsItem("甲", "中新网", "https://example.test/1", "", "", image_url="https://img.example/a.jpg", section="国内外要闻")
    second = NewsItem("乙", "中新网", "https://example.test/2", "", "", image_url="https://img.example/a.jpg", section="国内外要闻")
    page = render_html("2026-07-21", {"国内外要闻": [first, second]}, {}, "https://example.test")
    assert page.count('class="news-image"') == 1
```

- [ ] **Step 2: 运行测试，确认当前 HTML 重复展示图片而失败**

Run: `pytest tests/test_main.py::test_html_shows_a_duplicate_image_only_once -v`  
Expected: FAIL，图片标签数量为 2。

- [ ] **Step 3: 实现图片安全策略**

```python
def is_displayable_image(url: str, seen_images: set[str]) -> bool:
    return url.startswith(("https://", "http://")) and url not in seen_images
```

In `render_html`, create `seen_images: set[str] = set()` before looping over sections. Render `<img>` only when `is_displayable_image(item.image_url, seen_images)` is true, then add the URL to `seen_images`. Remove `enrich_image_from_metadata` and never call it. In `extract_article`, keep `Article.top_image` only after a successful `article.parse()` and a non-empty `article.text`.

- [ ] **Step 4: 运行全部测试**

Run: `pytest -q`  
Expected: 全部通过。

- [ ] **Step 5: 提交本任务**

```bash
git add daily-news-bot/main.py daily-news-bot/tests/test_main.py
git commit -m "fix: avoid duplicate and unverified news images"
```

### Task 4: 强制完整摘要并保留正文段落

**Files:**
- Modify: `daily-news-bot/main.py: plain_text、fallback_text、ai_enrich、render_html`
- Modify: `daily-news-bot/tests/test_main.py`

**Interfaces:**
- Consumes: DeepSeek 的 `summary` 和 `article` 字段。
- Produces: `normalize_article_paragraphs(value) -> str`、`is_valid_summary(value) -> bool`、`is_valid_article(value) -> bool`。

- [ ] **Step 1: 写出摘要和段落质量校验的失败测试**

```python
from main import is_valid_article, is_valid_summary, normalize_article_paragraphs, render_html


def test_summary_must_be_a_complete_sentence_between_fifty_and_eighty_characters():
    assert is_valid_summary("有关部门发布新政策，明确了实施范围、执行时间和配套措施，相关地区将根据实际情况稳妥推进，政策重点在于改善公共服务并保障群众便利。")
    assert not is_valid_summary("有关部门发布新政策，明确了实施范围")


def test_article_normalization_keeps_three_paragraphs_for_html():
    article = normalize_article_paragraphs("第一段事实。\n\n第二段背景。\n\n第三段影响。")
    assert article.count("\n\n") == 2
    item = NewsItem("标题", "来源", "https://example.test", "", "", summary="有关部门发布新政策，明确了实施范围、执行时间和配套措施，相关地区将根据实际情况稳妥推进，政策重点在于改善公共服务并保障群众便利。", article=article, section="国内外要闻")
    assert render_html("2026-07-21", {"国内外要闻": [item]}, {}, "https://example.test").count("<details><summary>") == 1
```

- [ ] **Step 2: 运行测试，确认新校验函数缺失而失败**

Run: `pytest tests/test_main.py -k 'summary_must or article_normalization' -v`  
Expected: `ImportError`，指出质量校验函数尚未定义。

- [ ] **Step 3: 实现质量校验、一次 AI 修复重试与段落渲染**

```python
def normalize_article_paragraphs(value: str) -> str:
    paragraphs = [plain_text(part) for part in re.split(r"\n\s*\n", value or "") if plain_text(part)]
    return "\n\n".join(paragraphs)


def is_valid_summary(value: str) -> bool:
    text = plain_text(value)
    return 50 <= len(text) <= 80 and text.endswith(("。", "！", "？"))


def is_valid_article(value: str) -> bool:
    paragraphs = normalize_article_paragraphs(value).split("\n\n")
    return 300 <= len("".join(paragraphs)) <= 500 and 3 <= len(paragraphs) <= 5
```

Change the DeepSeek instruction to require an independent, factual summary with subject and event, no unfinished sentence, and an article with 3 to 5 paragraphs separated by `\n\n`. Do not run `plain_text` on the article before validation. When validation fails, call DeepSeek once more with a repair instruction. If it still fails, use the existing source text as a clearly logged fallback; do not claim that a truncated excerpt is an AI summary. In `render_html`, split only by `\n\n` and wrap each paragraph in `<p>`.

- [ ] **Step 4: 运行全部测试**

Run: `pytest -q`  
Expected: 全部通过。

- [ ] **Step 5: 提交本任务**

```bash
git add daily-news-bot/main.py daily-news-bot/tests/test_main.py
git commit -m "fix: validate complete summaries and paragraph articles"
```

### Task 5: 为 GitHub Actions 增加可迁移配置并做最终验证

**Files:**
- Modify: `.github/workflows/daily.yml`
- Modify: `daily-news-bot/tests/test_workflow_location.py`

**Interfaces:**
- Consumes: 可选变量 `NEWSNOW_BASE_URL`。
- Produces: 保持现有 Secrets 不变的 Actions 运行环境。

- [ ] **Step 1: 写出 workflow 不要求新 Secret 的失败测试**

```python
def test_workflow_uses_defaultable_newsnow_base_url_without_a_secret():
    text = Path(".github/workflows/daily.yml").read_text(encoding="utf-8")
    assert "NEWSNOW_BASE_URL: ${{ vars.NEWSNOW_BASE_URL }}" in text
    assert "secrets.NEWSNOW_BASE_URL" not in text
```

- [ ] **Step 2: 运行测试，确认它因变量尚未配置而失败**

Run: `pytest daily-news-bot/tests/test_workflow_location.py -v`  
Expected: FAIL，找不到 `NEWSNOW_BASE_URL`。

- [ ] **Step 3: 添加可选 Action Variable**

```yaml
          NEWSNOW_BASE_URL: ${{ vars.NEWSNOW_BASE_URL }}
```

Place this alongside the existing three environment variables. An empty value makes `newsnow_base_url()` use the public default; NAS 迁移时可将该变量设为 NAS 上自建 NewsNow 的地址。

- [ ] **Step 4: 运行最终验证**

Run: `pytest -q`  
Expected: 全部通过。

Run: `python -m py_compile main.py` from `daily-news-bot`  
Expected: exit code 0。

- [ ] **Step 5: 提交本任务**

```bash
git add .github/workflows/daily.yml daily-news-bot/tests/test_workflow_location.py
git commit -m "chore: configure optional NewsNow endpoint"
```

