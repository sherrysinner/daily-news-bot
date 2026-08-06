# 日报与 Pages 发布分离 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 GitHub Pages 发布失败时可以单独重试发布任务，不重复发送企业微信。

**Architecture:** 保留 `build-and-send` 负责编译日报、发送企业微信与上传 Pages 工件；新建 `deploy-pages` 仅下载该工件并发布。第二个任务以 `needs` 依赖第一个任务，因而 GitHub 的“重试失败任务”不会重新执行日报脚本。

**Tech Stack:** GitHub Actions、GitHub Pages 官方 actions、Python pytest。

## Global Constraints

- 继续使用 Python 3.11 与现有 Secrets/Variables。
- 企业微信密钥只在 `build-and-send` 任务可用。
- Pages 部署使用 `actions/deploy-pages@v4`。

---

### Task 1: 为双任务工作流添加回归测试

**Files:**
- Modify: `daily-news-bot/tests/test_workflow_location.py`
- Test: `daily-news-bot/tests/test_workflow_location.py`

**Interfaces:**
- Consumes: 仓库根目录 `.github/workflows/daily.yml`。
- Produces: 对任务名称、依赖关系和密钥作用域的自动校验。

- [ ] **Step 1: 写出失败测试**

```python
def test_workflow_separates_build_from_pages_deploy():
    text = workflow_text()
    assert "build-and-send:" in text
    assert "deploy-pages:" in text
    assert "needs: build-and-send" in text


def test_wechat_secret_is_limited_to_build_job():
    build, deploy = workflow_text().split("  deploy-pages:", maxsplit=1)
    assert "WECHAT_WEBHOOK_URL: ${{ secrets.WECHAT_WEBHOOK_URL }}" in build
    assert "WECHAT_WEBHOOK_URL" not in deploy
```

- [ ] **Step 2: 运行测试，确认现有单任务工作流失败**

Run: `python -m pytest -q tests/test_workflow_location.py`

Expected: FAIL，因为当前工作流没有 `build-and-send` 和 `deploy-pages` 两个任务。

- [ ] **Step 3: 实现最小测试辅助函数和断言**

```python
def workflow_text() -> str:
    repository_root = Path(__file__).resolve().parents[2]
    return (repository_root / ".github" / "workflows" / "daily.yml").read_text(encoding="utf-8")
```

- [ ] **Step 4: 运行目标测试，确认仍因尚未修改工作流而失败**

Run: `python -m pytest -q tests/test_workflow_location.py`

Expected: FAIL，失败信息指向双任务结构断言。

### Task 2: 拆分 GitHub Actions 任务

**Files:**
- Modify: `.github/workflows/daily.yml`
- Test: `daily-news-bot/tests/test_workflow_location.py`

**Interfaces:**
- Consumes: `daily-news-bot/main.py` 生成的 `daily-news-bot/news/` 静态内容。
- Produces: 名为 `github-pages` 的上传工件；`deploy-pages` 独立发布该工件。

- [ ] **Step 1: 将现有任务改名为生成任务**

```yaml
jobs:
  build-and-send:
    runs-on: ubuntu-latest
```

删除该任务的 `environment` 块，保留抓取、发送、记录与 `actions/upload-pages-artifact@v3` 步骤。

- [ ] **Step 2: 新增只负责发布的任务**

```yaml
  deploy-pages:
    needs: build-and-send
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - name: Deploy to GitHub Pages
        id: deployment
        uses: actions/deploy-pages@v4
```

- [ ] **Step 3: 运行工作流结构测试**

Run: `python -m pytest -q tests/test_workflow_location.py`

Expected: PASS。

### Task 3: 完整验证与提交

**Files:**
- Modify: `.github/workflows/daily.yml`
- Modify: `daily-news-bot/tests/test_workflow_location.py`

**Interfaces:**
- Consumes: 项目所有 pytest 测试。
- Produces: 可推送的工作流改动。

- [ ] **Step 1: 运行完整测试集**

Run: `python -m pytest -q -p no:cacheprovider`

Expected: 全部通过。

- [ ] **Step 2: 检查工作流的发布动作只出现一次且位于 `deploy-pages`**

Run: `rg -n "build-and-send:|deploy-pages:|WECHAT_WEBHOOK_URL|upload-pages-artifact|deploy-pages@v4" .github/workflows/daily.yml`

Expected: 企业微信密钥位于生成任务；发布 action 位于发布任务。

- [ ] **Step 3: 提交改动**

```bash
git add .github/workflows/daily.yml daily-news-bot/tests/test_workflow_location.py docs/superpowers/plans/2026-08-06-pages-deploy-separation.md
git commit -m "fix: separate Pages deployment from news delivery"
```
