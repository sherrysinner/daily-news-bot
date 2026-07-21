# 热搜详情与图片优化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为热搜增加可点击的二级详情入口，并为每条日报新闻提供最多两张压缩图片。

**Architecture:** `HotTopic` 保存热词、链接和说明；HTML/企业微信都基于该结构呈现。图片从正文候选中筛选、压缩并写入本次 `news/images` 产物，HTML 只引用相对路径。

**Tech Stack:** Python 3.11、requests、newspaper3k、Pillow、pytest。

## Global Constraints

- 不为微博关键词编造事实概览。
- 每条新闻最多两张图片，单张最大约 300KB。
- 中新网通用 RSS 图片不展示。

### Task 1: 热搜详情

**Files:**
- Modify: `daily-news-bot/main.py`
- Test: `daily-news-bot/tests/test_main.py`

- [ ] 写入断言：网页热搜项含 `details`、微博链接和说明；企业微信含可点击链接。
- [ ] 运行该测试，确认现有字符串热搜结构不能满足。
- [ ] 新增 `HotTopic` 并将 NewsNow 热搜行转换为标题、搜索链接和固定事实说明。
- [ ] 用 `details` 和链接渲染网页热搜，企业微信逐条输出链接。
- [ ] 运行热搜测试，确认通过。

### Task 2: 多图压缩

**Files:**
- Modify: `daily-news-bot/main.py`、`daily-news-bot/requirements.txt`
- Test: `daily-news-bot/tests/test_main.py`

- [ ] 写入断言：一条新闻最多产出两张相对图片路径，超大图会被压缩。
- [ ] 运行测试，确认现有单图缓存实现不满足。
- [ ] 收集 `newspaper3k` 的文章图片候选，使用 Pillow 缩放和压缩后写入 `news/images`。
- [ ] 网页为同一新闻渲染最多两张图片；图片不可用时保留正文。
- [ ] 运行全套 pytest 和 Python 编译检查。
