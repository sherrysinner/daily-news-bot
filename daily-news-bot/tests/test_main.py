from main import (
    RSS_SOURCES,
    WALLSTREETCN_URL,
    NewsItem,
    apply_source_limits,
    build_hot_words,
    clean_editorial_title,
    fetch_newsnow_hot_words,
    fetch_newsnow_platform,
    is_valid_article,
    is_valid_summary,
    normalize_article_paragraphs,
    render_html,
    split_markdown,
    to_simplified,
)


def test_html_escapes_content_and_has_collapsible_article():
    item = NewsItem(
        title="标题 <x>",
        source="测试来源",
        url="https://example.test/news",
        description="简介",
        content="正文 <script>",
        summary="这是一段足够长的测试摘要，用于验证网页中新闻摘要能被正确显示。",
        article="这是一段用于测试的新闻整理正文，应当以折叠方式呈现并且内容被安全转义。正文 <script>",
        section="国内外要闻",
    )
    html = render_html("2026-07-20", {"国内外要闻": [item]}, {}, "https://example.test")
    assert "<details>" in html
    assert "&lt;script&gt;" in html
    assert 'id="news-1"' in html


def test_markdown_is_split_below_wechat_limit():
    parts = split_markdown("甲\n" * 5000)
    assert len(parts) > 1
    assert all(len(part) <= 4096 for part in parts)


def test_sources_replace_dead_xinhua_and_use_wallstreetcn_feed():
    domestic_urls = [url for _, url in RSS_SOURCES["国内外要闻"]]
    finance_urls = [url for _, url in RSS_SOURCES["金融财经"]]
    assert "http://www.xinhuanet.com/politics/xhll.xml" not in domestic_urls
    assert "https://www.chinanews.com.cn/rss/china.xml" in domestic_urls
    assert "https://www.chinanews.com.cn/rss/finance.xml" in finance_urls
    assert "api-one.wallstcn.com" in WALLSTREETCN_URL


def test_html_shows_image_only_when_a_news_image_exists():
    item = NewsItem("标题", "来源", "https://example.test", "简介", "正文", image_url="https://example.test/a.jpg", section="国内外要闻")
    html = render_html("2026-07-20", {"国内外要闻": [item]}, {}, "https://example.test")
    assert 'class="news-image"' in html


def test_traditional_characters_are_converted_to_simplified():
    assert to_simplified("華爾街日報關注經濟發展") == "华尔街日报关注经济发展"


def test_editorial_title_requires_chinese_text():
    assert clean_editorial_title("华尔街日报关注全球市场") == "华尔街日报关注全球市场"
    assert clean_editorial_title("Stocks rally") == ""


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


class RecordingSession(FakeSession):
    def __init__(self, payload):
        super().__init__(payload)
        self.request_kwargs = {}

    def get(self, *_args, **kwargs):
        self.request_kwargs = kwargs
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


def test_newsnow_uses_a_browser_compatible_request_header():
    session = RecordingSession({"status": "success", "items": []})
    fetch_newsnow_platform(session, "weibo", "微博", "weibo.com", "")
    assert session.request_kwargs["headers"]["User-Agent"].startswith("Mozilla/")


def test_source_limit_keeps_at_most_three_items_per_source_in_one_section():
    items = [NewsItem(f"标题{i}", "中新网", f"https://example.test/{i}", "", "", section="金融财经") for i in range(4)]
    items.append(NewsItem("财联社标题", "财联社", "https://www.cls.cn/detail/1", "", "", section="金融财经"))
    selected = apply_source_limits({"金融财经": items})
    assert [item.source for item in selected["金融财经"]].count("中新网") == 3
    assert selected["金融财经"][-1].source == "财联社"


def test_hot_words_marks_missing_xiaohongshu_data_in_chinese():
    assert build_hot_words(["热词一"], []) == {"微博热搜": ["热词一"], "小红书热搜": ["今日未获取到小红书热搜"]}


def test_html_shows_a_duplicate_image_only_once():
    first = NewsItem("甲", "中新网", "https://example.test/1", "", "", image_url="https://img.example/a.jpg", section="国内外要闻")
    second = NewsItem("乙", "中新网", "https://example.test/2", "", "", image_url="https://img.example/a.jpg", section="国内外要闻")
    page = render_html("2026-07-21", {"国内外要闻": [first, second]}, {}, "https://example.test")
    assert page.count('class="news-image"') == 1


def test_summary_must_be_a_complete_sentence_between_fifty_and_eighty_characters():
    complete = "有关部门发布新政策，明确了实施范围、执行时间和配套措施，相关地区将根据实际情况稳妥推进，政策重点在于改善公共服务并保障群众便利。"
    assert is_valid_summary(complete)
    assert not is_valid_summary("有关部门发布新政策，明确了实施范围")


def test_article_normalization_keeps_three_paragraphs_for_html():
    article = normalize_article_paragraphs("第一段事实。\n\n第二段背景。\n\n第三段影响。")
    assert article.count("\n\n") == 2
    assert not is_valid_article(article)
    item = NewsItem("标题", "来源", "https://example.test", "", "", summary="有关部门发布新政策，明确了实施范围、执行时间和配套措施，相关地区将根据实际情况稳妥推进，政策重点在于改善公共服务并保障群众便利。", article=article, section="国内外要闻")
    page = render_html("2026-07-21", {"国内外要闻": [item]}, {}, "https://example.test")
    assert "<p>第一段事实。</p><p>第二段背景。</p><p>第三段影响。</p>" in page
