from pathlib import Path

import pytest

import remote_ops_workspace.paths as paths


@pytest.mark.parametrize(
    ("system", "expected"),
    [
        ("Darwin", Path("home/Library/Application Support/RemoteOpsWorkspace")),
        ("Linux", Path("home/.config/remote-ops-workspace")),
    ],
)
def test_data_dir_uses_platform_defaults(monkeypatch, system: str, expected: Path) -> None:
    monkeypatch.delenv("ROW_HOME", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setattr(paths.platform, "system", lambda: system)
    monkeypatch.setattr(paths.Path, "home", classmethod(lambda cls: Path("home")))

    assert paths.data_dir() == expected


def test_runtime_paths_fail_clearly_when_assets_are_missing(tmp_path, monkeypatch) -> None:
    repository = tmp_path / "repository"
    package = tmp_path / "package"
    repository.mkdir()
    package.mkdir()
    monkeypatch.setattr(paths, "repo_root", lambda: repository)
    monkeypatch.setattr(paths, "files", lambda _package: package)

    with pytest.raises(FileNotFoundError, match="runtime configuration is missing"):
        paths.runtime_config_path("missing.json")
    with pytest.raises(FileNotFoundError, match="Web/PWA assets are missing"):
        paths.runtime_web_dir()


def test_data_dir_honors_portable_home(tmp_path, monkeypatch) -> None:
    portable = tmp_path / "portable"
    monkeypatch.setenv("ROW_HOME", str(portable))

    assert paths.data_dir() == portable.resolve()


def test_runtime_paths_use_packaged_resources(tmp_path, monkeypatch) -> None:
    repository = tmp_path / "repository"
    package = tmp_path / "package"
    config = package / "configs" / "present.json"
    web = package / "web"
    repository.mkdir()
    config.parent.mkdir(parents=True)
    config.write_text("{}", encoding="utf-8")
    web.mkdir()
    monkeypatch.setattr(paths, "repo_root", lambda: repository)
    monkeypatch.setattr(paths, "files", lambda _package: package)

    assert paths.runtime_config_path("present.json") == config
    assert paths.runtime_web_dir() == web


def test_runtime_web_dir_prefers_repository_assets(tmp_path, monkeypatch) -> None:
    repository = tmp_path / "repository"
    web = repository / "apps" / "web"
    web.mkdir(parents=True)
    monkeypatch.setattr(paths, "repo_root", lambda: repository)
    monkeypatch.setattr(
        paths,
        "files",
        lambda _package: (_ for _ in ()).throw(AssertionError("package fallback used")),
    )

    assert paths.runtime_web_dir() == web
