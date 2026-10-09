"""Read-only native observation on disposable official Windows CI hosts.

This does not qualify private staging, other-identity denial or SDK headers.
The GitHub job owns this process; this script launches no child processes.
Its watchdog terminates this process only, not all possible OS descendants.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import stat
import sys
import threading
from pathlib import Path

ROOT = Path(os.path.abspath(__file__)).parents[1]
OUTPUT = ROOT / ".tmp/windows-default-native-public/result.json"
FILES = (
    "src/remote_ops_workspace/__init__.py",
    "src/remote_ops_workspace/file_safety.py",
    "src/remote_ops_workspace/paths.py",
    "src/remote_ops_workspace/windows_private_storage.py",
    "src/remote_ops_workspace/update_channel.py",
    "scripts/observe_windows_default_native.py",
    ".github/workflows/windows-default-native-observation.yml",
)
PHASES = ("source", "imports", "native-bind", "token", "known-folders",
          "default-selection", "default-parent", "token-after", "source-readback", "finished")
FACTS = ("native_provider_constructed", "token_observed", "known_folders_observed",
         "default_selection_observed", "default_parent_boundary_observed",
         "existing_home_private", "first_missing_component_observed", "token_unchanged")
OWNER_SCOPE = "GitHub job/step; no independent process-reaping or complete-OS-descendant attestation"
KEYS = {"schema", "source", "run", "status", "phase", "reason_code", "observed", "source_unchanged",
        "source_readback_complete", "observation_finished", "sdk_headers_qualified",
        "other_identity_denial_qualified", "staging_qualified", "complete", "readiness_credit", "process_owner", "parent_observation"}


def require(condition):
    if not condition:
        raise ValueError("native-observation-input-refused")


def parent_observation():
    return {"ancestor_index": None, "ancestor_role": None, "snapshot_observed": False,
            "directory_attribute": None, "owner_class": None, "observer_live_handle_count": 0}


def validate_parent_observation(value):
    require(type(value) is dict and set(value) == set(parent_observation()))
    require(type(value["snapshot_observed"]) is bool
            and type(value["observer_live_handle_count"]) is int
            and 0 <= value["observer_live_handle_count"] <= 64)
    index, role = value["ancestor_index"], value["ancestor_role"]
    if index is None:
        require(role is None and not value["snapshot_observed"]
                and value["observer_live_handle_count"] == 0)
    else:
        require(type(index) is int and 0 <= index <= 63
                and role in ("volume-root", "parent", "home")
                and ((index == 0) is (role == "volume-root")))
    if value["snapshot_observed"]:
        require(index is not None and type(value["directory_attribute"]) is bool
                and value["owner_class"] in ("current-user", "system", "administrators", "other"))
    else:
        require(value["directory_attribute"] is None and value["owner_class"] is None)


class ParentObservation:
    """Transparent read-only delegate; private paths/handles/SIDs stay in memory.

    This adds no native calls and applies none of the storage policy itself.
    A live-handle count is local bookkeeping, not independent cleanup proof.
    """
    def __init__(self, native, user, home, storage, record):
        self.native, self.user, self.storage, self.record = native, user, storage, record
        ancestors = storage._ancestors(home)
        self.positions = {path: (index, "volume-root" if index == 0 else
                                 "home" if index == len(ancestors) - 1 else "parent")
                          for index, path in enumerate(ancestors)}
        self.handles = {}

    def token_user(self):
        return self.native.token_user()

    def _prepare(self, position):
        self.record.update(ancestor_index=position[0], ancestor_role=position[1],
                           snapshot_observed=False, directory_attribute=None, owner_class=None)

    def open_directory(self, path):
        position = self.positions[path]
        self._prepare(position)
        handle = self.native.open_directory(path)
        self.handles[handle] = position
        self.record["observer_live_handle_count"] = len(self.handles)
        return handle

    def snapshot(self, handle):
        self._prepare(self.handles[handle])
        snapshot = self.native.snapshot(handle)
        owner = ("current-user" if snapshot.owner == self.user else
                 "system" if snapshot.owner == self.storage.SYSTEM_SID else
                 "administrators" if snapshot.owner == self.storage.ADMINISTRATORS_SID else "other")
        self.record.update(snapshot_observed=True, directory_attribute=bool(snapshot.attributes & self.storage.DIRECTORY),
                           owner_class=owner)
        return snapshot

    def close(self, handle):
        self.native.close(handle)
        del self.handles[handle]
        self.record["observer_live_handle_count"] = len(self.handles)


def ordinary(path, *, file):
    item = path.lstat()
    require(not item.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)
    require(stat.S_ISREG(item.st_mode) if file else stat.S_ISDIR(item.st_mode))
    for parent in path.parents:
        parent_item = parent.lstat()
        require(stat.S_ISDIR(parent_item.st_mode)
                and not parent_item.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)
    return item


def read_file(path, maximum):
    before = ordinary(path, file=True)
    require(before.st_nlink == 1 and 0 < before.st_size <= maximum)
    path_keys = ("st_dev", "st_ino", "st_mode", "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns", "st_file_attributes")
    descriptor_keys = ("st_dev", "st_ino", "st_mode", "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns")
    shared_keys = ("st_dev", "st_ino", "st_size", "st_mtime_ns")
    with path.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        # Compare only shared Windows metadata across APIs; preserve complete
        # identities within each API before/after the bounded byte read.
        require(stat.S_ISREG(opened.st_mode) and opened.st_nlink == 1
                and all(getattr(before, key) == getattr(opened, key) for key in shared_keys))
        raw = stream.read(maximum + 1)
        closed = os.fstat(stream.fileno())
        require(all(getattr(opened, key) == getattr(closed, key) for key in descriptor_keys))
    after = ordinary(path, file=True)
    require(0 < len(raw) <= maximum and len(raw) == before.st_size
            and all(getattr(before, key) == getattr(after, key) for key in path_keys))
    return raw, tuple(getattr(after, key) for key in path_keys)


def context():
    require(os.name == "nt" and os.environ.get("GITHUB_ACTIONS") == "true"
            and os.environ.get("RUNNER_OS") == "Windows"
            and os.environ.get("RUNNER_ENVIRONMENT") == "github-hosted"
            and os.environ.get("GITHUB_REPOSITORY") == "Yunushan/remote-ops-workspace"
            and os.environ.get("GITHUB_EVENT_NAME") == "pull_request"
            and not os.environ.get("ROW_HOME"))
    require(os.path.normcase(str(ROOT)) == os.path.normcase(os.environ.get("GITHUB_WORKSPACE", "")))
    ordinary(ROOT, file=False)
    head = os.environ.get("ROW_EXPECTED_SOURCE_SHA", "")
    tree = os.environ.get("ROW_OBSERVED_TREE", "")
    require(re.fullmatch(r"[0-9a-f]{40}", head) is not None
            and os.environ.get("ROW_OBSERVED_HEAD") == head
            and re.fullmatch(r"[0-9a-f]{40}", tree) is not None)
    run = {"id": os.environ.get("GITHUB_RUN_ID", ""), "attempt": os.environ.get("GITHUB_RUN_ATTEMPT", "")}
    require(all(re.fullmatch(r"[0-9]{1,20}", value) is not None for value in run.values()))
    return head, tree, run


def sources():
    rows, identities, contents = [], {}, {}
    for name in FILES:
        raw, identities[name] = read_file(ROOT / name, 131072)
        contents[name] = raw
        rows.append({"path": name, "size": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
    gate_tree = ast.parse(contents["src/remote_ops_workspace/update_channel.py"])
    gates = [node.value for node in gate_tree.body if isinstance(node, ast.Assign)
             and any(isinstance(target, ast.Name) and target.id == "_WINDOWS_PRIVATE_STAGE_QUALIFIED"
                     for target in node.targets)]
    require(len(gates) == 1 and isinstance(gates[0], ast.Constant) and gates[0].value is False)
    native_tree = ast.parse(contents["src/remote_ops_workspace/windows_private_storage.py"])
    codes = set()
    for node in ast.walk(native_tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            argument = (node.args[-1] if node.func.id == "_require" and len(node.args) == 2 else
                        node.args[0] if node.func.id in {"PrivateStorageError", "PrivatePathMissing"} and node.args else None)
            if isinstance(argument, ast.Constant) and type(argument.value) is str:
                codes.add(argument.value)
    require(1 <= len(codes) <= 128 and all(re.fullmatch(r"[a-z0-9-]{1,80}", code) for code in codes))
    return rows, identities, codes


def checkpoint(record):
    raw = (json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n").encode()
    require(len(raw) <= 32768)
    temporary = OUTPUT.with_name("result.tmp")
    with temporary.open("xb") as stream:
        stream.write(raw)
    temporary.replace(OUTPUT)


def capture():
    head, tree, run = context()
    before, identities, codes = sources()
    base = OUTPUT.parent.parent
    try:
        ordinary(base, file=False)
    except FileNotFoundError:
        base.mkdir()
        ordinary(base, file=False)
    try:
        OUTPUT.parent.lstat()
    except FileNotFoundError:
        pass
    else:
        require(False)
    OUTPUT.parent.mkdir()
    ordinary(OUTPUT.parent, file=False)
    record = {"schema": "row.windows-default-native-readonly.v2", "source": {"head": head, "tree": tree, "files": before},
              "run": run, "status": "running", "phase": "source", "reason_code": None,
              "observed": dict.fromkeys(FACTS, False), "source_unchanged": False, "source_readback_complete": False,
              "observation_finished": False, "sdk_headers_qualified": False, "other_identity_denial_qualified": False,
              "staging_qualified": False, "complete": False, "readiness_credit": 0,
              "process_owner": OWNER_SCOPE, "parent_observation": parent_observation()}
    checkpoint(record)
    watchdog = threading.Timer(110, lambda: os._exit(124))
    watchdog.daemon = True
    watchdog.start()
    try:
        def phase(name):
            record["phase"] = name
            checkpoint(record)

        phase("imports")
        sys.path.insert(0, str(ROOT / "src"))
        from remote_ops_workspace import paths
        from remote_ops_workspace import windows_private_storage as storage

        phase("native-bind")
        native = storage._Native()
        record["observed"]["native_provider_constructed"] = True
        phase("token")
        user = native.token_user()
        record["observed"]["token_observed"] = True
        phase("known-folders")
        for role in ("roaming", "local"):
            for default in (False, True):
                native.known_folder(role, default=default)
        record["observed"]["known_folders_observed"] = True
        phase("default-selection")
        home = storage._selected_home(native, str(paths.data_dir()), os.environ)
        record["observed"]["default_selection_observed"] = True
        phase("default-parent")
        observer = ParentObservation(native, user, home, storage, record["parent_observation"])
        with storage.private_home_guard(home, _native=observer) as guard:
            guard.verify()
            record["observed"]["existing_home_private"] = guard.missing_path is None
            record["observed"]["first_missing_component_observed"] = guard.missing_path is not None
        record["observed"]["default_parent_boundary_observed"] = True
        phase("token-after")
        if native.token_user() != user:
            raise storage.PrivateStorageError("native-token-changed")
        record["observed"]["token_unchanged"] = True
        phase("source-readback")
        after, after_identities, after_codes = sources()
        require(after == before and after_identities == identities and after_codes == codes)
        record.update(source_unchanged=True, source_readback_complete=True,
                      observation_finished=True, status="observed", phase="finished")
        checkpoint(record)
        return 0
    except BaseException as exc:
        candidate = exc.args[0] if len(exc.args) == 1 and type(exc.args[0]) is str else None
        record.update(status="refused", observation_finished=False,
                      phase=record["phase"] if record["phase"] != "finished" else "source-readback",
                      reason_code=candidate if candidate in codes else "native-observation-runtime-refused")
        # Preserve the original refusal. Failed native observation must still
        # report whether all selected source bytes/identities were read back.
        try:
            after, after_identities, after_codes = sources()
            require(after == before and after_identities == identities and after_codes == codes)
            record.update(source_unchanged=True, source_readback_complete=True)
        except BaseException:
            pass
        checkpoint(record)
        return 1
    finally:
        watchdog.cancel()


def publish():
    head, tree, run = context()
    current, _identities, codes = sources()
    raw, _identity = read_file(OUTPUT, 32768)
    value = json.loads(raw)
    require(type(value) is dict and set(value) == KEYS and value["process_owner"] == OWNER_SCOPE
            and value["schema"] == "row.windows-default-native-readonly.v2"
            and value["source"] == {"head": head, "tree": tree, "files": current} and value["run"] == run)
    require(value["status"] in {"running", "refused", "observed"} and value["phase"] in PHASES
            and (value["reason_code"] is None or value["reason_code"] in codes | {"native-observation-runtime-refused"}))
    require(set(value["observed"]) == set(FACTS) and all(type(flag) is bool for flag in value["observed"].values()))
    require(all(value[key] is False for key in ("sdk_headers_qualified", "other_identity_denial_qualified", "staging_qualified", "complete"))
            and type(value["readiness_credit"]) is int and value["readiness_credit"] == 0)
    require(all(type(value[key]) is bool for key in ("source_unchanged", "source_readback_complete", "observation_finished")))
    require(value["source_unchanged"] is value["source_readback_complete"])
    validate_parent_observation(value["parent_observation"])
    if value["status"] == "observed":
        require(value["phase"] == "finished" and value["reason_code"] is None
                and value["source_unchanged"] and value["source_readback_complete"] and value["observation_finished"]
                and value["parent_observation"]["observer_live_handle_count"] == 0)
        require(all(value["observed"][key] for key in FACTS if key not in
                    {"existing_home_private", "first_missing_component_observed"}))
        require(value["observed"]["existing_home_private"] != value["observed"]["first_missing_component_observed"])
    else:
        require(not value["observation_finished"] and value["phase"] != "finished")
        require((value["reason_code"] is None) is (value["status"] == "running"))
    print("Bounded read-only native observation receipt validated; staging qualification remains false.")


if __name__ == "__main__":
    try:
        require(len(sys.argv) == 2 and sys.argv[1] in {"capture", "publish"})
        result = capture() if sys.argv[1] == "capture" else publish()
    except BaseException:
        print("native-observation-input-or-runtime-refused")
        result = 1
    raise SystemExit(result)
