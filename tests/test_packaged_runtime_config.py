import sys
from pathlib import Path

import pytest

from remote_ops_workspace import moba_mobapt, moba_servers, paths, x11


@pytest.mark.parametrize("frozen", [True, False], ids=["frozen", "source"])
@pytest.mark.parametrize(("resolver", "env_var", "runtime"), [
    (x11.x_server_packaged_runtime_roots, x11.XSERVER_RUNTIME_DIR_ENV, "xserver"),
    (moba_servers.moba_server_runtime_roots, moba_servers.SERVER_RUNTIME_DIR_ENV, "servers"),
    (moba_mobapt.mobapt_runtime_roots, moba_mobapt.MOBAPT_RUNTIME_DIR_ENV, "mobapt"),
])
def test_vendor_runtime_roots_are_source_only(resolver, env_var, runtime, frozen, monkeypatch, tmp_path):
    explicit = tmp_path / "explicit"
    configured = tmp_path / "configured"
    install_bin = tmp_path / "install" / "bin"
    monkeypatch.setenv(env_var, str(configured))
    monkeypatch.setattr(sys, "executable", str(install_bin / "row"))
    monkeypatch.setattr(sys, "frozen", frozen, raising=False)

    expected = [explicit, configured, install_bin / runtime, install_bin / "runtimes" / runtime]
    if not frozen:
        expected.append(paths.repo_root() / "vendor" / runtime)
    assert resolver([explicit]) == tuple(expected)


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



def test_frozen_runtime_config_and_web_require_bundle_resources(monkeypatch, tmp_path: Path) -> None:
    outside_bundle = tmp_path / "parent"
    outside_config = outside_bundle / "configs" / "platform_targets.json"
    outside_config.parent.mkdir(parents=True)
    outside_config.write_text("{}", encoding="utf-8")
    (outside_bundle / "apps" / "web").mkdir(parents=True)
    packaged = tmp_path / "extracted" / "remote_ops_workspace"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(paths, "repo_root", lambda: outside_bundle)
    monkeypatch.setattr(paths, "files", lambda _package: packaged)

    with pytest.raises(FileNotFoundError, match="runtime configuration is missing"):
        paths.runtime_config_path("platform_targets.json")
    with pytest.raises(FileNotFoundError, match="packaged Web/PWA assets are missing"):
        paths.runtime_web_dir()

    config = packaged / "configs" / "platform_targets.json"
    config.parent.mkdir(parents=True)
    config.write_text("{}", encoding="utf-8")
    web = packaged / "web"
    web.mkdir()
    assert paths.runtime_config_path("platform_targets.json") == config
    assert paths.runtime_web_dir() == web
