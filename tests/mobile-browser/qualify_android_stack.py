"""Hosted toolchain qualification. No product/Chrome/Playwright launch."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import secrets
import socket
import stat
import sys
import time
import urllib.request
from pathlib import Path

import hosted_controller as H
import observe_public_stack as O

HERE = Path(__file__).resolve().parent
WORKFLOW = ".github/workflows/android-toolchain-qualification.yml"
REPORT = "build/mobile-browser/android-toolchain-qualification.json"
BOOTSTRAP = ".tmp/android-sdk-bootstrap-observation.json"
FIXED_SOURCE_SDK = Path("/usr/local/lib/android/sdk")


def event_guard(root):
    # Qualification accepts head checkout distinct from the PR merge event.
    # Actual browser H.host_guard stays dispatch-only and is not weakened.
    expected = {"GITHUB_ACTIONS": "true", "RUNNER_ENVIRONMENT": "github-hosted", "RUNNER_OS": "Linux", "RUNNER_ARCH": "X64",
                "GITHUB_REPOSITORY": "Yunushan/remote-ops-workspace", "ROW_EXPECTED_HEAD": H.SOURCE,
                "GITHUB_SERVER_URL": "https://github.com", "GITHUB_API_URL": "https://api.github.com"}
    ref = os.environ.get("GITHUB_REF", "")
    if (any(os.environ.get(key) != value for key, value in expected.items()) or platform.system() != "Linux" or platform.machine() != "x86_64"
            or root.is_symlink() or root.resolve() != root or Path(os.environ.get("GITHUB_WORKSPACE", "")).resolve() != root
            or any(re.fullmatch(r"[0-9a-f]{40}", value or "") is None for value in (H.SOURCE, os.environ.get("GITHUB_SHA"), os.environ.get("GITHUB_WORKFLOW_SHA")))
            or any(re.fullmatch(r"[1-9][0-9]{0,19}", os.environ.get(key, "")) is None for key in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT"))
            or platform.python_version() != "3.14.7" or platform.python_implementation() != "CPython"):
        raise H.Refusal("actual-public-current-qualification-workflow-required")
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise H.Refusal("qualification-duplicate-event-field")
            value[key] = item
        return value
    event = json.loads(H.read_plain(Path(os.environ.get("GITHUB_EVENT_PATH", "")), 2 * 1024 * 1024), object_pairs_hook=unique)
    repository = event.get("repository") if isinstance(event, dict) else None
    if not isinstance(repository, dict) or repository.get("full_name") != "Yunushan/remote-ops-workspace" or repository.get("private") is not False:
        raise H.Refusal("public-same-repository-qualification-required")
    kind = os.environ.get("GITHUB_EVENT_NAME")
    if kind == "pull_request":
        pr, number = event.get("pull_request"), event.get("number")
        if not isinstance(pr, dict) or type(number) is not int or not 0 < number <= 2147483647:
            raise H.Refusal("qualification-same-repository-pr-required")
        head, base = pr.get("head"), pr.get("base")
        if (event.get("action") not in {"opened", "synchronize", "reopened"} or not isinstance(head, dict) or not isinstance(base, dict)
                or any(not isinstance(row.get("repo"), dict) or row["repo"].get("full_name") != "Yunushan/remote-ops-workspace" or row["repo"].get("private") is not False for row in (head, base))
                or head.get("sha") != H.SOURCE or base.get("ref") != "main" or re.fullmatch(r"[0-9a-f]{40}", base.get("sha", "")) is None
                or ref != f"refs/pull/{number}/merge"):
            raise H.Refusal("qualification-same-repository-pr-required")
    elif kind == "workflow_dispatch":
        if (os.environ["GITHUB_SHA"] != H.SOURCE or os.environ["GITHUB_WORKFLOW_SHA"] != H.SOURCE
                or re.fullmatch(r"refs/heads/[A-Za-z0-9][A-Za-z0-9_./-]{0,199}", ref) is None
                or ".." in ref or "//" in ref or ref.endswith(("/", "."))):
            raise H.Refusal("qualification-current-branch-dispatch-required")
    else:
        raise H.Refusal("qualification-event-refused")
    if os.environ.get("GITHUB_WORKFLOW_REF") != "Yunushan/remote-ops-workspace/" + WORKFLOW + "@" + ref:
        raise H.Refusal("qualification-actual-workflow-ref-required")
    return {"repository": "Yunushan/remote-ops-workspace", "event": kind, "source_sha": H.SOURCE, "event_sha": os.environ["GITHUB_SHA"],
            "workflow_sha": os.environ["GITHUB_WORKFLOW_SHA"], "workflow_path": WORKFLOW, "ref_sha256": H.sha(ref.encode()),
            "run_id": os.environ["GITHUB_RUN_ID"], "run_attempt": os.environ["GITHUB_RUN_ATTEMPT"]}


def commands(root, leaders):
    started = time.monotonic()
    env = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}

    def short(argv, stdin=None, timeout=30):
        deadline = min(started + 1500, time.monotonic() + timeout)
        if time.monotonic() >= deadline:
            raise H.Refusal("qualification-command-original-budget")
        leader = H.Managed(argv, env, root)
        leaders.append(leader)
        if stdin is not None:
            leader.child.stdin.write(stdin)
            leader.child.stdin.flush()
        leader.child.stdin.close()
        leader.zero(deadline)
        if leader.buffers[1]:
            raise H.Refusal("qualification-command-stderr")
        return bytes(leader.buffers[0])
    short.remaining = lambda: 1500 - (time.monotonic() - started)
    return short, started


def source_binding(root, short):
    execution = event_guard(root)
    if short(["git", "rev-parse", "HEAD"]).strip().decode("ascii") != H.SOURCE or short(["git", "status", "--porcelain", "--untracked-files=no"]):
        raise H.Refusal("qualification-clean-exact-source-required")
    tree = short(["git", "rev-parse", "HEAD^{tree}"]).strip().decode("ascii")
    if re.fullmatch(r"[0-9a-f]{40}", tree) is None:
        raise H.Refusal("qualification-current-tree-required")
    relative = HERE.relative_to(root).as_posix()
    hashes = {}
    for name in ("qualify_android_stack.py", "hosted_controller.py", "observe_public_stack.py", "archive_readers_frozen.py"):
        raw = H.read_plain(HERE / name, 262144)
        if short(["git", "show", H.SOURCE + ":" + relative + "/" + name]) != raw:
            raise H.Refusal("qualification-tracked-helper-bytes-required")
        hashes[name] = H.sha(raw)
    workflow = H.read_plain(root / WORKFLOW, 131072)
    if short(["git", "show", H.SOURCE + ":" + WORKFLOW]) != workflow:
        raise H.Refusal("qualification-executed-workflow-bytes-required")
    executed = executed_workflow(execution, workflow, getattr(short, "remaining", lambda: 0))
    return {"source_sha": H.SOURCE, "source_tree": tree, "helpers": hashes, "workflow_sha256": H.sha(workflow),
            "run_id": os.environ["GITHUB_RUN_ID"], "run_attempt": os.environ["GITHUB_RUN_ATTEMPT"], "execution": execution,
            "executed_workflow": executed}


def executed_workflow(execution, expected_raw, remaining, clock=time.monotonic):
    # Fixed immutable public URL only; no ambient authentication/proxy/redirect.
    if (re.fullmatch(r"[0-9a-f]{40}", execution.get("workflow_sha", "")) is None or execution.get("workflow_path") != WORKFLOW
            or not isinstance(expected_raw, bytes) or not 0 < len(expected_raw) <= 131072):
        raise H.Refusal("qualification-workflow-input-required")
    started = clock()
    deadline = started + min(60, remaining())
    if deadline <= started:
        raise H.Refusal("qualification-workflow-original-budget")
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *_args, **_kwargs):
            raise H.Refusal("qualification-workflow-redirect-refused")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    url = "https://raw.githubusercontent.com/Yunushan/remote-ops-workspace/" + execution["workflow_sha"] + "/" + WORKFLOW
    request = urllib.request.Request(url, headers={"Accept": "text/plain", "User-Agent": "ROW-public-qualification"})
    with opener.open(request, timeout=min(20, deadline - started)) as response:
        if response.status != 200 or response.headers.get("Content-Encoding", "identity") != "identity":
            raise H.Refusal("qualification-workflow-response-layout")
        length = response.headers.get("Content-Length")
        if length is not None and (re.fullmatch(r"[1-9][0-9]{0,9}", length) is None or int(length) > 131072):
            raise H.Refusal("qualification-workflow-content-bound")
        raw = bytearray()
        while True:
            if clock() >= deadline or remaining() <= 0:
                raise H.Refusal("qualification-workflow-byte-or-time-bound")
            chunk = response.read(min(65536, 131073 - len(raw)))
            if clock() >= deadline or remaining() <= 0:
                raise H.Refusal("qualification-workflow-byte-or-time-bound")
            if not chunk:
                break
            raw.extend(chunk)
            if len(raw) > 131072:
                raise H.Refusal("qualification-workflow-byte-or-time-bound")
        if clock() >= deadline or remaining() <= 0 or (length is not None and len(raw) != int(length)) or bytes(raw) != expected_raw:
            raise H.Refusal("qualification-actual-executed-workflow-mismatch-or-late")
    return {"workflow_sha": execution["workflow_sha"], "size_bytes": len(raw), "sha256": H.sha(raw), "source_contract_matches": True, "redirects": 0}


def observe_public(root):
    event_guard(root)  # Before any public acquisition; supports exact PR head checkout.
    leaders = []
    try:
        short, _started = commands(root, leaders)
        binding = source_binding(root, short)  # Actual executed workflow bytes first.
        return O._observe_bound_source(root, binding, source_check=lambda: source_binding(root, short), remaining=short.remaining)
    finally:
        initial = sys.exc_info()[1]
        if any(not row["complete"] for row in H.cleanup_all(leaders)) and initial is None:
            raise H.Refusal("qualification-owned-cleanup-unproved")


def owned_sdk():
    temp = Path(os.environ.get("RUNNER_TEMP", ""))
    if not temp.is_absolute() or temp.resolve() != temp or temp.is_symlink() or temp == Path("/"):
        raise H.Refusal("qualified-owned-runner-temp-required")
    sdk = temp / "row-browser-api36-sdk"
    if sdk.resolve() != sdk or sdk.is_symlink():
        raise H.Refusal("qualified-owned-sdk-path-required")
    return sdk


def bootstrap(root):
    event_guard(root)
    leaders = []
    try:
        short, _started = commands(root, leaders)
        binding = source_binding(root, short)
        if os.environ.get("ANDROID_HOME") != str(FIXED_SOURCE_SDK) or FIXED_SOURCE_SDK.resolve() != FIXED_SOURCE_SDK:
            raise H.Refusal("actual-hosted-source-sdk-layout-required")
        if owned_sdk().exists():
            raise H.Refusal("fresh-isolated-sdk-required")
        value = {"schema": "row.android-sdk-bootstrap-observation.v1", "binding": binding,
                 "cmdline_tree_sha256": H.tree_digest(FIXED_SOURCE_SDK / "cmdline-tools/latest", maximum_bytes=512 * 1024 * 1024),
                 "already_present_license_tree_sha256": H.tree_digest(FIXED_SOURCE_SDK / "licenses", maximum_files=128, maximum_bytes=2 * 1024 * 1024),
                 "signing_or_license_approval": False, "readiness_credit": 0}
        O.save(root / BOOTSTRAP, (json.dumps(value, indent=2) + "\n").encode())
        return {"status": "public-hosted-tool-inputs-observed", "bootstrap_sha256": H.sha(H.read_plain(root / BOOTSTRAP, 65536)), "readiness_credit": 0}
    finally:
        initial = sys.exc_info()[1]
        if any(not row["complete"] for row in H.cleanup_all(leaders)) and initial is None:
            raise H.Refusal("qualification-owned-cleanup-unproved")


def clone_guard(root, short, binding=None):
    if binding is None:
        binding = source_binding(root, short)
    observation = json.loads(H.read_plain(root / BOOTSTRAP, 65536))
    if (set(observation) != {"schema", "binding", "cmdline_tree_sha256", "already_present_license_tree_sha256", "signing_or_license_approval", "readiness_credit"}
            or observation["schema"] != "row.android-sdk-bootstrap-observation.v1" or observation["binding"] != binding
            or observation["signing_or_license_approval"] is not False or observation["readiness_credit"] != 0):
        raise H.Refusal("exact-current-bootstrap-observation-required")
    sdk = owned_sdk()
    if (H.tree_digest(sdk / "cmdline-tools/latest", maximum_bytes=512 * 1024 * 1024) != H.digest(observation["cmdline_tree_sha256"])
            or H.tree_digest(sdk / "licenses", maximum_files=128, maximum_bytes=2 * 1024 * 1024) != H.digest(observation["already_present_license_tree_sha256"])):
        raise H.Refusal("actual-cloned-tool-bytes-required")
    return binding, observation


def sdk_inventory(sdk):
    metadata = []
    prefixes = ("cmdline-tools/latest", "platform-tools", "emulator", "platforms/android-36", "system-images/android-36/google_apis/x86_64")
    for prefix in prefixes:
        for name in ("package.xml", "source.properties"):
            raw = H.read_plain(sdk / prefix / name, 512 * 1024)
            row = {"component": prefix, "file": name, "bytes": len(raw), "sha256": H.sha(raw)}
            if name == "source.properties":
                values = re.findall(rb"^Pkg\.Revision\s*=\s*([0-9]+(?:\.[0-9]+){0,3}(?:[- ](?:beta|rc)[0-9]*)?)\s*$", raw, re.MULTILINE)
                row["revision"] = values[0].decode("ascii") if len(values) == 1 and len(values[0]) <= 64 else "unobserved-format"
            metadata.append(row)
    tools = []
    for name, relative in (("adb", "platform-tools/adb"), ("emulator", "emulator/emulator"), ("avdmanager", "cmdline-tools/latest/bin/avdmanager"), ("sdkmanager", "cmdline-tools/latest/bin/sdkmanager")):
        raw = H.read_plain(sdk / relative, 128 * 1024 * 1024)
        tools.append({"tool": name, "bytes": len(raw), "sha256": H.sha(raw)})
    return {"tree_sha256": H.tree_digest(sdk, maximum_files=30000, maximum_bytes=4 * 1024 * 1024 * 1024), "metadata": metadata, "tools": tools,
            "catalog_approval": False, "license_approval": False, "whole_image_semantic_closure": "not-established"}


def public_receipt(root, record):
    raw = (json.dumps(record, indent=2) + "\n").encode()
    if len(raw) > 131072:
        raise H.Refusal("qualification-public-receipt-bound")
    O.save(root / REPORT, raw)
    marker = Path(os.environ.get("GITHUB_OUTPUT", ""))
    if not marker.is_absolute() or marker.resolve() != marker or any(parent.is_symlink() for parent in marker.parents):
        raise H.Refusal("qualification-runner-output-required")
    before = marker.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > 65536:
        raise H.Refusal("qualification-runner-output-required")
    fd = os.open(marker, os.O_WRONLY | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "wb") as stream:
        opened = os.fstat(stream.fileno())
        if (opened.st_dev, opened.st_ino, opened.st_size) != (before.st_dev, before.st_ino, before.st_size):
            raise H.Refusal("qualification-runner-output-changed")
        stream.write(b"public_receipt=saved\n")
        stream.flush()
        after = os.fstat(stream.fileno())
    after_path = marker.lstat()
    if after.st_size != before.st_size + 21 or (after.st_dev, after.st_ino, after.st_size) != (after_path.st_dev, after_path.st_ino, after_path.st_size):
        raise H.Refusal("qualification-runner-output-changed")


def capture(root):
    event_guard(root)
    leaders, context = [], None
    try:
        short, started = commands(root, leaders)
        binding = source_binding(root, short)
        context = {"binding": binding, "phase": "bootstrap-and-cloned-sdk", "observed": {}}
        binding, bootstrap_record = clone_guard(root, short, binding)
        context["phase"] = "sdk-observation"
        sdk = owned_sdk()
        if Path(os.environ.get("ANDROID_HOME", "")) != sdk:
            raise H.Refusal("actual-isolated-sdk-environment-required")
        observed = sdk_inventory(sdk)
        context["observed"]["sdk_tree_sha256"] = observed["tree_sha256"]
        private = root / ".tmp" / ("android-toolchain-owned-" + secrets.token_hex(16))
        if private.parent.resolve() != private.parent:
            raise H.Refusal("qualification-private-parent-required")
        private.mkdir(mode=0o700)
        for name in ("home", "avd", "android-home"):
            (private / name).mkdir(mode=0o700)
        env = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "HOME": str(private / "home"),
               "ANDROID_HOME": str(sdk), "ANDROID_SDK_ROOT": str(sdk), "ANDROID_AVD_HOME": str(private / "avd"),
               "ANDROID_USER_HOME": str(private / "android-home"), "ADB_SERVER_SOCKET": "tcp:127.0.0.1:5039", "ANDROID_ADB_SERVER_PORT": "5039",
               "ADB_MDNS_AUTO_CONNECT": "", "ADB_LOCAL_TRANSPORT_MAX_PORT": "5557", "JAVA_HOME": os.environ.get("JAVA_HOME", "")}

        def native(argv, stdin=None, timeout=30):
            deadline = min(started + 1500, time.monotonic() + timeout)
            if time.monotonic() >= deadline:
                raise H.Refusal("qualification-command-original-budget")
            child = H.Managed(argv, env, root)
            leaders.append(child)
            if stdin is not None:
                child.child.stdin.write(stdin)
                child.child.stdin.flush()
            child.child.stdin.close()
            child.zero(deadline)
            if child.buffers[1]:
                raise H.Refusal("qualification-command-stderr")
            return bytes(child.buffers[0])

        context["phase"] = "owned-api36-emulator"
        avd = "row-qualification-36-" + secrets.token_hex(8)
        native([str(sdk / "cmdline-tools/latest/bin/avdmanager"), "create", "avd", "-n", avd, "-k", "system-images;android-36;google_apis;x86_64", "--device", "pixel_6"], stdin=b"no\n", timeout=180)
        for port in (H.ADB_PORT, 5556, 5557):
            with socket.socket() as reservation:
                reservation.bind(("127.0.0.1", port))
        adb_leader = H.Managed([str(sdk / "platform-tools/adb"), "-L", "tcp:127.0.0.1:5039", "nodaemon", "server"], env, root)
        leaders.append(adb_leader)
        ready = time.monotonic() + 10
        while time.monotonic() < ready:
            try:
                H.owned_listener(adb_leader, H.ADB_PORT)
                if time.monotonic() >= ready:
                    raise H.Refusal("qualification-late-adb-listener")
                break
            except H.Refusal as exc:
                if str(exc) != "owned-loopback-listener-missing":
                    raise
            time.sleep(0.1)
        else:
            raise H.Refusal("qualification-adb-listener-deadline")
        emulator = H.Managed([str(sdk / "emulator/emulator"), "-avd", avd, "-port", "5556", "-no-window", "-gpu", "swiftshader_indirect", "-no-snapshot", "-no-snapshot-load", "-no-snapshot-save", "-noaudio", "-no-boot-anim", "-camera-back", "none", "-no-metrics"], env, root)
        leaders.append(emulator)
        adb = H.AdbSocket(adb_leader)
        connected = time.monotonic() + 180
        while time.monotonic() < connected:
            emulator.live()
            rows = adb.command("host:devices", framed=True, timeout=min(30, connected - time.monotonic())).decode("ascii").splitlines()
            if time.monotonic() >= connected:
                raise H.Refusal("qualification-late-device")
            if rows == [H.SERIAL + "\tdevice"]:
                break
            if any(row and row.split("\t")[0] != H.SERIAL for row in rows):
                raise H.Refusal("qualification-foreign-device")
            time.sleep(0.1)
        else:
            raise H.Refusal("qualification-device-deadline")
        boot = time.monotonic() + 180
        while time.monotonic() < boot:
            emulator.live()
            value = H.shell_v2(adb.command("shell,v2,raw:getprop sys.boot_completed", transport=True, timeout=min(30, boot - time.monotonic()))).strip()
            if time.monotonic() >= boot:
                raise H.Refusal("qualification-late-boot")
            if value == b"1":
                break
            time.sleep(0.1)
        else:
            raise H.Refusal("qualification-boot-deadline")
        if adb.shell("getprop ro.build.version.sdk").strip() != b"36" or adb.shell("getprop ro.product.cpu.abi").strip() != b"x86_64":
            raise H.Refusal("qualification-api-or-abi-mismatch")
        context["phase"] = "chrome-static-device-inventory"
        chrome = H.package_inventory(adb, "com.android.chrome")
        sockets = adb.shell("cat /proc/net/unix")
        socket_rows = sockets.decode("ascii").splitlines()
        # No am start, UI command, Playwright require or DevTools connection.
        socket_seen = any(row.split()[-1:] == ["@chrome_devtools_remote"] for row in socket_rows)
        context["observed"]["chrome_apk_count"] = len(chrome["apks"])
        if (source_binding(root, short) != binding or sdk_inventory(sdk) != observed
                or H.package_inventory(adb, "com.android.chrome") != chrome or time.monotonic() >= started + 1500):
            raise H.Refusal("qualification-current-source-tool-or-device-changed")
        cleanup = H.cleanup_all(leaders)
        if any(not row["complete"] for row in cleanup):
            raise H.Refusal("qualification-owned-cleanup-unproved")
        record = {"schema": "row.android-toolchain-qualification.v1", "status": "observations-with-unresolved-browser",
                  "binding": binding, "bootstrap": bootstrap_record, "sdk": observed, "android_api": 36, "serial": H.SERIAL,
                  "chrome": chrome, "devtools_socket_seen_before_launch": socket_seen, "devtools_socket_inventory_sha256": hashlib.sha256(sockets).hexdigest(),
                  "CDP_availability": "not-probed-without-browser-launch", "native_product_or_browser_launch": False,
                  "Playwright_or_NPM_code_execution": False, "Android_helper_APKs": False, "owned_leader_cleanup": cleanup,
                  "process_descendants": "disposable-host-destruction-required", "approval": False, "readiness_credit": 0}
        public_receipt(root, record)
        return {"status": record["status"], "output_sha256": H.sha(H.read_plain(root / REPORT, 131072)), "readiness_credit": 0}
    except Exception:
        if context is not None:
            record = {"schema": "row.android-toolchain-qualification.v1", "status": "refused", **context,
                      "native_product_or_browser_launch": False, "CDP_availability": "unproved", "source_unchanged": "not-established", "approval": False, "readiness_credit": 0}
            try:
                public_receipt(root, record)
            except Exception:
                pass
        raise
    finally:
        initial = sys.exc_info()[1]
        if any(not row["complete"] for row in H.cleanup_all(leaders)) and initial is None:
            raise H.Refusal("qualification-owned-cleanup-unproved")


DEVICE = "/dev/kvm"
MAX_ID = (1 << 63) - 1


class KvmContractRefusal(ValueError):
    pass



def _bounded_integer(value, minimum=0, maximum=MAX_ID):
    if type(value) is not int or not minimum <= value <= maximum:
        raise KvmContractRefusal("kvm-observation-layout")
    return value



def kvm_projection(snapshot):
    """Classify only a fixed path's bounded stat/access facts, never an error string."""
    if type(snapshot) is not dict or snapshot.get("path") != DEVICE:
        raise KvmContractRefusal("fixed-kvm-observation-required")
    if type(snapshot.get("present")) is not bool:
        raise KvmContractRefusal("kvm-observation-layout")
    if snapshot["present"] is False:
        if set(snapshot) != {"path", "present", "errno"}:
            raise KvmContractRefusal("kvm-observation-layout")
        number = _bounded_integer(snapshot["errno"], 1, 4095)
        return {"path": DEVICE, "present": False, "errno": number,
                "classification": "device-missing" if number == 2 else "device-stat-refused",
                "qualified_device_identity": False, "permission_change": False,
                "approval": False, "readiness_credit": 0}
    keys = {"path", "present", "mode", "uid", "gid", "dev", "ino", "nlink", "rdev_major", "rdev_minor", "readable", "writable"}
    if set(snapshot) != keys or any(type(snapshot[k]) is not bool for k in ("readable", "writable")):
        raise KvmContractRefusal("kvm-observation-layout")
    mode = _bounded_integer(snapshot["mode"], 0, 0o177777)
    for key in ("uid", "gid", "dev", "rdev_major", "rdev_minor"):
        _bounded_integer(snapshot[key])
    for key in ("ino", "nlink"):
        _bounded_integer(snapshot[key], 1)
    character = stat.S_ISCHR(mode)
    symlink = stat.S_ISLNK(mode)
    qualified = character and snapshot["uid"] == 0 and snapshot["nlink"] == 1 and (snapshot["rdev_major"], snapshot["rdev_minor"]) == (10, 232)
    kind = "symlink" if symlink else "character-device" if character else "wrong-file-type"
    if not qualified:
        classification = "device-identity-refused"
    elif not snapshot["readable"]:
        classification = "device-read-access-refused"
    elif not snapshot["writable"]:
        classification = "device-write-access-refused"
    else:
        classification = "device-read-write-observed"
    return {"path": DEVICE, "present": True, "kind": kind, "mode": stat.S_IMODE(mode),
            **{k: snapshot[k] for k in ("uid", "gid", "dev", "ino", "nlink", "rdev_major", "rdev_minor", "readable", "writable")},
            "classification": classification, "qualified_device_identity": qualified,
            "permission_change": False, "approval": False, "readiness_credit": 0}



def kvm_preflight(root):
    # Read-only diagnostics on one literal device; no open/ioctl or ACL changes.
    event_guard(root)
    leaders = []
    try:
        short, _started = commands(root, leaders)
        binding = source_binding(root, short)
        context = {"schema": "row.android-kvm-readonly-preflight.v1", "binding": binding,
                   "phase": "owned-host-kvm-lstat-preflight", "approval": False, "readiness_credit": 0}
        try:
            before = os.lstat("/dev/kvm")
        except OSError as exc:
            number = exc.errno if type(exc.errno) is int and 0 < exc.errno <= 4095 else 4095
            snapshot = {"path": "/dev/kvm", "present": False, "errno": number}
        else:
            snapshot = {"path": "/dev/kvm", "present": True, "mode": before.st_mode,
                        "uid": before.st_uid, "gid": before.st_gid, "dev": before.st_dev,
                        "ino": before.st_ino, "nlink": before.st_nlink,
                        "rdev_major": os.major(before.st_rdev), "rdev_minor": os.minor(before.st_rdev),
                        "readable": os.access("/dev/kvm", os.R_OK, effective_ids=True, follow_symlinks=False),
                        "writable": os.access("/dev/kvm", os.W_OK, effective_ids=True, follow_symlinks=False)}
            fields = ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_nlink", "st_rdev", "st_ctime_ns", "st_mtime_ns")
            try:
                after = os.lstat("/dev/kvm")
                stable = all(getattr(before, name) == getattr(after, name) for name in fields)
            except OSError:
                stable = False
            if not stable:
                if source_binding(root, short) != binding:
                    raise H.Refusal("qualification-current-source-changed")
                context["device"] = {"path": "/dev/kvm", "classification": "device-stat-access-raced-refused",
                                     "permission_change": False, "qualified_device_identity": False}
                print(json.dumps(context))
                raise H.Refusal("owned-host-kvm-stable-identity-required")
        context["device"] = kvm_projection(snapshot)
        if source_binding(root, short) != binding:
            raise H.Refusal("qualification-current-source-changed")
        if not context["device"]["qualified_device_identity"]:
            print(json.dumps(context))
            raise H.Refusal("owned-host-character-kvm-identity-required")
        return context
    finally:
        initial = sys.exc_info()[1]
        if any(not row["complete"] for row in H.cleanup_all(leaders)) and initial is None:
            raise H.Refusal("qualification-owned-cleanup-unproved")



def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("plan", "guard", "observe-public", "bootstrap", "guard-clone", "kvm-preflight", "capture"), default="plan", nargs="?")
    args = parser.parse_args(argv)
    if args.action == "plan":
        print(json.dumps({"status": "qualification-only", "no_browser_or_product_launch": True, "CDP_availability": "requires-separate-actual-browser-proof", "readiness_credit": 0}))
        return 0
    try:
        root = Path.cwd().resolve()
        if args.action == "kvm-preflight":
            value = kvm_preflight(root)
        elif args.action == "bootstrap":
            value = bootstrap(root)
        elif args.action == "observe-public":
            value = observe_public(root)
        elif args.action == "capture":
            value = capture(root)
        else:
            event_guard(root)
            leaders = []
            try:
                short, _started = commands(root, leaders)
                source_binding(root, short) if args.action == "guard" else clone_guard(root, short)
                value = {"status": "exact-current-host-source-guard", "readiness_credit": 0}
            finally:
                initial = sys.exc_info()[1]
                if any(not row["complete"] for row in H.cleanup_all(leaders)) and initial is None:
                    raise H.Refusal("qualification-owned-cleanup-unproved")
        print(json.dumps(value))
        return 0
    except Exception:
        print("android-toolchain-qualification-refused", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
