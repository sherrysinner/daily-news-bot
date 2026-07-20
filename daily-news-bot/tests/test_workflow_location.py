from pathlib import Path


def test_github_workflow_is_at_repository_root():
    repository_root = Path(__file__).resolve().parents[2]
    assert (repository_root / ".github" / "workflows" / "daily.yml").is_file()
