# 定时送达与阅读质量修复 Implementation Plan

**Goal:** 改善日报的送达时间、图片稳定性、摘要降级与热搜阅读体验。

### Task 1: 北京时间日期与避开整点的调度

- [ ] 为 `beijing_today()` 写测试，确认 UTC 23:45 对应次日北京时间。
- [ ] 将 `main()` 的日期改为使用 `zoneinfo.ZoneInfo("Asia/Shanghai")`。
- [ ] 将 workflow cron 从 `0 0 * * *` 改为 `45 23 * * *`。
- [ ] 为 workflow 增加 cron 断言并运行完整测试。

### Task 2: 本地缓存有效图片

- [ ] 写测试：中新网来源不允许展示图片；成功下载图片后返回相对 `images/` 路径；非图片响应返回空字符串。
- [ ] 实现 `cache_article_image()`，仅下载 HTTP 图片、检查 Content-Type、使用 SHA-256 文件名写入 `news/images/`。
- [ ] 在选中新闻完成整理后缓存配图；HTML 仅引用本地相对路径或现有可信 URL。
- [ ] 运行完整测试。

### Task 3: 保留可读摘要并格式化热搜

- [ ] 写测试：有结尾标点的短摘要保留；RSS 简介首句优先于通用提示；HTML 热搜生成有序列表。
- [ ] 增加 `is_usable_summary()` 与 `fallback_summary()`；调整 AI 整理回退。
- [ ] 改造 HTML 与企业微信热搜为编号列表。
- [ ] 运行完整测试和语法检查。
