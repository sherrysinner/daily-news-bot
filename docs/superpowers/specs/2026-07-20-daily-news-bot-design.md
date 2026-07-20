# 每日新闻推送系统设计

## 目标

每天北京时间 8:00 自动抓取指定 RSS 与热搜关键词，经 DeepSeek API 两轮处理后，向企业微信机器人推送适合 50 岁读者阅读的中文日报，并发布可在手机阅读的静态网页。

## 架构与数据流

GitHub Actions 在 UTC 00:00 运行 `daily-news-bot/main.py`。脚本抓取 RSS 标题、摘要和链接，使用 `newspaper3k` 尝试提取正文；失败条目保留其 RSS 信息。随后抓取微博与小红书各五个热搜词。

DeepSeek 第一轮只接收新闻标题、来源和简介，返回四个板块的入选链接列表：国内外要闻最多 8 条，科技、金融财经、娱乐体育各最多 4 条。第二轮接收每条入选新闻的可用正文，返回 50 至 80 字摘要和 300 至 500 字事实整理。两轮均要求客观、中文、无网络用语、不编造、过滤标题党和健康焦虑内容。

脚本生成 `news/YYYY-MM-DD.html`，并将当天页面 URL 及其新闻锚点写入六条企业微信 Markdown 消息。工作流部署仓库中的静态文件至 GitHub Pages。

## 组件

- `main.py`：配置读取、抓取、正文提取、DeepSeek 调用、保底处理、HTML/Markdown 生成与企业微信推送。
- `requirements.txt`：固定运行依赖，包括 `feedparser`、`requests`、`newspaper3k` 与 `lxml_html_clean`。
- `.github/workflows/daily.yml`：定时/手动执行、依赖安装、运行脚本、部署 GitHub Pages。
- `news/`：每日 HTML 输出目录；其内容作为 Pages 静态站点发布。

## 接口与配置

必需环境变量：

- `DEEPSEEK_API_KEY`：DeepSeek API 密钥。
- `WECHAT_WEBHOOK_URL`：企业微信机器人 Webhook。
- `PAGE_URL`：GitHub Pages 根地址，不带末尾斜杠。

DeepSeek 使用兼容 Chat Completions 的 `https://api.deepseek.com/chat/completions`，模型默认为 `deepseek-chat`。所有模型输出必须是 JSON；解析失败时记录日志，并用来源映射与正文截取的本地保底逻辑继续生成网页和推送。

## 异常与边界

单个 RSS、正文、热搜或推送请求失败不得中断其它步骤。板块不足时按实际数量输出。新闻去重使用规范化链接和标题。企业微信每个 Markdown 请求限制为 4096 字符，超限按新闻边界拆分。静态网页使用转义后的文本，避免新闻原文注入 HTML。

## 验证

单元测试使用模拟 RSS、DeepSeek 与 Webhook 响应，覆盖分板块限额、HTML 锚点和转义、企业微信消息拆分、模型 JSON 解析失败的保底路径。执行 Python 语法编译和测试套件；工作流文件使用 YAML 解析检查。

## 部署前置条件

仓库 Settings → Pages 的 Source 设置为 GitHub Actions。Secrets 中设置上述三个变量。`PAGE_URL` 必须与实际 Pages 公开根地址一致。
