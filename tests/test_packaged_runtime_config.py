from pathlib import Path

from remote_ops_workspace import paths


def test_runtime_config_path_uses_packaged_resource_outside_repository(
    monkeypatch, tmp_path: Path
) -> None:
    repository = tmp_path / "repository"
    packaged = tmp_path / "site-packages" / "remote_ops_workspace"
    config = packaged / "configs" / "feature_manifest.json"
    config.parent.mkdir(parents=True)
    config.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(paths, "repo_root", lambda: repository)
    monkeypatch.setattr(paths, "files", lambda package: packaged)

    assert paths.runtime_config_path("feature_manifest.json") == config


def test_runtime_config_path_prefers_repository_file_during_development(
    monkeypatch, tmp_path: Path
) -> None:
    repository = tmp_path / "repository"
    config = repository / "configs" / "feature_manifest.json"
    config.parent.mkdir(parents=True)
    config.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(paths, "repo_root", lambda: repository)

    assert paths.runtime_config_path("feature_manifest.json") == config


def test_runtime_web_dir_uses_packaged_resource_outside_repository(
    monkeypatch, tmp_path: Path
) -> None:
    repository = tmp_path / "repository"
    packaged = tmp_path / "site-packages" / "remote_ops_workspace"
    web = packaged / "web"
    web.mkdir(parents=True)
    (web / "index.html").write_text("<!doctype html>", encoding="utf-8")
    monkeypatch.setattr(paths, "repo_root", lambda: repository)
    monkeypatch.setattr(paths, "files", lambda package: packaged)

    assert paths.runtime_web_dir() == web


def test_runtime_web_dir_prefers_repository_assets_during_development(
    monkeypatch, tmp_path: Path
) -> None:
    repository = tmp_path / "repository"
    web = repository / "apps" / "web"
    web.mkdir(parents=True)
    monkeypatch.setattr(paths, "repo_root", lambda: repository)

    assert paths.runtime_web_dir() == web
