# 日报与 Pages 发布分离设计

## 目标

将每日新闻生成、企业微信推送与 GitHub Pages 发布拆为两个 GitHub Actions 任务。Pages 发布排队或超时时，可以只重试发布任务，不重复发送企业微信。

## 结构

`build-and-send` 任务负责安装 Python 依赖、运行 `daily-news-bot/main.py`、保存 B 站已发送记录，并上传 `daily-news-bot` 为 Pages 工件。它不配置 Pages 环境，也不调用部署动作。

`deploy-pages` 任务依赖 `build-and-send` 成功完成。它下载前一任务的 Pages 工件并调用 GitHub 官方 Pages 部署动作。GitHub Pages 环境 URL 仅放在该任务中。

## 失败处理

新闻生成失败时，发布任务不运行。Pages 发布失败时，新闻已经生成和推送；之后在 Actions 中选择仅重试失败任务，只会重新下载同一份网页工件并再次请求 Pages 发布。

## 验证

测试应验证工作流存在两个任务、发布任务依赖生成任务、网页工件在两个任务之间传递，且企业微信密钥只出现在生成任务中。
