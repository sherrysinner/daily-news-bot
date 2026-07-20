from main import RSS_SOURCES, NewsItem, clean_editorial_title, render_html, split_markdown, to_simplified


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


def test_sources_replace_dead_xinhua_and_add_wsj_markets_feed():
    domestic_urls = [url for _, url in RSS_SOURCES["国内外要闻"]]
    finance_urls = [url for _, url in RSS_SOURCES["金融财经"]]
    assert "http://www.xinhuanet.com/politics/xhll.xml" not in domestic_urls
    assert "https://www.chinanews.com.cn/rss/china.xml" in domestic_urls
    assert "https://feeds.a.dj.com/rss/RSSMarketsMain.xml" in finance_urls


def test_traditional_characters_are_converted_to_simplified():
    assert to_simplified("華爾街日報關注經濟發展") == "华尔街日报关注经济发展"


def test_editorial_title_requires_chinese_text():
    assert clean_editorial_title("华尔街日报关注全球市场") == "华尔街日报关注全球市场"
    assert clean_editorial_title("Stocks rally") == ""
