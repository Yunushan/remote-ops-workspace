from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")

    def import_bundle(self, path: Path, replace: bool = False) -> int:
        return self.store.import_from(path, replace=replace)
