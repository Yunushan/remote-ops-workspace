"""Shared disposable Android API36 tools. Missing browser qualification refuses."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import queue
import re
import secrets
import socket
import stat
import struct
import subprocess
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASELINE = "0c4834fff7f11e5259699c340f071a872b806214"
SOURCE = os.environ.get("ROW_EXPECTED_HEAD", BASELINE)
SERIAL, ADB_PORT = "emulator-5556", 5039
BROWSER_SECONDS = 120  # Original probe deadline; no late-result recovery.
REQUIRED = {"Chrome-CDP-identity", "policy-allow", "policy-inactive", "policy-deny", "policy-restricted",
            "policy-malformed", "policy-reject", "policy-timeout", "policy-pending", "locked-match", "locked-mismatch",
            "profile-storage-reload", "no-opener-tab-isolation", "horizontal-vertical-clear", "service-worker-source-cache",
            "owned-server-down-offline", "same-origin-restart-new-add"}


class Refusal(ValueError):
    """Fixed public refusal; raw tool/device output stays private."""


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read_plain(path, maximum):
    before = path.lstat()
    if path.is_symlink() or not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or not 0 < before.st_size <= maximum:
        raise Refusal("plain-bounded-input-required")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "rb") as stream:
        opened = os.fstat(stream.fileno())
        raw = stream.read(before.st_size + 1)
        after = os.fstat(stream.fileno())
    after_path = path.lstat()

    def fields(row):
        return row.st_dev, row.st_ino, row.st_size, row.st_mtime_ns, row.st_ctime_ns

    if fields(before) != fields(after_path) or fields(opened) != fields(after) or fields(before)[:4] != fields(opened)[:4] or len(raw) != before.st_size:
        raise Refusal("input-identity-changed")
    return raw


def digest(value):
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise Refusal("unobserved-exact-digest")
    return value


def host_guard(root):
    wanted = {"GITHUB_ACTIONS": "true", "RUNNER_ENVIRONMENT": "github-hosted", "RUNNER_OS": "Linux", "RUNNER_ARCH": "X64",
              "GITHUB_REPOSITORY": "Yunushan/remote-ops-workspace", "ROW_EXPECTED_HEAD": SOURCE}
    if (re.fullmatch(r"[0-9a-f]{40}", SOURCE) is None or os.environ.get("GITHUB_SHA") != SOURCE
            or any(os.environ.get(k) != v for k, v in wanted.items()) or platform.system() != "Linux"
            or platform.machine() != "x86_64" or root.is_symlink() or root.resolve() != root
            or Path(os.environ.get("GITHUB_WORKSPACE", "")).resolve() != root
            or any(re.fullmatch(r"[1-9][0-9]{0,19}", os.environ.get(k, "")) is None for k in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT"))):
        raise Refusal("actual-official-host-source-run-required")


def validate_pins(record):
    expected = {"schema", "source_sha", "playwright_version", "npm_lock_sha256", "npm_tree_sha256",
                "sdk_tree_sha256", "tools", "qualified_contract_receipt_sha256"}
    if not isinstance(record, dict) or set(record) != expected or record["schema"] != "row.android-cdp-public-stack.v1":
        raise Refusal("unqualified-stack-schema")
    if record["source_sha"] != SOURCE or record["playwright_version"] != "1.56.1":
        raise Refusal("stack-source-or-version-mismatch")
    for key in expected & {"npm_lock_sha256", "npm_tree_sha256", "sdk_tree_sha256", "qualified_contract_receipt_sha256"}:
        digest(record[key])
    tools = record["tools"]
    if not isinstance(tools, dict) or set(tools) != {"adb", "emulator", "avdmanager", "node"}:
        raise Refusal("qualified-tool-inventory-required")
    for row in tools.values():
        if (not isinstance(row, dict) or set(row) != {"path", "sha256"} or not isinstance(row["path"], str)
                or not row["path"].startswith("/") or len(row["path"]) > 1024 or ".." in row["path"].split("/")
                or any(ord(c) < 32 or ord(c) == 127 for c in row["path"])):
            raise Refusal("qualified-tool-identity-required")
        digest(row["sha256"])
    return record


def tree_digest(root, maximum_files=12000, maximum_bytes=256 * 1024 * 1024):
    if root.is_symlink() or root.resolve() != root:
        raise Refusal("tree-root-alias")
    pending, rows, total = [root], [], 0
    while pending:
        path = pending.pop()
        info = path.lstat()
        if len(rows) + len(pending) + 1 > maximum_files or path.is_symlink():
            raise Refusal("tree-node-bound-or-link")
        if stat.S_ISDIR(info.st_mode):
            with os.scandir(path) as children:
                for child in children:
                    if len(rows) + len(pending) + 1 >= maximum_files:
                        raise Refusal("tree-node-bound")
                    pending.append(Path(child.path))
            rows.append({"path": path.relative_to(root).as_posix(), "kind": "directory"})
        elif stat.S_ISREG(info.st_mode):
            total += info.st_size
            if total > maximum_bytes:
                raise Refusal("tree-total-byte-bound")
            if info.st_nlink != 1:
                raise Refusal("tree-hardlink")
            state = hashlib.sha256()
            size = 0
            with path.open("rb") as stream:
                opened = os.fstat(stream.fileno())
                while chunk := stream.read(1024 * 1024):
                    size += len(chunk)
                    if size > info.st_size or size > maximum_bytes:
                        raise Refusal("tree-file-size-changed")
                    state.update(chunk)
                after_fd = os.fstat(stream.fileno())
            after_path = path.lstat()
            if (size != info.st_size or (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
                    != (after_path.st_dev, after_path.st_ino, after_path.st_size, after_path.st_mtime_ns, after_path.st_ctime_ns)
                    or (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns)
                    != (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
                    or (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns, opened.st_ctime_ns)
                    != (after_fd.st_dev, after_fd.st_ino, after_fd.st_size, after_fd.st_mtime_ns, after_fd.st_ctime_ns)):
                raise Refusal("tree-file-identity-changed")
            rows.append({"path": path.relative_to(root).as_posix(), "kind": "file", "sha256": state.hexdigest(), "bytes": size})
        else:
            raise Refusal("tree-unsupported-type")
    return sha(json.dumps(sorted(rows, key=lambda r: r["path"]), sort_keys=True, separators=(",", ":")).encode())


class Managed:
    """Retained owned Popen leader with bounded pipes and original deadlines."""
    def __init__(self, argv, env, cwd, *, popen=subprocess.Popen, clock=time.monotonic, protocol=False):
        self.clock, self.events = clock, queue.Queue(maxsize=32)
        self.protocol = protocol
        self.failed = threading.Event()
        self.buffers = [bytearray(), bytearray()]
        self.child = popen(argv, cwd=cwd, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
        self.threads = []
        self.cleanup_requested = False
        try:
            for index, stream in enumerate((self.child.stdout, self.child.stderr)):
                thread = threading.Thread(target=self.drain, args=(stream, index), daemon=True)
                self.threads.append(thread)
                thread.start()
        except BaseException:
            self.failed.set()
            # This constructor's child is retained here before the caller can
            # register it. Thread creation/start failures still attempt cleanup.
            try:
                self.cleanup()
            except Exception:
                pass  # Original failure stays nonzero; host disposal remains mandatory.
            raise

    def drain(self, stream, index):
        try:
            while raw := (stream.readline(4097) if self.protocol else stream.read(65536)):
                if (self.protocol and len(raw) > 4096) or len(self.buffers[index]) + len(raw) > (4 * 1024 * 1024 if index == 0 else 1024 * 1024):
                    self.failed.set()
                    continue
                self.buffers[index].extend(raw)
                if index == 0 and self.protocol:
                    self.events.put_nowait(raw)
        except Exception:
            self.failed.set()

    def live(self):
        if self.failed.is_set() or self.child.poll() is not None:
            raise Refusal("owned-leader-or-pipe-unavailable")

    def send(self, value):
        self.live()
        raw = (json.dumps(value, separators=(",", ":")) + "\n").encode()
        if len(raw) > 4096:
            raise Refusal("control-bound")
        # At most four <=4KiB control records; owned counterpart continuously reads.
        self.child.stdin.write(raw)
        self.child.stdin.flush()

    def next(self, deadline):
        if self.failed.is_set() or self.clock() >= deadline:
            raise Refusal("owned-event-deadline-or-bound")
        while self.clock() < deadline:
            try:
                raw = self.events.get(timeout=min(0.1, deadline - self.clock()))
                if self.clock() >= deadline or self.failed.is_set():
                    raise Refusal("owned-event-late-or-unbounded")
                return json.loads(raw)
            except queue.Empty:
                if self.child.poll() is not None or self.failed.is_set():
                    raise Refusal("owned-event-missing-before-exit") from None
        raise Refusal("owned-event-deadline")

    def zero(self, deadline):
        while self.clock() < deadline:
            try:
                code = self.child.wait(timeout=min(0.1, deadline - self.clock()))
                break
            except subprocess.TimeoutExpired:
                continue
        else:
            raise Refusal("owned-zero-exit-timeout")
        if self.clock() >= deadline or type(code) is not int or code != 0 or self.failed.is_set():
            raise Refusal("late-nonzero-or-unbounded-completion")
        for thread in self.threads:
            thread.join(max(0, min(1, deadline - self.clock())))
        if self.clock() >= deadline or any(t.is_alive() for t in self.threads) or self.failed.is_set():
            raise Refusal("owned-pipe-lifetime-unproved")
        if self.child.wait(timeout=0) != 0:
            raise Refusal("owned-reap-unproved")
        return {"zero_exit": True, "leader_reaped": True, "process_descendants": "not-proven"}

    def cleanup(self):
        self.cleanup_requested = True
        errors = []
        try:
            if self.child.poll() is None:
                self.child.terminate()  # Only retained leader; no numeric PID/group signal.
        except Exception as exc:
            errors.append(type(exc).__name__)
        try:
            self.child.wait(timeout=5)
        except Exception as exc:
            errors.append(type(exc).__name__)
            try:
                self.child.kill()
                self.child.wait(timeout=5)
            except Exception as retry_exc:
                errors.append(type(retry_exc).__name__)
        for thread in self.threads:
            try:
                if thread.ident is not None:
                    thread.join(1)
            except Exception as exc:
                errors.append(type(exc).__name__)
        if self.child.returncode is None or any(t.is_alive() for t in self.threads):
            raise Refusal("owned-cleanup-unproved")
        # A timeout followed by proven kill/reap is a recorded cleanup action,
        # while other errors remain a refusal even if a later wait returned.
        if any(error != "TimeoutExpired" for error in errors):
            raise Refusal("owned-cleanup-error")
        return {"leader_reaped": True, "cleanup_requested": True, "process_descendants": "host-disposal-required"}


def cleanup_all(leaders):
    """Every retained leader is attempted, including exited leaders with pipes."""
    records, seen = [], set()
    for leader in reversed(leaders):
        if id(leader) in seen:
            continue
        seen.add(id(leader))
        try:
            records.append({"complete": True, **leader.cleanup()})
        except Exception:
            records.append({"complete": False, "reason": "owned-cleanup-unproved", "process_descendants": "host-disposal-required"})
    return records


def owned_listener(leader, port):
    """Read-only Linux leader FD/inode proof; port availability alone is insufficient."""
    leader.live()
    pid = leader.child.pid
    if type(pid) is not int or pid <= 0 or type(port) is not int or not 1024 <= port <= 65535:
        raise Refusal("owned-listener-identity-required")
    sockets = set()
    with os.scandir(Path("/proc") / str(pid) / "fd") as descriptors:
        for count, descriptor in enumerate(descriptors, 1):
            if count > 4096:
                raise Refusal("owned-descriptor-bound")
            target = os.readlink(descriptor.path)
            match = re.fullmatch(r"socket:\[([1-9][0-9]{0,19})\]", target)
            if match:
                sockets.add(match[1])
    with (Path("/proc") / str(pid) / "net/tcp").open("rb") as stream:
        raw = stream.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise Refusal("owned-socket-table-bound")
    matches = []
    for line in raw.decode("ascii").splitlines()[1:]:
        fields = line.split()
        if len(fields) < 10:
            raise Refusal("owned-socket-table-layout")
        if fields[1] == f"0100007F:{port:04X}" and fields[3] == "0A":
            matches.append(fields[9])
    leader.live()
    if not matches:
        raise Refusal("owned-loopback-listener-missing")
    if len(matches) != 1 or matches[0] not in sockets:
        raise Refusal("owned-loopback-listener-unproved")
    return True


class AdbSocket:
    """Direct loopback smart socket; never an adb CLI auto-start fallback."""
    def __init__(self, server, clock=time.monotonic, listener=owned_listener):
        self.server, self.clock, self.listener = server, clock, listener

    def command(self, service, *, transport=False, timeout=30, limit=65536, framed=False):
        self.server.live()
        self.listener(self.server, ADB_PORT)  # Refuses foreign/descendant-only listeners; never auto-starts.
        deadline = self.clock() + timeout
        with socket.create_connection(("127.0.0.1", ADB_PORT), timeout=timeout) as connection:
            def exact(size):
                result = bytearray()
                while len(result) < size:
                    remaining = deadline - self.clock()
                    if remaining <= 0:
                        raise Refusal("adb-original-command-deadline")
                    connection.settimeout(remaining)
                    chunk = connection.recv(size - len(result))
                    if not chunk:
                        raise Refusal("adb-truncated-service")
                    result.extend(chunk)
                return bytes(result)

            def request(value):
                raw = value.encode("ascii")
                if not 0 < len(raw) <= 1024 or any(c < 32 for c in raw):
                    raise Refusal("adb-fixed-service-bound")
                connection.sendall(f"{len(raw):04x}".encode() + raw)
                if exact(4) != b"OKAY":
                    raise Refusal("adb-service-refused")

            if transport:
                request("host:transport:" + SERIAL)
            request(service)
            if framed:
                header = exact(4)
                if re.fullmatch(b"[0-9A-Fa-f]{4}", header) is None or int(header, 16) > limit:
                    raise Refusal("adb-response-bound")
                result = exact(int(header, 16))
                remaining = deadline - self.clock()
                if remaining <= 0:
                    raise Refusal("adb-original-command-deadline")
                connection.settimeout(remaining)
                if connection.recv(1):
                    raise Refusal("adb-framed-unaccounted-tail")
            else:
                result = bytearray()
                while True:
                    remaining = deadline - self.clock()
                    if remaining <= 0:
                        raise Refusal("adb-original-command-deadline")
                    connection.settimeout(remaining)
                    chunk = connection.recv(min(65536, limit + 1 - len(result)))
                    if not chunk:
                        break
                    result.extend(chunk)
                    if len(result) > limit:
                        raise Refusal("adb-output-bound")
                result = bytes(result)
        self.server.live()
        if self.clock() >= deadline:
            raise Refusal("adb-late-completed-command")
        return result

    def shell(self, fixed):
        return shell_v2(self.command("shell,v2,raw:" + fixed, transport=True))

    def forward(self, service, expected_port, *, transport=False):
        raw = self.command(service, transport=transport, limit=64)
        if not raw.startswith(b"OKAY"):
            raise Refusal("adb-forward-status-required")
        extra = raw[4:]
        if extra:
            if (len(extra) < 4 or re.fullmatch(b"[0-9a-fA-F]{4}", extra[:4]) is None
                    or int(extra[:4], 16) != len(extra) - 4 or extra[4:] != str(expected_port).encode("ascii")):
                raise Refusal("adb-forward-exact-port-layout")
        return {"status": "OKAY", "requested_port": expected_port, "returned_port": bool(extra)}


def shell_v2(raw):
    """Only bounded stdout, empty stderr and one final exact zero exit packet."""
    if not isinstance(raw, bytes) or len(raw) > 65536:
        raise Refusal("adb-shell-v2-total-bound")
    cursor, output, exit_seen, packets = 0, bytearray(), False, 0
    while cursor < len(raw):
        packets += 1
        if packets > 1024 or len(raw) - cursor < 5 or exit_seen:
            raise Refusal("adb-shell-v2-packet-layout")
        kind, length = raw[cursor], struct.unpack_from("<I", raw, cursor + 1)[0]
        cursor += 5
        if length > 65536 or length > len(raw) - cursor:
            raise Refusal("adb-shell-v2-payload-bound")
        payload = raw[cursor:cursor + length]
        cursor += length
        if kind == 1:
            output.extend(payload)
        elif kind == 2 and not payload:
            continue
        elif kind == 3 and payload == b"\0":
            exit_seen = True
        else:
            raise Refusal("adb-shell-v2-nonzero-stderr-or-type")
    if not exit_seen:
        raise Refusal("adb-shell-v2-zero-exit-unproved")
    return bytes(output)


def package_inventory(adb, package):
    if package != "com.android.chrome":
        raise Refusal("unowned-package-probe")
    dump = adb.shell("dumpsys package " + package).decode("ascii")
    names = re.findall(r"\bversionName=([0-9]+(?:\.[0-9]+){0,3})\b", dump)
    codes = re.findall(r"\bversionCode=([0-9]{1,12})\b", dump)
    if len(names) != 1 or len(codes) != 1:
        raise Refusal("actual-package-version-unobserved")
    lines = adb.shell("pm path " + package).decode("ascii").splitlines()
    if not 1 <= len(lines) <= 16 or len(set(lines)) != len(lines):
        raise Refusal("actual-apk-path-inventory-unobserved")
    rows = []
    for line in lines:
        if not line.startswith("package:"):
            raise Refusal("apk-path-layout")
        path = line[8:]
        if re.fullmatch(r"/(?:system|product|system_ext|data)/[A-Za-z0-9_./+=-]{1,240}\.apk", path) is None or ".." in path.split("/"):
            raise Refusal("apk-path-bound")
        fields = adb.shell("sha256sum " + path).decode("ascii").split()
        if len(fields) != 2 or fields[1] != path:
            raise Refusal("actual-apk-digest-layout")
        size = adb.shell("stat -c %s " + path).decode("ascii").strip()
        if re.fullmatch(r"[1-9][0-9]{0,11}", size) is None:
            raise Refusal("actual-apk-size-layout")
        rows.append({"path": path, "sha256": digest(fields[0]), "bytes": int(size)})
    return {"package": package, "version": names[0], "version_code": codes[0], "apks": rows,
            "publisher_signing_trust": "not-approved-by-this-test"}


def source_guard(root, run_command):
    if run_command(["git", "rev-parse", "HEAD"]).strip().decode("ascii") != SOURCE or run_command(["git", "status", "--porcelain", "--untracked-files=no"]):
        raise Refusal("clean-exact-source-required")
    manifest = json.loads(read_plain(HERE / "source-manifest.json", 65536))
    if (manifest["source_sha"] != BASELINE or run_command(["git", "rev-parse", BASELINE + "^{tree}"]).strip().decode("ascii") != manifest["source_tree"]
            or len(manifest["files"]) != 5 or {row["path"] for row in manifest["files"]} != {"apps/web/" + name for name in ("app.js", "sw.js", "index.html", "styles.css", "manifest.json")}):
        raise Refusal("source-manifest-mismatch")
    checkout = []
    for row in manifest["files"]:
        if (not isinstance(row, dict) or set(row) != {"path", "fixture_file", "sha256", "size_bytes"}
                or row["fixture_file"] not in {"app.js", "sw.js", "index.html", "styles.css", "manifest.json"}
                or row["path"] != "apps/web/" + row["fixture_file"] or type(row["size_bytes"]) is not int
                or not 0 < row["size_bytes"] <= 65536):
            raise Refusal("exact-known-asset-row-required")
        digest(row["sha256"])
        git_bytes = run_command(["git", "show", SOURCE + ":" + row["path"]])
        if len(git_bytes) != row["size_bytes"] or sha(git_bytes) != row["sha256"] or read_plain(HERE / "source" / row["fixture_file"], 65536) != git_bytes:
            raise Refusal("actual-git-fixture-bytes-mismatch")
        checkout.append({"path": row["path"], "git_sha256": row["sha256"], "checkout_sha256": sha(read_plain(root / row["path"], 65536))})
    current_tree = run_command(["git", "rev-parse", SOURCE + "^{tree}"]).strip().decode("ascii")
    if re.fullmatch(r"[0-9a-f]{40}", current_tree) is None:
        raise Refusal("actual-current-tree-unobserved")
    return {"checkout": checkout, "live_manifest": {**manifest, "source_sha": SOURCE, "source_tree": current_tree,
                                                    "asset_baseline_ref": BASELINE, "scope": "Actual current Git assets checked byte-for-byte against frozen demo baseline"}}


def result_guard(result, nonce, inventory_hash, manifest_hash, probe_hash, source_tree, browser_inventory):
    keys = {"schema", "complete", "status", "nonce", "source_sha", "source_tree", "run_id", "run_attempt", "manifest_sha256",
            "probe_sha256", "inventory_sha256", "android_api", "serial", "playwright_version", "browser", "checks",
            "screenshot_sha256", "screenshot_bytes", "elapsed_ms", "limits"}
    expected_limits = ["Demo shell only; no backend profile API or remote-protocol rendering", "No installed PWA/iOS/Termux/native APK/IPA proof",
                       "Owned server unavailable; no physical radio/device isolation proof", "No Android native UI/helper APK instrumentation proof",
                       "CDP attachment has lower fidelity than native Playwright protocol", "Process descendants require disposable-host destruction"]
    if (not isinstance(result, dict) or set(result) != keys or result.get("schema") != "row.android-actual-demo-browser.v1"
            or result.get("complete") is not True or result.get("status") != "passed" or result.get("nonce") != nonce
            or result.get("source_sha") != SOURCE or result.get("run_id") != os.environ.get("GITHUB_RUN_ID")
            or result.get("run_attempt") != os.environ.get("GITHUB_RUN_ATTEMPT")
            or result.get("manifest_sha256") != manifest_hash or result.get("probe_sha256") != probe_hash
            or result.get("inventory_sha256") != inventory_hash or result.get("android_api") != 36 or result.get("serial") != SERIAL
            or result.get("playwright_version") != "1.56.1" or not isinstance(result.get("checks"), list)
            or len(result["checks"]) != len(REQUIRED) or set(result["checks"]) != REQUIRED
            or result.get("source_tree") != source_tree or result.get("browser") != browser_inventory or result.get("limits") != expected_limits
            or type(result.get("screenshot_bytes")) is not int or not 0 < result["screenshot_bytes"] <= 4 * 1024 * 1024
            or re.fullmatch(r"[0-9a-f]{64}", result.get("screenshot_sha256", "")) is None
            or type(result.get("elapsed_ms")) not in {float, int} or not 0 <= result["elapsed_ms"] < 115000):
        raise Refusal("complete-nonce-source-browser-result-required")
    return True


def run(root, pin_path):
    host_guard(root)  # No SDK/ADB/Chrome command is reachable on a local host.
    pins = validate_pins(json.loads(read_plain(pin_path, 131072)))  # Missing pins refuse BEFORE every native command.
    if sha(read_plain(HERE / "package-lock.json", 131072)) != pins["npm_lock_sha256"] or tree_digest(HERE / "node_modules") != pins["npm_tree_sha256"]:
        raise Refusal("actual-pinned-npm-tree-required")
    sdk = Path(os.environ.get("ANDROID_HOME", ""))
    if tree_digest(sdk, maximum_files=30000, maximum_bytes=4 * 1024 * 1024 * 1024) != pins["sdk_tree_sha256"]:
        raise Refusal("actual-qualified-sdk-tree-required")
    for row in pins["tools"].values():
        if sha(read_plain(Path(row["path"]), 128 * 1024 * 1024)) != row["sha256"]:
            raise Refusal("qualified-tool-bytes-mismatch")
    parent = root / ".tmp"
    if parent.is_symlink() or parent.resolve() != parent:
        raise Refusal("owned-private-parent-required")
    private = parent / ("android-browser-owned-" + secrets.token_hex(16))
    private.mkdir(mode=0o700)
    nonce = secrets.token_hex(32)
    env = {"PATH": os.environ.get("PATH", ""), "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "PYTHONDONTWRITEBYTECODE": "1",
           "HOME": str(private), "ANDROID_HOME": str(sdk), "ANDROID_SDK_ROOT": str(sdk), "ANDROID_AVD_HOME": str(private / "avd"),
           "ANDROID_USER_HOME": str(private / "android-home"), "PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD": "1",
           "ADB_SERVER_SOCKET": "tcp:127.0.0.1:5039", "ANDROID_ADB_SERVER_PORT": "5039", "ADB_MDNS_AUTO_CONNECT": "",
           "ADB_LOCAL_TRANSPORT_MAX_PORT": "5557"}
    env.update({k: os.environ[k] for k in ("GITHUB_ACTIONS", "RUNNER_ENVIRONMENT", "RUNNER_OS", "RUNNER_ARCH", "GITHUB_REPOSITORY", "GITHUB_WORKSPACE", "GITHUB_SHA", "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT", "ROW_EXPECTED_HEAD")})
    leaders, server, browser = [], None, None
    started = time.monotonic()

    def short(argv, stdin=None, timeout=30):
        deadline = min(time.monotonic() + timeout, started + 1500)
        leader = Managed(argv, env, root)
        leaders.append(leader)
        if stdin is not None:
            leader.child.stdin.write(stdin)
            leader.child.stdin.flush()
        leader.child.stdin.close()
        leader.zero(deadline)
        if leader.buffers[1]:
            raise Refusal("unexpected-private-command-stderr")
        return bytes(leader.buffers[0])

    try:
        checkout = source_guard(root, short)
        names = {"hosted_controller.py", "android_browser_probe.mjs", "fixture_server.py", "source-manifest.json"}
        relative = HERE.relative_to(root).as_posix()
        hashes = {}
        for name in names:
            raw = read_plain(HERE / name, 262144)
            if short(["git", "show", SOURCE + ":" + relative + "/" + name]) != raw:
                raise Refusal("actual-tracked-controller-byte-mismatch")
            hashes[name] = sha(raw)
        live_path = private / "source-binding.json"
        with live_path.open("x") as stream:
            json.dump(checkout["live_manifest"], stream)
        live_hash = sha(read_plain(live_path, 65536))
        for directory in (private / "avd", private / "android-home"):
            directory.mkdir(mode=0o700)
        avd_name = "row-browser-36-" + nonce[:16]
        short([pins["tools"]["avdmanager"]["path"], "create", "avd", "-n", avd_name, "-k", "system-images;android-36;google_apis;x86_64", "--device", "pixel_6"], stdin=b"no\n", timeout=180)
        for port in (ADB_PORT, 5556, 5557):
            with socket.socket() as check:
                check.bind(("127.0.0.1", port))
        adb_server = Managed([pins["tools"]["adb"]["path"], "-L", "tcp:127.0.0.1:5039", "nodaemon", "server"], env, root)
        leaders.append(adb_server)
        adb_ready_deadline = time.monotonic() + 10
        while time.monotonic() < adb_ready_deadline:
            try:
                owned_listener(adb_server, ADB_PORT)
                if time.monotonic() >= adb_ready_deadline:
                    raise Refusal("late-owned-adb-listener")
                break
            except Refusal as exc:
                if str(exc) != "owned-loopback-listener-missing":
                    raise
            time.sleep(0.1)
        else:
            raise Refusal("original-owned-adb-listener-deadline")
        emulator = Managed([pins["tools"]["emulator"]["path"], "-avd", avd_name, "-port", "5556", "-no-window", "-gpu", "swiftshader_indirect", "-no-snapshot", "-no-snapshot-load", "-no-snapshot-save", "-noaudio", "-no-boot-anim", "-camera-back", "none", "-no-metrics"], env, root)
        leaders.append(emulator)
        adb = AdbSocket(adb_server)
        connect_deadline = time.monotonic() + 180
        while time.monotonic() < connect_deadline:
            emulator.live()
            try:
                devices = adb.command("host:devices", framed=True, timeout=min(30, connect_deadline - time.monotonic())).decode("ascii").splitlines()
                if time.monotonic() >= connect_deadline:
                    raise Refusal("late-device-connect")
                if devices == [SERIAL + "\tdevice"]:
                    break
                if any(line and line.split("\t")[0] != SERIAL for line in devices):
                    raise Refusal("foreign-device-namespace")
            except (ConnectionError, TimeoutError):
                pass
            time.sleep(0.1)
        else:
            raise Refusal("original-device-connect-deadline")
        boot_deadline = time.monotonic() + 180
        while time.monotonic() < boot_deadline:
            emulator.live()
            boot = shell_v2(adb.command("shell,v2,raw:getprop sys.boot_completed", transport=True, timeout=min(30, boot_deadline - time.monotonic()))).strip()
            if time.monotonic() >= boot_deadline:
                raise Refusal("late-emulator-boot")
            if boot == b"1":
                break
            time.sleep(0.1)
        else:
            raise Refusal("original-emulator-boot-deadline")
        if adb.shell("getprop ro.build.version.sdk").strip() != b"36" or adb.shell("getprop ro.product.cpu.abi").strip() != b"x86_64":
            raise Refusal("actual-api-or-abi-mismatch")
        chrome = package_inventory(adb, "com.android.chrome")
        if int(chrome["version"].split(".")[0]) < 87:
            raise Refusal("actual-supported-chrome-required")
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        # Reverse service is direct, fixed and serial-bound; never invoke an adb
        # CLI client which could silently auto-start a replacement server.
        if adb.command("host:list-forward", framed=True) or adb.command("reverse:list-forward", transport=True, framed=True):
            raise Refusal("clean-owned-forward-namespace-required")
        adb.forward(f"reverse:forward:norebind:tcp:{port};tcp:{port}", port, transport=True)
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            cdp_port = reservation.getsockname()[1]
        adb.forward(f"host-serial:{SERIAL}:forward:norebind:tcp:{cdp_port};localabstract:chrome_devtools_remote", cdp_port)
        env.update({"ROW_DISPOSABLE_ANDROID_BROWSER_PROBE": "1", "ROW_ANDROID_SERIAL": SERIAL, "ROW_ANDROID_API": "36",
                    "ROW_BROWSER_NONCE": nonce, "ROW_BROWSER_PRIVATE": str(private), "ROW_BROWSER_FIXTURE_URL": f"http://127.0.0.1:{port}/",
                    "ROW_CHROME_CDP_URL": f"http://127.0.0.1:{cdp_port}/", "ROW_SOURCE_MANIFEST": str(live_path)})
        inventory = {"nonce": nonce, "source_sha": SOURCE, "serial": SERIAL, "android_api": 36,
                     "browser": chrome, "cdp_socket_serial_bound": True,
                     "pin_receipt_sha256": sha(read_plain(pin_path, 131072)), "Android_helper_APKs": "not-used",
                     "native_Chrome_UI_accessibility": "not-claimed"}
        with (private / "device-inventory.json").open("x") as stream:
            json.dump(inventory, stream)
        inventory_hash = sha(read_plain(private / "device-inventory.json", 65536))

        def start_server(generation, deadline):
            value = Managed([sys.executable, str(HERE / "fixture_server.py"), "--port", str(port), "--nonce", nonce, "--generation", str(generation)], env, root, protocol=True)
            leaders.append(value)
            if value.next(deadline) != {"type": "ready", "nonce": nonce, "generation": generation, "port": port, "source_sha": SOURCE}:
                raise Refusal("owned-fixture-readiness-mismatch")
            owned_listener(value, port)
            return value

        server = start_server(1, time.monotonic() + 10)
        adb.shell("am force-stop com.android.chrome")
        adb.shell(f"am start -W -a android.intent.action.VIEW -d http://127.0.0.1:{port}/allow/index.html -p com.android.chrome")
        owned_listener(adb_server, cdp_port)
        browser_deadline = time.monotonic() + BROWSER_SECONDS
        browser = Managed([pins["tools"]["node"]["path"], str(HERE / "android_browser_probe.mjs")], env, root, protocol=True)
        leaders.append(browser)
        controls = ["release-pending", "stop-server", "restart-server"]
        server_receipts = []
        for control in controls:
            if browser.next(browser_deadline) != {"type": "control", "control": control, "nonce": nonce}:
                raise Refusal("browser-control-sequence-or-nonce")
            emulator.live()
            adb_server.live()
            if control == "release-pending":
                server.send({"control": control, "nonce": nonce})
                if server.next(browser_deadline) != {"type": "ack", "nonce": nonce, "control": control}:
                    raise Refusal("owned-pending-release-ack")
            elif control == "stop-server":
                server.send({"control": control, "nonce": nonce})
                server_receipts.append(server.zero(browser_deadline))
                with socket.socket() as check:
                    check.settimeout(min(1, browser_deadline - time.monotonic()))
                    if check.connect_ex(("127.0.0.1", port)) == 0:
                        raise Refusal("fixture-listener-remains-after-owned-exit")
                server = None
            else:
                server = start_server(2, browser_deadline)
            browser.send({"type": "ack", "control": control, "nonce": nonce})
        completion = browser.zero(browser_deadline)
        result = json.loads(read_plain(private / "browser-result.json", 65536))
        source_tree = checkout["live_manifest"]["source_tree"]
        result_guard(result, nonce, inventory_hash, live_hash, hashes["android_browser_probe.mjs"], source_tree, chrome)
        screenshot = read_plain(private / "browser-synthetic.png", 4 * 1024 * 1024)
        if sha(screenshot) != result["screenshot_sha256"] or len(screenshot) != result["screenshot_bytes"]:
            raise Refusal("actual-synthetic-screenshot-binding")
        server.send({"control": "stop-server", "nonce": nonce})
        server_receipts.append(server.zero(min(time.monotonic() + 10, started + 1500)))
        server = None
        if source_guard(root, short) != checkout or sha(read_plain(live_path, 65536)) != live_hash:
            raise Refusal("current-source-binding-changed")
        if package_inventory(adb, "com.android.chrome") != chrome or tree_digest(HERE / "node_modules") != pins["npm_tree_sha256"]:
            raise Refusal("actual-browser-or-library-bytes-changed")
        if {name: sha(read_plain(HERE / name, 262144)) for name in hashes} != hashes or sha(read_plain(pin_path, 131072)) != inventory["pin_receipt_sha256"]:
            raise Refusal("source-or-pins-changed-after-browser")
        cleanup = [emulator.cleanup(), adb_server.cleanup()]
        report = {"schema": "row.android-demo-hosted-controller.v1", "status": "passed", "source_sha": SOURCE, "nonce": nonce,
                  "run_id": os.environ["GITHUB_RUN_ID"], "run_attempt": os.environ["GITHUB_RUN_ATTEMPT"], "checkout_asset_bytes": checkout["checkout"],
                  "actual_source_tree": source_tree, "live_source_manifest_sha256": live_hash,
                  "source_sha256": hashes, "stack_pins_sha256": inventory["pin_receipt_sha256"], "browser_result": result,
                  "completion": completion, "server_lifecycles": server_receipts, "owned_host_leaders": cleanup,
                  "host_disposal_required": True, "installed_pwa": False, "ios": False, "termux": False,
                  "full_backend_protocol_rendering": False, "native_apk_ipa_release": False, "readiness_credit": 0}
        target = root / "build/mobile-browser/android-api36-actual-demo-draft.json"
        if target.parent.resolve() != target.parent or target.parent.is_symlink():
            raise Refusal("public-output-parent-containment")
        raw = (json.dumps(report, indent=2) + "\n").encode()
        if len(raw) > 131072:
            raise Refusal("public-result-bound")
        with target.open("xb") as stream:
            stream.write(raw)
        return {"status": "passed", "public_result_sha256": sha(raw), "readiness_credit": 0}
    finally:
        # Failure never triggers further device commands, package cleanup, port
        # reuse or result acceptance. Only retained owned host leader cleanup.
        original_failure = sys.exc_info()[1]
        receipts = cleanup_all(leaders)
        if any(not receipt["complete"] for receipt in receipts) and original_failure is None:
            raise Refusal("owned-final-cleanup-unproved")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("action", choices=("plan", "run"), nargs="?", default="plan")
    ap.add_argument("--pins", type=Path, default=HERE / "stack-pins.unqualified.json")
    args = ap.parse_args(argv)
    if args.action == "plan":
        print(json.dumps({"status": "unadopted-unexecuted", "source_sha": SOURCE, "android_api": 36,
                          "original_browser_deadline_seconds": 120, "stack_qualification": "missing-refuses-before-native",
                          "future_source_binding": "refresh-required-after-root-changes", "readiness_credit": 0}))
        return 0
    try:
        print(json.dumps(run(Path.cwd().resolve(), args.pins)))
        return 0
    except Exception:
        print("android-hosted-draft-refused", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
