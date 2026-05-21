from pathlib import Path

from remote_ops_workspace.models import Profile
from remote_ops_workspace.storage import ProfileStore
from remote_ops_workspace.sync import BackupService, DirectorySyncProvider


def test_directory_sync_provider_push_pull(tmp_path: Path) -> None:
    source = ProfileStore(tmp_path / "source.json")
    source.add(Profile(name="edge", protocol="ssh", host="192.0.2.10"))
    provider = DirectorySyncProvider(BackupService(source))
    bundle = provider.push(tmp_path / "cloud")

    target = ProfileStore(tmp_path / "target.json")
    count = DirectorySyncProvider(BackupService(target)).pull(bundle)

    assert count == 1
    assert target.get("edge").host == "192.0.2.10"
