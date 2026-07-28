from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from main import (
    BilibiliVideo,
    bilibili_player_url,
    build_wechat_messages,
    load_sent_bilibili_videos,
    record_sent_bilibili_videos,
    render_html,
    select_bilibili_videos,
)


BEIJING = timezone(timedelta(hours=8))


def _row(bvid: str, title: str, published_at: datetime) -> dict[str, object]:
    return {"bvid": bvid, "title": title, "created": int(published_at.timestamp())}


def test_select_bilibili_videos_keeps_recent_unsent_and_caps_each_up() -> None:
    now = datetime(2026, 7, 28, 8, 0, tzinfo=BEIJING)
    rows = [
        _row("BVtoday", "今天发布", datetime(2026, 7, 28, 7, 0, tzinfo=BEIJING)),
        _row("BVsent", "昨天已推送", datetime(2026, 7, 27, 21, 0, tzinfo=BEIJING)),
        _row("BVyesterday", "昨天新视频", datetime(2026, 7, 27, 12, 0, tzinfo=BEIJING)),
        _row("BVthird", "应被数量限制过滤", datetime(2026, 7, 27, 9, 0, tzinfo=BEIJING)),
        _row("BVold", "前天视频", datetime(2026, 7, 26, 23, 59, tzinfo=BEIJING)),
    ]

    videos = select_bilibili_videos("央视新闻", rows, {"BVsent"}, now)

    assert [video.bvid for video in videos] == ["BVtoday", "BVyesterday"]
    assert all(video.source == "央视新闻" for video in videos)
    assert videos[0].url == "https://www.bilibili.com/video/BVtoday"


def test_sent_bilibili_history_prunes_old_entries_and_keeps_new_ones(tmp_path: Path) -> None:
    history_path = tmp_path / "sent.json"
    history_path.write_text(json.dumps({"videos": {"BVold": "2026-04-18", "BVkept": "2026-07-27"}}), encoding="utf-8")
    video = BilibiliVideo("1818黄金眼", "一条新视频", "BVnew", "https://www.bilibili.com/video/BVnew", datetime(2026, 7, 28, 7, tzinfo=BEIJING))

    record_sent_bilibili_videos(history_path, [video], "2026-07-28")

    assert load_sent_bilibili_videos(history_path) == {"BVkept", "BVnew"}


def test_bilibili_player_url_uses_embedded_player_and_bvid() -> None:
    assert bilibili_player_url("BV1abc") == "https://player.bilibili.com/player.html?bvid=BV1abc&page=1&high_quality=1&danmaku=0"


def test_bilibili_videos_render_embedded_player_and_use_it_in_wechat() -> None:
    video = BilibiliVideo("央视新闻", "测试视频", "BVnew", "https://www.bilibili.com/video/BVnew", datetime(2026, 7, 28, 7, tzinfo=BEIJING))

    page = render_html("2026-07-28", {}, {}, "https://example.test", bilibili_videos=[video])
    messages = build_wechat_messages("2026-07-28", {}, {}, "https://example.test", bilibili_videos=[video])

    assert 'src="https://player.bilibili.com/player.html?bvid=BVnew&amp;page=1&amp;high_quality=1&amp;danmaku=0"' in page
    assert 'allowfullscreen="true"' in page
    assert 'webkitallowfullscreen="true"' in page
    assert 'mozallowfullscreen="true"' in page
    assert '打开 B站原页面' in page
    assert "[观看视频](https://player.bilibili.com/player.html?bvid=BVnew&page=1&high_quality=1&danmaku=0)" in "\n".join(messages)
    assert 'class="bilibili-expand"' in page
    assert 'data-player-url="https://player.bilibili.com/player.html?bvid=BVnew&amp;page=1&amp;high_quality=1&amp;danmaku=0"' in page
    assert '放大播放' in page
    assert 'id="bilibili-overlay"' in page
    assert 'id="bilibili-overlay-frame"' in page
    assert 'overlay.classList.add("is-open")' in page
    assert 'overlayFrame.src = ""' in page
