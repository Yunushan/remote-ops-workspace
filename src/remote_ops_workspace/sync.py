from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .file_safety import write_json_atomic
from .storage import ProfileStore


class BackupService:
    """Export/import profile bundles.

    This is the local-first sync seam. Future providers can implement Git, S3,
    WebDAV, Nextcloud, GitHub Gist, or end-to-end encrypted team sync.
    """

    def __init__(self, store: ProfileStore | None = None) -> None:
        self.store = store or ProfileStore()

    def export_bundle(self, path: Path) -> None:
        data: dict[str, Any] = {
            "version": 1,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "profiles": [profile.to_dict() for profile in self.store.load()],
        }
        write_json_atomic(path, data, private=True)

    def import_bundle(self, path: Path, replace: bool = False) -> int:
        return self.store.import_from(path, replace=replace)


class DirectorySyncProvider:
    """Sync profile bundles through a mounted/shared directory.

    This covers local folders, removable media, SMB shares, WebDAV mounts, and
    cloud-sync folders such as OneDrive, Dropbox, iCloud Drive or Nextcloud.
    """

    def __init__(self, service: BackupService | None = None, filename: str = "remote-ops-workspace-sync.json") -> None:
        self.service = service or BackupService()
        self.filename = filename

    def push(self, directory: Path) -> Path:
        target = directory / self.filename
        self.service.export_bundle(target)
        return target

    def pull(self, source: Path, replace: bool = False) -> int:
        bundle = source / self.filename if source.is_dir() else source
        return self.service.import_bundle(bundle, replace=replace)
