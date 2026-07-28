# B站新闻视频推送 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在每日新闻中加入四个指定 UP 主当天或前一天发布、且未推送过的新闻视频。

**Architecture:** `main.py` 新增 B站视频数据模型、异步 API 查询适配层及 JSON 去重台账。渲染层将视频列表输出到静态页面与企业微信消息；工作流负责保存已发送 BV 号。

**Tech Stack:** Python 3.11、bilibili-api-python、aiohttp、GitHub Actions、企业微信 Markdown。

## Global Constraints

- 追踪央视频、央视新闻、1818黄金眼、一觉醒来发生啥四个固定 UID。
- 每个账号最多推两条；仅接受北京时间今天或昨天发布的视频。
- 以 BV 号去重，台账只保留 90 天。
- B站请求失败不得阻断日报。

---

### Task 1: 视频采集与去重台账

**Files:**
- Modify: `daily-news-bot/main.py`
- Modify: `daily-news-bot/requirements.txt`
- Test: `daily-news-bot/tests/test_main.py`

**Interfaces:**
- Produces: `fetch_bilibili_news_videos(...) -> list[BilibiliVideo]`
- Produces: `load_sent_bilibili_videos(...) -> dict[str, str]`

- [ ] 写入 UID 配置、视频模型、日期筛选与 JSON 台账测试。
- [ ] 验证测试失败。
- [ ] 使用 `bilibili-api-python` 查询固定用户投稿，过滤日期和已发送 BV 号。
- [ ] 测试通过并提交。

### Task 2: 网页、企业微信与工作流保存

**Files:**
- Modify: `daily-news-bot/main.py`
- Modify: `.github/workflows/daily.yml`
- Test: `daily-news-bot/tests/test_main.py`

**Interfaces:**
- Consumes: `list[BilibiliVideo]`
- Produces: 网页视频区块、企业微信视频消息和更新后的 `data/sent_bilibili_videos.json`。

- [ ] 写入网页及 Markdown 推送测试。
- [ ] 验证测试失败。
- [ ] 输出视频区块并允许 Actions 提交台账。
- [ ] 全量测试、编译检查并提交。
