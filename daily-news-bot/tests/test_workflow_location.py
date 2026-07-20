from pathlib import Path


def test_github_workflow_is_at_repository_root():
    repository_root = Path(__file__).resolve().parents[2]
    assert (repository_root / ".github" / "workflows" / "daily.yml").is_file()


def test_workflow_uses_defaultable_newsnow_base_url_without_a_secret():
    repository_root = Path(__file__).resolve().parents[2]
    text = (repository_root / ".github" / "workflows" / "daily.yml").read_text(encoding="utf-8")
    assert "NEWSNOW_BASE_URL: ${{ vars.NEWSNOW_BASE_URL }}" in text
    assert "secrets.NEWSNOW_BASE_URL" not in text
