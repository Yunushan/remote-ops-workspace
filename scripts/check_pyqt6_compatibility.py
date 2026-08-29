from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLCHAIN_PATH = ROOT / "configs" / "release_toolchain.json"
VERSION_RE = re.compile(
    r"^\s*v?(?P<major>\d+)\.(?P<minor>\d+)(?:\.(?P<micro>\d+))?"
)
Version = tuple[int, int, int]


@dataclass(frozen=True)
class PyQt6Policy:
    minimum_version: Version
    target_version: Version
    maximum_version_exclusive: Version


@dataclass(frozen=True)
class PyQt6Runtime:
    distribution_version: str
    binding_version: str
    qt_distribution_version: str
    qt_version: str
    sip_distribution_version: str


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate the installed PyQt6 runtime and its forward-compatibility contract."
    )
    parser.add_argument(
        "--target-version",
        help="Forward-compatibility target, defaulting to the release-toolchain policy.",
    )
    parser.add_argument(
        "--require-pyqt6",
        action="store_true",
        help="Fail when PyQt6 is not installed instead of reporting a deferred check.",
    )
    parser.add_argument(
        "--require-target",
        action="store_true",
        help="Fail unless both the PyQt6 binding and bundled Qt runtime meet the target version.",
    )
    args = parser.parse_args(argv)

    try:
        policy = load_policy()
        target_version = (
            parse_version(args.target_version, label="target version")
            if args.target_version
            else policy.target_version
        )
        target_errors = validate_target_version(policy, target_version)
    except (OSError, TypeError, ValueError, json.JSONDecodeError, KeyError) as exc:
        print(f"PyQt6 compatibility: invalid release-toolchain policy: {exc}", file=sys.stderr)
        return 1

    if target_errors:
        for error in target_errors:
            print(f"PyQt6 compatibility: {error}", file=sys.stderr)
        return 1

    errors, messages = check_runtime(
        policy,
        target_version=target_version,
        require_pyqt6=args.require_pyqt6 or args.require_target,
        require_target=args.require_target,
    )
    for message in messages:
        print(f"PyQt6 compatibility: {message}")
    if errors:
        for error in errors:
            print(f"PyQt6 compatibility: {error}", file=sys.stderr)
        return 1
    print("PyQt6 compatibility contract passed")
    return 0


def load_policy(path: Path = TOOLCHAIN_PATH) -> PyQt6Policy:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    raw_policy = manifest["pyqt6_support"]
    return PyQt6Policy(
        minimum_version=parse_version(raw_policy["minimum_version"], label="minimum version"),
        target_version=parse_version(
            raw_policy["forward_compatibility_target"], label="forward-compatibility target"
        ),
        maximum_version_exclusive=parse_version(
            raw_policy["maximum_version_exclusive"], label="maximum version"
        ),
    )


def parse_version(value: str, *, label: str = "version") -> Version:
    match = VERSION_RE.match(value)
    if match is None:
        raise ValueError(f"{label} must start with major.minor[.micro], got {value!r}")
    return (
        int(match.group("major")),
        int(match.group("minor")),
        int(match.group("micro") or 0),
    )


def distribution_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def probe_runtime() -> PyQt6Runtime:
    versions = {
        name: distribution_version(name)
        for name in ("PyQt6", "PyQt6-Qt6", "PyQt6-sip")
    }
    missing = [name for name, version in versions.items() if version is None]
    if missing:
        raise RuntimeError(f"missing distributions: {', '.join(missing)}")

    try:
        from PyQt6.QtCore import PYQT_VERSION_STR, QT_VERSION_STR
    except (ImportError, OSError) as exc:
        raise RuntimeError(f"PyQt6 modules could not be imported: {exc}") from exc

    return PyQt6Runtime(
        distribution_version=versions["PyQt6"] or "",
        binding_version=PYQT_VERSION_STR,
        qt_distribution_version=versions["PyQt6-Qt6"] or "",
        qt_version=QT_VERSION_STR,
        sip_distribution_version=versions["PyQt6-sip"] or "",
    )


def check_runtime(
    policy: PyQt6Policy,
    *,
    target_version: Version,
    require_pyqt6: bool,
    require_target: bool,
    run_widget_smoke: bool = True,
) -> tuple[list[str], list[str]]:
    target_errors = validate_target_version(policy, target_version)
    if target_errors:
        return target_errors, []
    configure_qt_environment()
    try:
        runtime = probe_runtime()
    except (ImportError, OSError, RuntimeError) as exc:
        if require_pyqt6:
            return [f"PyQt6 runtime is required but unavailable: {exc}"], []
        return [], [f"PyQt6 runtime unavailable; forward-compatibility check deferred: {exc}"]

    errors = validate_runtime(runtime, policy, target_version, require_target=require_target)
    if errors:
        return errors, []

    if run_widget_smoke:
        try:
            run_qt_widget_smoke()
        except (ImportError, RuntimeError) as exc:
            return [f"PyQt6 QtWidgets startup smoke failed: {exc}"], []

    binding = parse_version(runtime.binding_version, label="PyQt6 binding version")
    qt = parse_version(runtime.qt_version, label="Qt runtime version")
    if binding >= target_version and qt >= target_version:
        message = (
            f"PyQt6 {runtime.distribution_version} and Qt {runtime.qt_version} "
            f"satisfy the {format_version(target_version)} target"
        )
    else:
        message = (
            f"PyQt6 {runtime.distribution_version} and Qt {runtime.qt_version} "
            f"satisfy the {format_version(policy.minimum_version)} minimum; "
            f"{format_version(target_version)} target validation is deferred until that upstream runtime is available"
        )
    return [], [message]


def validate_runtime(
    runtime: PyQt6Runtime,
    policy: PyQt6Policy,
    target_version: Version,
    *,
    require_target: bool,
) -> list[str]:
    errors = validate_target_version(policy, target_version)
    if errors:
        return errors
    try:
        distribution = parse_version(runtime.distribution_version, label="PyQt6 distribution version")
        binding = parse_version(runtime.binding_version, label="PyQt6 binding version")
        qt_distribution = parse_version(
            runtime.qt_distribution_version, label="PyQt6-Qt6 distribution version"
        )
        qt = parse_version(runtime.qt_version, label="Qt runtime version")
        parse_version(runtime.sip_distribution_version, label="PyQt6-sip distribution version")
    except ValueError as exc:
        return [str(exc)]

    if distribution[:2] != binding[:2]:
        errors.append(
            "PyQt6 distribution and imported binding major/minor versions do not match: "
            f"{runtime.distribution_version} vs {runtime.binding_version}"
        )
    if qt_distribution[:2] != qt[:2]:
        errors.append(
            "PyQt6-Qt6 distribution and imported Qt major/minor versions do not match: "
            f"{runtime.qt_distribution_version} vs {runtime.qt_version}"
        )
    if binding[:2] != qt[:2]:
        errors.append(
            "PyQt6 binding and bundled Qt runtime major/minor versions do not match: "
            f"{runtime.binding_version} vs {runtime.qt_version}"
        )
    for label, version in (
        ("PyQt6", distribution),
        ("PyQt6 binding", binding),
        ("PyQt6-Qt6", qt_distribution),
        ("Qt runtime", qt),
    ):
        if version < policy.minimum_version:
            errors.append(
                f"{label} {format_version(version)} is below the supported minimum "
                f"{format_version(policy.minimum_version)}"
            )
        if version >= policy.maximum_version_exclusive:
            errors.append(
                f"{label} {format_version(version)} is outside the supported PyQt6 6.x range"
            )

    target_versions = {
        "PyQt6 distribution": distribution,
        "PyQt6 binding": binding,
        "PyQt6-Qt6 distribution": qt_distribution,
        "Qt runtime": qt,
    }
    newer_target_line = {
        label: format_version(version)
        for label, version in target_versions.items()
        if version[:2] > target_version[:2]
    }
    if newer_target_line:
        installed = ", ".join(
            f"{label}={version}" for label, version in newer_target_line.items()
        )
        errors.append(
            f"PyQt6 target {format_version(target_version)} cannot be certified because "
            f"the installed runtime is newer than that target line: {installed}"
        )

    target_ready = {label: version >= target_version for label, version in target_versions.items()}
    target_is_partial = any(target_ready.values()) and not all(target_ready.values())
    if target_is_partial:
        if require_target:
            below_target = [label for label, ready in target_ready.items() if not ready]
            errors.append(
                f"PyQt6 target {format_version(target_version)} requires the PyQt6 and Qt "
                "distributions plus imported runtimes to meet that version; below target: "
                + ", ".join(below_target)
            )
        else:
            errors.append(
                f"PyQt6 target {format_version(target_version)} requires the binding and Qt "
                f"runtime to advance together; installed binding={runtime.binding_version}, "
                f"Qt={runtime.qt_version}"
            )
    elif require_target and not all(target_ready.values()):
        errors.append(
            f"PyQt6 target {format_version(target_version)} requires the PyQt6 and Qt "
            "distributions plus imported runtimes to meet that version; "
            f"installed PyQt6={runtime.distribution_version}, "
            f"binding={runtime.binding_version}, PyQt6-Qt6={runtime.qt_distribution_version}, "
            f"Qt={runtime.qt_version}"
        )
    return errors


def validate_target_version(policy: PyQt6Policy, target_version: Version) -> list[str]:
    if not policy.minimum_version <= target_version < policy.maximum_version_exclusive:
        return [
            f"PyQt6 target {format_version(target_version)} must be within the supported "
            f"range {format_version(policy.minimum_version)} <= target < "
            f"{format_version(policy.maximum_version_exclusive)}"
        ]
    return []


def configure_qt_environment() -> None:
    if sys.platform != "win32":
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def run_qt_widget_smoke() -> None:
    try:
        from PyQt6.QtWidgets import QApplication, QLabel
    except (ImportError, OSError) as exc:
        raise RuntimeError(f"QtWidgets could not be imported: {exc}") from exc

    application = QApplication.instance()
    owns_application = application is None
    if application is None:
        application = QApplication([])
    label = QLabel("PyQt6 compatibility smoke")
    try:
        label.resize(320, 80)
        label.show()
        application.processEvents()
        if not label.isVisible():
            raise RuntimeError("QLabel did not become visible")
        if label.grab().isNull():
            raise RuntimeError("QLabel did not produce a painted image")
    finally:
        label.close()
        application.processEvents()
        if owns_application:
            application.quit()


def format_version(version: Version) -> str:
    return ".".join(str(part) for part in version)


if __name__ == "__main__":
    raise SystemExit(main())
