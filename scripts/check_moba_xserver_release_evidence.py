from __future__ import annotations

import argparse
import json
import re
import struct
import sys
import zlib
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for location in (ROOT, SRC):
    if str(location) not in sys.path:
        sys.path.insert(0, str(location))

from remote_ops_workspace.x11 import (  # noqa: E402
    XSERVER_RUNTIME_BUNDLE_SCHEMA,
    XServerReleaseEvidenceValidation,
    validate_moba_x_server_release_evidence,
)
from scripts.check_gui_visual_metrics import read_png_rgb  # noqa: E402
from scripts.check_mobaxterm_parity_evidence import capture_release_identity  # noqa: E402
from scripts.check_release_license_compliance import (  # noqa: E402
    bound_evidence_file,
    read_json_object,
    secure_regular_file,
)
from scripts.debian_release_fixture import (  # noqa: E402
    PRODUCT_PACKAGE,
    ROW_EXECUTABLE,
    release_deb_version,
    validate_native_debian_probe,
)

FORWARDING_SCHEMA = "row.moba-xserver.ssh-forwarding.v1"
REMOTE_DISPLAY_PROBE = 'printf "remote_display=%s\\n" "$DISPLAY"'
NATIVE_PROBE_SCHEMA = "row.x11.native-evidence-verify.v1"
NATIVE_PROBE_PATH = "row-native-evidence-verify.json"
NATIVE_PROBE_ARGV = [ROW_EXECUTABLE, "x11", "evidence-verify", "--evidence", "evidence.json", "--assets-dir", ".", "--json"]
INSTALLED_XSERVER = PurePosixPath("/usr/lib/remote-ops-workspace/xserver")


def check_packaged_runtime(root: Path, evidence: dict[str, Any]) -> tuple[bool, bool]:
    runtime = evidence["runtime"]
    path = bound_evidence_file(
        root, runtime.get("manifest"), runtime.get("manifest_sha256"), "runtime manifest"
    )
    _, manifest = read_json_object(path, "runtime manifest")
    packaged = manifest.get("runtime")
    if (
        manifest.get("schema") != XSERVER_RUNTIME_BUNDLE_SCHEMA
        or manifest.get("release_target") != evidence["release_target"]
        or str(manifest.get("system", "")).lower() != str(evidence["platform"]).lower()
        or not isinstance(packaged, dict)
        or packaged.get("placeholder") is not False
        or packaged.get("bundled") is not True
        or packaged.get("source") != "packaged"
        or not isinstance(packaged.get("executable"), str)
        or packaged.get("key") != runtime["key"]
        or packaged.get("sha256") != runtime["sha256"]
        or (path.parent.relative_to(root) / packaged["executable"]).as_posix()
        != runtime["executable"]
    ):
        raise ValueError(
            "runtime manifest must describe the same release and real bundled X server"
        )

    start_path = bound_evidence_file(
        root, runtime.get("start"), runtime.get("start_sha256"), "managed X server start"
    )
    _, start = read_json_object(start_path, "managed X server start")
    selected, lifecycle, command = (
        start.get("runtime"),
        start.get("lifecycle"),
        start.get("command"),
    )
    from_package = "installed_runtime" in runtime
    unprivileged = False
    if from_package:
        observed_path = INSTALLED_XSERVER / packaged["executable"]
        receipt_path = bound_evidence_file(
            root, runtime["installed_runtime"], runtime.get("installed_runtime_sha256"), "installed X server receipt",
        )
        _, receipt = read_json_object(receipt_path, "installed X server receipt")
        if (
            "release_asset" not in evidence or not isinstance(lifecycle, dict)
            or type(receipt.get("pid")) is not int or receipt["pid"] <= 1 or receipt["pid"] != lifecycle.get("pid")
            or receipt.get("executable") != str(observed_path)
            or receipt.get("owner") != PRODUCT_PACKAGE
            or receipt.get("sha256") != runtime["sha256"]
        ):
            raise ValueError("installed X server receipt must bind the package-owned executable to the live process")
        if "uids" in receipt or "effective_capabilities" in receipt:
            uids = receipt.get("uids")
            capabilities = receipt.get("effective_capabilities")
            if (
                not isinstance(uids, list) or len(uids) != 4
                or not all(type(uid) is int and uid > 0 for uid in uids) or len(set(uids)) != 1
                or type(capabilities) is not int or capabilities != 0
            ):
                raise ValueError("installed X server receipt must show an unprivileged desktop process")
            unprivileged = True
        selected_path_matches = executable_name(command) and command[0] == str(observed_path)
    else:
        selected_path_matches = executable_name(command) and command[0].replace("\\", "/").endswith(
            "/" + runtime["executable"],
        )
    if (
        start.get("display") != evidence["display"]
        or not isinstance(selected, dict)
        or selected.get("bundled") is not True
        or selected.get("key") != runtime["key"]
        or not selected_path_matches
        or command[0] != selected.get("executable")
        or not isinstance(lifecycle, dict)
        or lifecycle.get("command") != command
        or lifecycle.get("runtime_key") != runtime["key"]
        or lifecycle.get("state") != "started"
        or lifecycle.get("display") != evidence["display"]
        or lifecycle.get("running") is not True
        or lifecycle.get("dry_run") is not False
    ):
        raise ValueError(
            "managed X server start must record the live bundled runtime on the evidenced display"
        )
    return from_package, unprivileged


def executable_name(argv: Any) -> str:
    if (
        not isinstance(argv, list)
        or not argv
        or not all(isinstance(arg, str) and arg for arg in argv)
    ):
        return ""
    return PurePosixPath(argv[0].replace("\\", "/")).name.lower().removesuffix(".exe")


def check_display_probe(path: Path, evidence: dict[str, Any]) -> None:
    _, smoke = read_json_object(path, "X11 smoke")
    display = evidence["display"]
    probe = smoke.get("probe_command")
    if (
        smoke.get("status") != "passed"
        or type(smoke.get("returncode")) is not int
        or smoke["returncode"] != 0
        or smoke.get("runtime_key") != evidence["runtime"]["key"]
        or smoke.get("lifecycle_running") is not True
        or smoke.get("display_in_use") is not True
        or executable_name(probe) != "xdpyinfo"
        or display not in probe[1:]
        or not re.search(
            rf"^name of display:\s+{re.escape(display)}(?:\.0)?$", str(smoke.get("stdout")), re.M
        )
    ):
        raise ValueError(
            "X11 smoke must record a successful xdpyinfo probe of the running bundled display"
        )


def check_forwarded_window(root: Path, evidence: dict[str, Any], screenshot: Path) -> None:
    forwarded = evidence["forwarded_gui_app"]
    path = bound_evidence_file(
        root,
        forwarded.get("receipt"),
        forwarded.get("receipt_sha256"),
        "SSH forwarding receipt",
    )
    _, receipt = read_json_object(path, "SSH forwarding receipt")
    argv = receipt.get("ssh_argv")
    forwarding_flags = {"trusted": {"-Y"}, "untrusted": {"-X"}, "enabled": {"-X", "-Y"}}
    mode, command = forwarded.get("x11_forwarding"), forwarded.get("command")
    if (
        receipt.get("schema") != FORWARDING_SCHEMA
        or receipt.get("display") != evidence["display"]
        or not re.fullmatch(r"[A-Za-z0-9.-]+:[0-9]+\.[0-9]+", str(receipt.get("remote_display")))
        or receipt.get("runtime_sha256") != evidence["runtime"]["sha256"]
        or receipt.get("start_sha256") != evidence["runtime"]["start_sha256"]
        or receipt.get("smoke_sha256") != evidence["smoke"]["evidence_sha256"]
        or receipt.get("screenshot_sha256") != forwarded["screenshot_sha256"]
        or not isinstance(command, str)
        or receipt.get("command") != command
        or executable_name(argv) != "ssh"
        or not isinstance(mode, str)
        or not forwarding_flags.get(mode, set()).intersection(argv[:-1])
    ):
        raise ValueError(
            "SSH forwarding receipt must bind the display, command, runtime, probe and screenshot"
        )

    # The control must use the same destination, credentials, and SSH settings. Only
    # forwarding and the remote command change between these two real sessions.
    control = receipt.get("control_argv")
    expected = ["-x" if item in {"-X", "-Y"} else item for item in argv[:-1]]
    if (
        argv[-1] != f"{REMOTE_DISPLAY_PROBE}; exec {command}"
        or sum(item in {"-X", "-Y"} for item in argv[:-1]) != 1 or "-x" in argv[:-1]
        or control != [*expected, REMOTE_DISPLAY_PROBE]
        or receipt.get("control_stdout") != "remote_display=\n"
    ):
        raise ValueError("SSH forwarding receipt must include a matched session with forwarding disabled and no remote display")

    window_id, title = receipt["window_id"], receipt["window_title"]
    info = bound_evidence_file(
        root, receipt["window_info"], receipt["window_info_sha256"], "X11 window capture"
    )
    window = info.read_text(encoding="utf-8").splitlines()
    if (
        not isinstance(title, str)
        or not title.strip()
        or not isinstance(window_id, str)
        or not re.fullmatch(r"0x[0-9a-fA-F]+", window_id)
        or f'xwininfo: Window id: {window_id} "{title}"' not in window
        or "Map State: IsViewable" not in {line.strip() for line in window}
    ):
        raise ValueError(
            "X11 window capture must show the observed window ID and title in a viewable state"
        )
    if screenshot.stat().st_size > 16 * 1024 * 1024:
        raise ValueError("forwarded window screenshot exceeds 16 MiB")
    image = read_png_rgb(screenshot, max_pixels=4_194_304)
    if all(pixel == image.pixels[0] for pixel in image.pixels):
        raise ValueError("forwarded window screenshot must contain visible content")


def validate_forwarding_capture(
    evidence_path: Path,
    *,
    assets_dir: Path | None,
    require_release_source: bool,
) -> XServerReleaseEvidenceValidation:
    root = assets_dir if assets_dir is not None else evidence_path.parent
    try:
        relative = evidence_path.absolute().relative_to(root.absolute()).as_posix()
        evidence_file, error = secure_regular_file(root, relative, "X11 release evidence")
        if evidence_file is None:
            raise ValueError(error)
        _, evidence = read_json_object(evidence_file, "X11 release evidence")
        for section in ("runtime", "smoke", "forwarded_gui_app"):
            if not isinstance(evidence.get(section), dict):
                raise ValueError(f"X11 release evidence requires a {section} object")
        runtime, smoke, forwarded = (
            evidence[key] for key in ("runtime", "smoke", "forwarded_gui_app")
        )
        bound_evidence_file(root, runtime["executable"], runtime["sha256"], "X server executable")
        probe = bound_evidence_file(
            root, smoke["evidence_file"], smoke["evidence_sha256"], "X11 smoke"
        )
        image = bound_evidence_file(
            root, forwarded["screenshot"], forwarded["screenshot_sha256"], "X11 screenshot"
        )
        result = validate_moba_x_server_release_evidence(evidence_file, assets_dir=root)
        if not result.passed:
            return result
        from_package, unprivileged = check_packaged_runtime(root, evidence)
        check_display_probe(probe, evidence)
        check_forwarded_window(root, evidence, image)
        if "release_asset" in evidence:
            result.summary["tested_release_asset"] = validate_native_debian_probe(
                root, evidence_file, evidence, result.summary,
                schema=NATIVE_PROBE_SCHEMA, receipt_path=NATIVE_PROBE_PATH, argv=NATIVE_PROBE_ARGV,
            )
        if require_release_source:
            if "tested_release_asset" not in result.summary:
                raise ValueError("strict X11 evidence requires a native Debian release asset probe")
            identity = capture_release_identity(evidence, "X11 release evidence")
            if from_package and not unprivileged:
                raise ValueError("package-owned X11 release evidence requires an unprivileged desktop process")
            version = release_deb_version(identity["tested_release_asset"]["name"], evidence["release_target"])
            if identity["release_tag"] != f"v{version}":
                raise ValueError("tested Debian package version must match the exact X11 release tag")
            result.summary.update(identity)
        if from_package:
            result.summary["installed_runtime_verified"] = True
        if unprivileged:
            result.summary["unprivileged_runtime_verified"] = True
    except (KeyError, OSError, ValueError, struct.error, zlib.error) as exc:
        return XServerReleaseEvidenceValidation(
            str(evidence_path), str(root), False, [str(exc)], [], {}
        )
    result.summary["live_forwarding_receipt_verified"] = True
    return result


def validate_moba_x_server_live_release_evidence(
    evidence_path: Path, *, assets_dir: Path | None = None,
) -> XServerReleaseEvidenceValidation:
    return validate_forwarding_capture(evidence_path, assets_dir=assets_dir, require_release_source=False)


def validate_moba_x_server_release_asset_evidence(
    evidence_path: Path, *, assets_dir: Path | None = None,
) -> XServerReleaseEvidenceValidation:
    return validate_forwarding_capture(evidence_path, assets_dir=assets_dir, require_release_source=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify MobaXterm-style packaged X server release evidence."
    )
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--assets-dir", type=Path)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--local-capture", action="store_true", help="qualify forwarding without exact release provenance")
    args = parser.parse_args()

    validator = validate_moba_x_server_live_release_evidence if args.local_capture else validate_moba_x_server_release_asset_evidence
    result = validator(args.evidence, assets_dir=args.assets_dir)
    if args.json:
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    elif result.passed:
        print("moba xserver release evidence passed")
    else:
        for error in result.errors:
            print(f"moba xserver release evidence: {error}", file=sys.stderr)
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
