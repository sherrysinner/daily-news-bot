from main import NewsItem, render_html, split_markdown


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
