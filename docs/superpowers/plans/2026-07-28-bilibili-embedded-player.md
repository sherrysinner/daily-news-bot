# B站嵌入式播放器 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在日报网页中直接播放 B 站新闻视频，并让企业微信跳转到可播放的官方嵌入式播放器。

**Architecture:** `BilibiliVideo` 根据 BV 号派生官方播放器 URL，同时继续保存原详情页 URL。HTML 使用响应式 iframe 内嵌播放器；企业微信使用播放器地址且网页提供备用详情页链接。

**Tech Stack:** Python 3.11、静态 HTML、pytest。

## Global Constraints

- 不下载、缓存或转码 B 站视频。
- 保留原始 B 站详情页作为备用链接。
- iframe 使用官方 `player.bilibili.com` 地址和 `allowfullscreen`。
- 全部测试通过后才提交功能代码。

---

### Task 1: 生成播放器地址并覆盖消息链接

**Files:**
- Modify: `daily-news-bot/main.py`
- Modify: `daily-news-bot/tests/test_bilibili.py`

**Interfaces:**
- Produces: `bilibili_player_url(bvid: str) -> str`
- Consumes: `BilibiliVideo.bvid`

- [ ] **Step 1: 写失败测试**

```python
def test_bilibili_player_url_uses_embedded_player_and_bvid() -> None:
    assert bilibili_player_url("BV1abc") == "https://player.bilibili.com/player.html?bvid=BV1abc&page=1&high_quality=1&danmaku=0"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_bilibili.py -q`
Expected: `ImportError`，因为函数尚未定义。

- [ ] **Step 3: 最小实现**

```python
def bilibili_player_url(bvid: str) -> str:
    return f"https://player.bilibili.com/player.html?bvid={quote(bvid)}&page=1&high_quality=1&danmaku=0"
```

将企业微信视频消息的“观看视频”链接改为此函数返回值。

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_bilibili.py -q`
Expected: PASS。

### Task 2: 将网页视频卡片改为内嵌播放器

**Files:**
- Modify: `daily-news-bot/main.py`
- Modify: `daily-news-bot/tests/test_bilibili.py`

**Interfaces:**
- Consumes: `bilibili_player_url(video.bvid)` 与 `video.url`
- Produces: 包含播放器 iframe 和备用详情页链接的 HTML 视频卡片。

- [ ] **Step 1: 写失败测试**

```python
page = render_html("2026-07-28", {}, {}, "https://example.test", bilibili_videos=[video])
assert 'src="https://player.bilibili.com/player.html?bvid=BVnew&amp;page=1&amp;high_quality=1&amp;danmaku=0"' in page
assert 'allowfullscreen' in page
assert '打开 B站原页面' in page
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_bilibili.py -q`
Expected: FAIL，因为现有页面只显示普通详情页链接。

- [ ] **Step 3: 最小实现**

使用 `.bilibili-player` 容器固定 16:9 比例；iframe 带 `allow="autoplay; fullscreen"`、`allowfullscreen` 和标题。视频卡片下方保留原详情页链接。

- [ ] **Step 4: 完整验证并提交**

Run: `python -m pytest -q -p no:cacheprovider --basetemp .test-tmp`
Expected: 全部 PASS。

```bash
git add daily-news-bot/main.py daily-news-bot/tests/test_bilibili.py docs/superpowers/plans/2026-07-28-bilibili-embedded-player.md
git commit -m "feat: embed Bilibili news videos"
```
