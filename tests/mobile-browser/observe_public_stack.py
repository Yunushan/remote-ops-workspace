"""Hosted-only official public package observation; no ADB/emulator/app commands.

Two reviewable stages: observe exact official bytes, then finalize after a real
byte-bound contract review and SDK parser/tool observations. Never called locally.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
import zlib
from pathlib import Path
from urllib.parse import urlsplit

import hosted_controller as H

HERE = Path(__file__).resolve().parent
ARCHIVE_SHA = "10f8c307a89275bacda2eb9fd5fed10b1a8879e5bbb833e151052fd4bcc94250"
META_URL = "https://registry.npmjs.org/playwright-core/1.56.1"
TAR_URL = "https://registry.npmjs.org/playwright-core/-/playwright-core-1.56.1.tgz"
REDIRECT_HOSTS = {"registry.npmjs.org"}


def public_url(url):
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.hostname not in REDIRECT_HOSTS or parsed.port not in (None, 443)
            or parsed.username or parsed.password or parsed.query or parsed.fragment or not parsed.path.startswith("/")):
        raise H.Refusal("official-public-source-url-required")
    if parsed.hostname == "registry.npmjs.org" and parsed.path not in {"/playwright-core/1.56.1", "/playwright-core/-/playwright-core-1.56.1.tgz"}:
        raise H.Refusal("public-source-path-unexpected")
    return url


def fetch(url, maximum):
    public_url(url)

    class Redirects(urllib.request.HTTPRedirectHandler):
        def __init__(self):
            self.count = 0

        def redirect_request(self, request, fp, code, message, headers, newurl):
            self.count += 1
            if self.count > 3:
                raise H.Refusal("official-source-redirect-bound")
            public_url(newurl)
            return super().redirect_request(request, fp, code, message, headers, newurl)

    started, body = time.monotonic(), bytearray()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), Redirects())
    with opener.open(urllib.request.Request(url, headers={"Accept": "application/json, application/octet-stream", "User-Agent": "ROW-disposable-public-qualification"}), timeout=20) as response:
        if response.status != 200 or response.headers.get("Content-Encoding", "identity") != "identity":
            raise H.Refusal("public-source-response-layout")
        length = response.headers.get("Content-Length")
        if length is not None and (re.fullmatch(r"[1-9][0-9]{0,9}", length) is None or int(length) > maximum):
            raise H.Refusal("public-source-content-bound")
        while chunk := response.read(min(65536, maximum + 1 - len(body))):
            if time.monotonic() - started >= 60:
                raise H.Refusal("original-public-source-request-budget")
            body.extend(chunk)
            if len(body) > maximum:
                raise H.Refusal("public-source-byte-bound")
        if length is not None and len(body) != int(length):
            raise H.Refusal("public-source-length-mismatch")
        if not body or time.monotonic() - started >= 60:
            raise H.Refusal("public-source-empty-or-late-completion")
    return bytes(body)


def archive_reader():
    raw = H.read_plain(HERE / "archive_readers_frozen.py", 131072)
    if H.sha(raw) != ARCHIVE_SHA:
        raise H.Refusal("frozen-archive-reader-mismatch")
    spec = importlib.util.spec_from_file_location("row_android_archive_reader", HERE / "archive_readers_frozen.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    exec(compile(raw, str(spec.origin), "exec"), module.__dict__)
    return module


def fetch_qualification(url, maximum, remaining, clock=time.monotonic):
    """Qualification-only shared deadline; standalone fetch remains unchanged."""
    public_url(url)
    started = clock()
    deadline = started + min(60, remaining())
    if deadline <= started:
        raise H.Refusal("qualification-public-fetch-original-budget")

    class Redirects(urllib.request.HTTPRedirectHandler):
        def __init__(self):
            self.count = 0

        def redirect_request(self, request, fp, code, message, headers, newurl):
            self.count += 1
            if self.count > 3 or clock() >= deadline or remaining() <= 0:
                raise H.Refusal("qualification-public-redirect-budget")
            public_url(newurl)
            return super().redirect_request(request, fp, code, message, headers, newurl)

    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), Redirects())
    body = bytearray()
    request = urllib.request.Request(url, headers={"Accept": "application/json, application/octet-stream", "User-Agent": "ROW-disposable-public-qualification"})
    with opener.open(request, timeout=min(20, deadline - started)) as response:
        if response.status != 200 or response.headers.get("Content-Encoding", "identity") != "identity":
            raise H.Refusal("qualification-public-response-layout")
        length = response.headers.get("Content-Length")
        if length is not None and (re.fullmatch(r"[1-9][0-9]{0,9}", length) is None or int(length) > maximum):
            raise H.Refusal("qualification-public-content-bound")
        while True:
            if clock() >= deadline or remaining() <= 0:
                raise H.Refusal("qualification-public-fetch-original-budget")
            chunk = response.read(min(65536, maximum + 1 - len(body)))
            if clock() >= deadline or remaining() <= 0:
                raise H.Refusal("qualification-public-fetch-original-budget")
            if not chunk:
                break
            body.extend(chunk)
            if len(body) > maximum:
                raise H.Refusal("qualification-public-byte-bound")
        if not body or (length is not None and len(body) != int(length)):
            raise H.Refusal("qualification-public-length-layout")
    if clock() >= deadline or remaining() <= 0:
        raise H.Refusal("qualification-public-fetch-original-budget")
    return bytes(body)


def unpack_public(raw, kind, reader):
    limits = reader.Limits(input_bytes=32 * 1024 * 1024, expanded_bytes=64 * 1024 * 1024,
                           member_bytes=16 * 1024 * 1024, members=12000, json_bytes=4 * 1024 * 1024)
    observations = reader.Observations(limits)
    if kind == "npm":
        decoder = zlib.decompressobj(31)
        expanded = decoder.decompress(raw, limits.expanded_bytes + 1)
        if len(expanded) > limits.expanded_bytes or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
            raise H.Refusal("public-npm-gzip-bound-or-tail")
        values = list(reader.tar_members(expanded, observations))
        if any(not name.startswith("package/") for name, _ in values):
            raise H.Refusal("public-npm-package-root")
        return {name[8:]: value for name, value in values}
    raise H.Refusal("unknown-public-archive")


def save(path, raw):
    if path.exists() or path.is_symlink() or path.parent.resolve() != path.parent:
        raise H.Refusal("fresh-private-output-required")
    with path.open("xb") as stream:
        stream.write(raw)


def git_source(root):
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, timeout=10, capture_output=True, check=True)
    status = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=root, timeout=10, capture_output=True, check=True)
    if result.stderr or status.stderr or result.stdout.strip().decode("ascii") != H.SOURCE or status.stdout:
        raise H.Refusal("clean-exact-source-before-public-fetch")
    relative = HERE.relative_to(root).as_posix()
    for name in ("hosted_controller.py", "observe_public_stack.py", "archive_readers_frozen.py"):
        committed = subprocess.run(["git", "show", H.SOURCE + ":" + relative + "/" + name], cwd=root, timeout=10, capture_output=True, check=True)
        if committed.stderr or len(committed.stdout) > 262144 or committed.stdout != H.read_plain(HERE / name, 262144):
            raise H.Refusal("actual-tracked-qualification-source-required")


def observe(root):
    H.host_guard(root)
    return _observe_bound_source(root)


def _observe_bound_source(root, qualification=None, *, source_check=None, remaining=None):
    if qualification is None:
        H.host_guard(root)  # Standalone observation behavior remains dispatch-only.
    else:
        import qualify_android_stack as Q
        event = Q.event_guard(root)  # Local/fork/malformed sources refuse before NPM fetch.
        if (not isinstance(qualification, dict) or set(qualification) != {"source_sha", "source_tree", "helpers", "workflow_sha256", "run_id", "run_attempt", "execution", "executed_workflow"}
                or qualification["execution"] != event or qualification["source_sha"] != H.SOURCE
                or re.fullmatch(r"[0-9a-f]{40}", qualification["source_tree"]) is None
                or qualification["run_id"] != event["run_id"] or qualification["run_attempt"] != event["run_attempt"]
                or not isinstance(qualification["executed_workflow"], dict)
                or set(qualification["executed_workflow"]) != {"workflow_sha", "size_bytes", "sha256", "source_contract_matches", "redirects"}
                or qualification["executed_workflow"]["workflow_sha"] != event["workflow_sha"]
                or qualification["executed_workflow"]["source_contract_matches"] is not True
                or qualification["executed_workflow"]["redirects"] != 0
                or type(qualification["executed_workflow"]["size_bytes"]) is not int
                or not 0 < qualification["executed_workflow"]["size_bytes"] <= 131072
                or qualification["executed_workflow"]["sha256"] != qualification["workflow_sha256"]):
            raise H.Refusal("exact-current-qualification-before-NPM-required")
        H.digest(qualification["workflow_sha256"])
        if not isinstance(qualification["helpers"], dict) or set(qualification["helpers"]) != {"qualify_android_stack.py", "hosted_controller.py", "observe_public_stack.py", "archive_readers_frozen.py"}:
            raise H.Refusal("exact-qualification-helper-inventory-required")
        for value in qualification["helpers"].values():
            H.digest(value)
        for name, value in qualification["helpers"].items():
            if H.sha(H.read_plain(HERE / name, 262144)) != value:
                raise H.Refusal("current-qualified-helper-bytes-changed")
        if not callable(source_check) or not callable(remaining) or remaining() <= 0 or source_check() != qualification:
            raise H.Refusal("current-owned-qualification-source-check-required")
    if qualification is None:
        git_source(root)
    acquire = fetch if qualification is None else lambda url, maximum: fetch_qualification(url, maximum, remaining)
    reader = archive_reader()
    metadata_raw = acquire(META_URL, 131072)
    metadata = json.loads(metadata_raw)
    if metadata.get("name") != "playwright-core" or metadata.get("version") != "1.56.1" or metadata.get("dependencies") or metadata.get("optionalDependencies"):
        raise H.Refusal("exact-single-npm-runtime-package-required")
    dist = metadata.get("dist", {})
    integrity = dist.get("integrity", "")
    if dist.get("tarball") != TAR_URL or re.fullmatch(r"sha512-[A-Za-z0-9+/]{86}==", integrity) is None:
        raise H.Refusal("exact-public-npm-integrity-required")
    tar = acquire(TAR_URL, 16 * 1024 * 1024)
    if "sha512-" + base64.b64encode(hashlib.sha512(tar).digest()).decode() != integrity:
        raise H.Refusal("published-npm-integrity-mismatch")
    npm = unpack_public(tar, "npm", reader)
    package = json.loads(npm["package.json"])
    if package.get("name") != "playwright-core" or package.get("version") != "1.56.1":
        raise H.Refusal("published-npm-package-identity")
    for name in ("lib/client/browserType.js", "lib/server/chromium/chromium.js"):
        if name not in npm:
            raise H.Refusal("exact-pinned-implementation-unobserved")
    # Preserve complete public inventories for review; never execute these bytes.
    report = {"schema": "row.android-public-stack-observation.v1", "status": "observed-unqualified",
              "source_sha": H.SOURCE, "run_id": os.environ["GITHUB_RUN_ID"], "run_attempt": os.environ["GITHUB_RUN_ATTEMPT"],
              "metadata_sha256": H.sha(metadata_raw), "npm_url": TAR_URL, "npm_integrity": integrity,
              "npm_tar_sha256": H.sha(tar), "npm_tar_bytes": len(tar),
              "npm_files": [{"path": name, "sha256": H.sha(raw), "bytes": len(raw)} for name, raw in sorted(npm.items())],
              "Android_helper_APKs": "not-required-or-used-by-this-CDP-route",
              "exact_CDP_contract_review": "required-before-native-device-or-browser-commands",
              "sdk_toolchain": "not-qualified-by-this-stage", "native_commands": False, "readiness_credit": 0, "approval": False}
    if qualification is not None:
        report["qualification_execution"] = qualification
    parent = root / ".tmp"
    if qualification is not None and remaining() <= 0:
        raise H.Refusal("qualification-public-fetch-original-budget")
    if parent.resolve() != parent or parent.is_symlink():
        raise H.Refusal("private-parent-containment")
    private = parent / "android-public-stack-observation"
    private.mkdir(mode=0o700)  # Existing output never replaced; single fresh capture.
    for name, raw in {"metadata.json": metadata_raw, "npm.tgz": tar}.items():
        save(private / name, raw)
    selected = {"package.json", "lib/client/browserType.js", "lib/server/chromium/chromium.js"}
    for name in selected:
        save(private / (name.replace("/", "__")), npm[name])
    lock = {"name": "row-disposable-android-browser-tool", "version": "0.0.0", "lockfileVersion": 3, "requires": True,
            "packages": {"": {"name": "row-disposable-android-browser-tool", "version": "0.0.0", "dependencies": {"playwright-core": "1.56.1"}},
                         "node_modules/playwright-core": {"version": "1.56.1", "resolved": TAR_URL, "integrity": integrity}}}
    save(private / "package-lock.json", (json.dumps(lock, indent=2) + "\n").encode())
    report["npm_lock_sha256"] = H.sha(H.read_plain(private / "package-lock.json", 131072))
    raw = (json.dumps(report, indent=2) + "\n").encode()
    if len(raw) > 2 * 1024 * 1024:
        raise H.Refusal("public-source-observation-bound")
    if qualification is None:
        git_source(root)
    elif remaining() <= 0 or source_check() != qualification:
        raise H.Refusal("qualified-current-source-readback-required")
    destination = root / "build/mobile-browser/android-public-stack-observation.json"
    save(destination, raw)
    return {"status": report["status"], "public_sha256": H.sha(raw), "readiness_credit": 0}


def stage(root, review_path):
    """Concrete post-review staging/pin observation; no package code executes."""
    H.host_guard(root)
    git_source(root)
    private = root / ".tmp/android-public-stack-observation"
    report_raw = H.read_plain(root / "build/mobile-browser/android-public-stack-observation.json", 2 * 1024 * 1024)
    report = json.loads(report_raw)
    if (not isinstance(report, dict) or report.get("schema") != "row.android-public-stack-observation.v1"
            or report.get("status") != "observed-unqualified" or report.get("source_sha") != H.SOURCE
            or report.get("npm_url") != TAR_URL or report.get("native_commands") is not False
            or report.get("readiness_credit") != 0 or report.get("approval") is not False):
        raise H.Refusal("actual-current-public-observation-required")
    review_raw = H.read_plain(review_path, 65536)
    review = json.loads(review_raw)
    if (not isinstance(review, dict) or set(review) != {"schema", "status", "source_sha", "observation_sha256", "npm_tar_sha256", "npm_lock_sha256", "CDP_contract"}
            or review["schema"] != "row.android-CDP-source-review.v1" or review["status"] != "accepted-for-disposable-tool-staging"
            or review["source_sha"] != H.SOURCE or review["observation_sha256"] != H.sha(report_raw)
            or review["npm_tar_sha256"] != report["npm_tar_sha256"] or review["npm_lock_sha256"] != report["npm_lock_sha256"]
            or review["CDP_contract"] != {"connect_over_CDP_only": True, "no_Android_driver_APKs": True, "no_host_browser_launch": True}):
        raise H.Refusal("genuine-byte-bound-source-review-required")
    metadata_raw = H.read_plain(private / "metadata.json", 131072)
    tar = H.read_plain(private / "npm.tgz", 16 * 1024 * 1024)
    metadata = json.loads(metadata_raw)
    if H.sha(metadata_raw) != report["metadata_sha256"] or H.sha(tar) != report["npm_tar_sha256"]:
        raise H.Refusal("original-public-source-byte-mismatch")
    integrity = "sha512-" + base64.b64encode(hashlib.sha512(tar).digest()).decode()
    if integrity != metadata["dist"]["integrity"] or integrity != report["npm_integrity"] or metadata["dist"]["tarball"] != TAR_URL:
        raise H.Refusal("original-published-integrity-mismatch")
    npm = unpack_public(tar, "npm", archive_reader())
    if [{"path": name, "sha256": H.sha(raw), "bytes": len(raw)} for name, raw in sorted(npm.items())] != report["npm_files"]:
        raise H.Refusal("complete-public-package-inventory-mismatch")
    node_modules = HERE / "node_modules"
    node_modules.mkdir(mode=0o700)  # Never replace/reuse unknown dependencies.
    core = node_modules / "playwright-core"
    core.mkdir(mode=0o700)
    for name, raw in npm.items():
        path = core.joinpath(*name.split("/"))
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        save(path, raw)
    lock = H.read_plain(private / "package-lock.json", 131072)
    if H.sha(lock) != report["npm_lock_sha256"]:
        raise H.Refusal("observed-public-lock-mismatch")
    save(HERE / "package-lock.json", lock)
    sdk = Path(os.environ.get("ANDROID_HOME", "")).resolve()
    if not sdk.is_absolute() or not sdk.is_dir() or sdk == Path("/"):
        raise H.Refusal("bounded-isolated-SDK-directory-required")
    node = shutil.which("node")
    if node is None:
        raise H.Refusal("hosted-node-unavailable")
    paths = {"adb": sdk / "platform-tools/adb", "emulator": sdk / "emulator/emulator",
             "avdmanager": sdk / "cmdline-tools/latest/bin/avdmanager", "node": Path(node).resolve()}
    tools = {name: {"path": str(path), "sha256": H.sha(H.read_plain(path, 128 * 1024 * 1024))} for name, path in paths.items()}
    pins = {"schema": "row.android-cdp-public-stack.v1", "source_sha": H.SOURCE, "playwright_version": "1.56.1",
            "npm_lock_sha256": H.sha(lock), "npm_tree_sha256": H.tree_digest(node_modules),
            "sdk_tree_sha256": H.tree_digest(sdk, maximum_files=30000, maximum_bytes=4 * 1024 * 1024 * 1024),
            "tools": tools, "qualified_contract_receipt_sha256": H.sha(review_raw)}
    H.validate_pins(pins)
    git_source(root)
    save(HERE / "stack-pins.observed.json", (json.dumps(pins, indent=2) + "\n").encode())
    return {"status": "observed-staged-tool-inputs", "source_sha": H.SOURCE,
            "pins_sha256": H.sha(H.read_plain(HERE / "stack-pins.observed.json", 131072)),
            "npm_ci_executed": False, "package_code_executed": False, "SDK_or_Android_commands_executed": False,
            "legal_or_signing_approval": False, "readiness_credit": 0}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("action", choices=("plan", "guard", "observe", "stage"), default="plan", nargs="?")
    ap.add_argument("--source-review", type=Path)
    args = ap.parse_args(argv)
    if args.action == "plan":
        print(json.dumps({"status": "unadopted-unexecuted", "official_metadata": META_URL, "official_tarball": TAR_URL,
                          "Android_helper_APKs": "not-required-by-CDP-route", "next": "hosted-source-observe -> exact-byte independent review -> isolated SDK provision -> read-only pinned staging -> guarded Chrome CDP",
                          "no_local_download": True, "readiness_credit": 0}))
        return 0
    try:
        root = Path.cwd().resolve()
        if args.action == "guard":
            H.host_guard(root)
            git_source(root)
            value = {"status": "actual-host-source-guard-passed", "source_sha": H.SOURCE}
        elif args.action == "stage":
            if args.source_review is None:
                raise H.Refusal("actual-source-review-required")
            value = stage(root, args.source_review)
        else:
            value = observe(root)
        print(json.dumps(value))
        return 0
    except Exception:
        print("android-public-source-observation-refused", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
