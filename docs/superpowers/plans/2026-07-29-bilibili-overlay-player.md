# B站视频放大播放 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在日报静态网页中为 B站视频提供不依赖原生全屏权限的放大播放遮罩。

**Architecture:** 视频卡片按钮通过 `data-player-url` 把官方播放器地址传给一个全局遮罩。内嵌脚本负责打开、关闭、清空 iframe 和恢复滚动；CSS 让遮罩覆盖整个视口。

**Tech Stack:** Python 3.11、静态 HTML/CSS/JavaScript、pytest。

## Global Constraints

- 不下载、缓存、转码或代理视频。
- 继续保留卡片内播放器和原页面备用链接。
- 遮罩关闭后清空播放器地址。
- 全部 pytest 通过后才提交。

---

### Task 1: 为视频卡片输出遮罩所需标记

**Files:**
- Modify: `daily-news-bot/main.py`
- Modify: `daily-news-bot/tests/test_bilibili.py`

**Interfaces:**
- Consumes: `bilibili_player_url(video.bvid)`
- Produces: `button.bilibili-expand`，含 `data-player-url` 与 `data-title`。

- [ ] **Step 1: 写失败测试**

```python
assert 'class="bilibili-expand"' in page
assert 'data-player-url="https://player.bilibili.com/player.html?bvid=BVnew&amp;page=1&amp;high_quality=1&amp;danmaku=0"' in page
assert '放大播放' in page
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_bilibili.py -q`
Expected: FAIL，因为按钮尚未输出。

- [ ] **Step 3: 最小实现**

在每张视频卡片内添加按钮；补齐 iframe 的官方全屏属性。

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_bilibili.py -q`
Expected: PASS。

### Task 2: 输出并验证全屏遮罩

**Files:**
- Modify: `daily-news-bot/main.py`
- Modify: `daily-news-bot/tests/test_bilibili.py`

**Interfaces:**
- Consumes: `.bilibili-expand` 的 data 属性。
- Produces: `#bilibili-overlay`、`#bilibili-overlay-frame` 和关闭行为脚本。

- [ ] **Step 1: 写失败测试**

```python
assert 'id="bilibili-overlay"' in page
assert 'id="bilibili-overlay-frame"' in page
assert 'overlay.classList.add("is-open")' in page
assert 'overlayFrame.src = ""' in page
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_bilibili.py -q`
Expected: FAIL，因为遮罩和脚本不存在。

- [ ] **Step 3: 最小实现**

输出覆盖视口的遮罩、关闭按钮和脚本；支持点击空白区域及 Escape 关闭，并锁定页面滚动。

- [ ] **Step 4: 完整验证并提交**

Run: `python -m pytest -q -p no:cacheprovider --basetemp .test-tmp`
Expected: 全部 PASS。

```bash
git add daily-news-bot/main.py daily-news-bot/tests/test_bilibili.py docs/superpowers/plans/2026-07-29-bilibili-overlay-player.md
git commit -m "feat: add Bilibili overlay player"
```
