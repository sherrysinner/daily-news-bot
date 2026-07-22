import main as main_module

from datetime import datetime, timezone
from io import BytesIO

from PIL import Image

from main import (
    RSS_SOURCES,
    WALLSTREETCN_URL,
    NewsItem,
    HotTopic,
    GeoBrief,
    apply_source_limits,
    ai_enrich,
    build_hot_words,
    clean_editorial_title,
    cache_article_image,
    cache_article_images,
    beijing_today,
    build_wechat_messages,
    fallback_text,
    fill_section_gaps,
    fetch_newsnow_hot_words,
    fetch_newsnow_hot_topics,
    hot_topic_note,
    fetch_newsnow_platform,
    is_valid_article,
    is_valid_summary,
    normalize_article_paragraphs,
    paragraphize_article,
    render_html,
    extract_body_image_urls,
    ai_geopolitical_brief,
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
    item = NewsItem("标题", "来源", "https://example.test", "简介", "正文", article="正文第一段。", image_url="https://example.test/a.jpg", section="国内外要闻")
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


def test_newsnow_hot_topics_keep_the_weibo_search_link_and_honest_description():
    rows = [{"title": "热词一", "url": "https://s.weibo.com/weibo?q=热词一", "mobileUrl": ""}]
    topics = fetch_newsnow_hot_topics(FakeSession({"status": "success", "items": rows}), "weibo")
    assert topics == [HotTopic("热词一", "https://s.weibo.com/weibo?q=热词一", "点击查看微博实时讨论")]


def test_newsnow_bilibili_hot_topics_keep_the_bilibili_search_link():
    rows = [{"title": "B站热词", "url": "https://search.bilibili.com/all?keyword=x"}]
    topics = fetch_newsnow_hot_topics(FakeSession({"status": "success", "items": rows}), "bilibili-hot-search", "bilibili.com", "点击查看B站实时讨论")
    assert topics == [HotTopic("B站热词", "https://search.bilibili.com/all?keyword=x", "点击查看B站实时讨论")]


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
    first = NewsItem("甲", "中新网", "https://example.test/1", "", "", article="第一段。", image_url="https://img.example/a.jpg", section="国内外要闻")
    second = NewsItem("乙", "中新网", "https://example.test/2", "", "", article="第一段。", image_url="https://img.example/a.jpg", section="国内外要闻")
    page = render_html("2026-07-21", {"国内外要闻": [first, second]}, {}, "https://example.test")
    assert page.count('class="news-image"') == 1


def test_chinanews_image_is_not_used_when_it_may_be_a_generic_rss_image(tmp_path):
    item = NewsItem("标题", "中新网国内", "https://example.test/1", "", "", image_url="https://img.example/a.jpg")
    cache_article_image(object(), item, tmp_path)
    assert item.image_url == ""


class ImageResponse:
    headers = {"Content-Type": "image/jpeg"}

    def __init__(self):
        image = Image.new("RGB", (200, 200), "#884422")
        buffer = BytesIO()
        image.save(buffer, format="JPEG")
        self.content = buffer.getvalue()

    def raise_for_status(self):
        return None


class ImageSession:
    def get(self, *_args, **_kwargs):
        return ImageResponse()


class MultiImageSession:
    def __init__(self):
        image = Image.new("RGB", (1800, 1200), "#884422")
        buffer = BytesIO()
        image.save(buffer, format="JPEG", quality=95)
        self.content = buffer.getvalue()

    def get(self, *_args, **_kwargs):
        response = ImageResponse()
        response.content = self.content
        return response


def test_article_image_is_cached_beside_daily_html(tmp_path):
    item = NewsItem("标题", "36氪", "https://36kr.com/p/1", "", "", image_url="https://img.example/a.jpg")
    cache_article_image(ImageSession(), item, tmp_path)
    assert item.image_url.startswith("images/")
    assert (tmp_path / item.image_url.removeprefix("images/")).is_file()


def test_article_can_cache_at_most_two_compressed_images(tmp_path):
    item = NewsItem("标题", "36氪", "https://36kr.com/p/1", "", "", image_urls=["https://img.example/a.jpg", "https://img.example/b.jpg", "https://img.example/c.jpg"])
    cache_article_images(MultiImageSession(), item, tmp_path)
    assert len(item.image_urls) == 2
    assert all(url.startswith("images/") for url in item.image_urls)
    assert all((tmp_path / url.removeprefix("images/")).stat().st_size <= 300 * 1024 for url in item.image_urls)


def test_html_renders_two_images_for_one_news_item():
    item = NewsItem("标题", "36氪", "https://36kr.com/p/1", "", "", article="第一段。\n\n第二段。", image_urls=["images/a.jpg", "images/b.jpg"], section="国内外要闻")
    page = render_html("2026-07-21", {"国内外要闻": [item]}, {}, "https://example.test")
    assert page.count('class="news-image"') == 2


def test_html_uses_first_image_as_cover_and_keeps_remaining_images_at_article_end():
    item = NewsItem("标题", "36氪", "https://36kr.com/p/1", "", "", article="第一段。\n\n第二段。\n\n第三段。", image_urls=["images/a.jpg", "images/b.jpg"], section="国内外要闻")
    page = render_html("2026-07-21", {"国内外要闻": [item]}, {}, "https://example.test")
    assert page.index("<h3>标题</h3>") < page.index('class="news-image"')
    assert page.index('src="images/a.jpg"') < page.index("<details>")
    assert page.index("<p>第三段。</p>") < page.index('src="images/b.jpg"')


def test_body_image_urls_keep_article_order_and_skip_page_chrome():
    page = '''<html><body><header><img src="/logo.png"></header><article>
    <p>正文</p><img data-src="/body-first.jpg"><img src="/advert-banner.jpg"><img src="/body-last.jpg">
    </article><footer><img src="/footer.jpg"></footer></body></html>'''
    assert extract_body_image_urls(page, "https://example.test/news") == [
        "https://example.test/body-first.jpg", "https://example.test/body-last.jpg",
    ]


def test_short_complete_summary_is_kept_when_ai_strict_length_check_fails(monkeypatch):
    responses = iter([
        {"title": "测试标题", "summary": "这是一个完整但较短的新闻摘要，说明了事件主体和已经发生的事实。", "article": "第一句。第二句。第三句。"},
        {"summary": "仍然过短。"},
    ])
    monkeypatch.setattr(main_module, "call_deepseek", lambda *_args, **_kwargs: next(responses))
    item = NewsItem("原标题", "测试来源", "https://example.test/news", "原始简介第一句。后续内容。", "正文", section="国内外要闻")
    ai_enrich({"国内外要闻": [item]}, object(), "test-key")
    assert item.summary == "这是一个完整但较短的新闻摘要，说明了事件主体和已经发生的事实。"


def test_fallback_summary_uses_the_first_complete_source_sentence():
    item = NewsItem("原标题", "测试来源", "https://example.test/news", "这是一条可读的来源简介第一句。第二句不应成为摘要。", "")
    summary, _ = fallback_text(item)
    assert summary == "这是一条可读的来源简介第一句。"


def test_hot_words_are_rendered_as_numbered_rows_in_html_and_wechat():
    hot = {"微博热搜": ["热词一", "热词二"]}
    page = render_html("2026-07-21", {}, hot, "https://example.test")
    messages = build_wechat_messages("2026-07-21", {}, hot, "https://example.test")
    assert "<ol class=\"hot-list\"><li>热词一</li><li>热词二</li></ol>" in page
    assert "1. 热词一\n2. 热词二" in "\n".join(messages)


def test_hot_topic_has_a_clickable_title_and_a_single_column_note_in_html_and_wechat():
    topic = HotTopic("热词一", "https://s.weibo.com/weibo?q=x", "点击查看微博实时讨论")
    page = render_html("2026-07-21", {}, {"微博热搜": [topic]}, "https://example.test")
    messages = build_wechat_messages("2026-07-21", {}, {"微博热搜": [topic]}, "https://example.test")
    assert 'href="https://s.weibo.com/weibo?q=x"' in page
    assert page.count('class="hot-note"') == 1
    assert hot_topic_note("微博热搜") in page
    assert "[热词一](https://s.weibo.com/weibo?q=x)" in "\n".join(messages)
    assert f"\n{hot_topic_note('微博热搜')}" in "\n".join(messages)


def test_geo_brief_is_exactly_three_items_and_rendered_before_news(monkeypatch):
    response = {"briefs": [
        {"title": "第一条", "event": "发生了第一件事。", "impact": "影响一。", "watch": "关注一。"},
        {"title": "第二条", "event": "发生了第二件事。", "impact": "影响二。", "watch": "关注二。"},
        {"title": "第三条", "event": "发生了第三件事。", "impact": "影响三。", "watch": "关注三。"},
    ]}
    monkeypatch.setattr(main_module, "call_deepseek", lambda *_args, **_kwargs: response)
    briefs = ai_geopolitical_brief({"国内外要闻": [NewsItem("国际新闻", "来源", "https://example.test", "事实。", "事实。", summary="完整事实。")]} , object(), "key")
    assert briefs == [GeoBrief("第一条", "发生了第一件事。", "影响一。", "关注一。"), GeoBrief("第二条", "发生了第二件事。", "影响二。", "关注二。"), GeoBrief("第三条", "发生了第三件事。", "影响三。", "关注三。")]
    page = render_html("2026-07-21", {"国内外要闻": []}, {}, "https://example.test", briefs)
    assert page.index('id="geopolitics"') < page.index("国内外要闻")
    assert "事件概述：" in page
    assert "影响分析：" in page
    assert "后续关注：" in page
    assert '<ul class="geo-points">' in page
    assert "发生了什么：" not in page


def test_daily_date_uses_beijing_timezone():
    assert beijing_today(datetime(2026, 7, 20, 23, 45, tzinfo=timezone.utc)) == "2026-07-21"


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


def test_section_gaps_are_filled_from_original_candidates():
    chosen = {name: [] for name in RSS_SOURCES}
    chosen["金融财经"] = [NewsItem("已选", "来源甲", "https://example.test/selected", "", "", section="金融财经")]
    candidates = {
        "金融财经": [
            NewsItem("已选", "来源甲", "https://example.test/selected", "", "", section="金融财经"),
            NewsItem("候选一", "来源乙", "https://example.test/one", "", "", section="金融财经"),
            NewsItem("候选二", "来源丙", "https://example.test/two", "", "", section="金融财经"),
            NewsItem("候选三", "来源丁", "https://example.test/three", "", "", section="金融财经"),
        ]
    }
    result = fill_section_gaps(chosen, candidates)
    assert [item.title for item in result["金融财经"]] == ["已选", "候选一", "候选二", "候选三"]


def test_article_is_split_into_three_paragraphs_when_ai_omits_breaks():
    article = paragraphize_article("第一句。第二句。第三句。第四句。第五句。第六句。")
    assert article.count("\n\n") == 2
    assert article.split("\n\n") == ["第一句。第二句。", "第三句。第四句。", "第五句。第六句。"]


def test_ai_retries_only_the_summary_and_keeps_a_paragraphized_article(monkeypatch):
    complete_summary = "有关部门发布新政策，明确了实施范围、执行时间和配套措施，相关地区将根据实际情况稳妥推进，政策重点在于改善公共服务并保障群众便利。"
    responses = iter([
        {"title": "测试标题", "summary": "过短摘要。", "article": "第一句。第二句。第三句。第四句。第五句。第六句。"},
        {"summary": complete_summary},
    ])
    monkeypatch.setattr(main_module, "call_deepseek", lambda *_args, **_kwargs: next(responses))
    item = NewsItem("原标题", "测试来源", "https://example.test/news", "简介", "正文", section="国内外要闻")
    ai_enrich({"国内外要闻": [item]}, object(), "test-key")
    assert item.summary == complete_summary
    assert item.article.count("\n\n") == 2
