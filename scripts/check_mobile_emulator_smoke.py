from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

DEFAULT_IOS_OPEN_URL_ATTEMPTS = 3
DEFAULT_IOS_OPEN_URL_RETRY_DELAY_SECONDS = 10.0
DEFAULT_WEB_READY_TIMEOUT_SECONDS = 30.0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Smoke-test the mobile Web/PWA on an emulator or simulator.")
    parser.add_argument("--platform", choices=("android", "ios"), required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--android-api", type=int)
    parser.add_argument(
        "--ios-open-url-attempts",
        type=int,
        default=DEFAULT_IOS_OPEN_URL_ATTEMPTS,
        help="Retry budget for first-boot iOS simulator URL opening.",
    )
    parser.add_argument("--out-dir", default="artifacts/mobile")
    args = parser.parse_args(argv)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if args.platform == "android":
        if args.android_api is None:
            raise SystemExit("--android-api is required for Android smoke")
        return check_android(api_level=args.android_api, url=args.url, out_dir=out_dir)
    return check_ios(url=args.url, out_dir=out_dir, open_url_attempts=args.ios_open_url_attempts)


def check_android(*, api_level: int, url: str, out_dir: Path) -> int:
    require_tool("adb")
    actual_api = run(["adb", "shell", "getprop", "ro.build.version.sdk"]).stdout.strip()
    if actual_api != str(api_level):
        raise SystemExit(f"Android emulator API mismatch: expected {api_level}, got {actual_api!r}")

    run(["adb", "shell", "input", "keyevent", "82"], check=False)
    run(["adb", "shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", url])
    time.sleep(5)

    screenshot = run(["adb", "exec-out", "screencap", "-p"], text=False).stdout
    if not screenshot:
        raise SystemExit("Android emulator screenshot was empty")
    target = out_dir / f"android-api-{api_level}-web-pwa.png"
    target.write_bytes(screenshot)
    print(f"Android API {api_level} Web/PWA smoke passed: {target}")
    return 0


def check_ios(*, url: str, out_dir: Path, open_url_attempts: int = DEFAULT_IOS_OPEN_URL_ATTEMPTS) -> int:
    require_tool("xcrun")
    wait_for_web_url(url)
    runtime = latest_ios_runtime()
    device_type = preferred_iphone_device_type()
    udid = run(["xcrun", "simctl", "create", "row-web-pwa", device_type, runtime["identifier"]]).stdout.strip()
    try:
        run(["xcrun", "simctl", "boot", udid], check=False)
        run(["xcrun", "simctl", "bootstatus", udid, "-b"])
        warm_ios_browser(udid)
        open_ios_url(udid, url, attempts=open_url_attempts)
        time.sleep(5)
        target = out_dir / "ios-simulator-web-pwa.png"
        run(["xcrun", "simctl", "io", udid, "screenshot", str(target)])
        if not target.exists() or target.stat().st_size == 0:
            raise SystemExit("iOS simulator screenshot was empty")
        print(f"iOS simulator Web/PWA smoke passed on {runtime['name']}: {target}")
        return 0
    finally:
        run(["xcrun", "simctl", "shutdown", udid], check=False)
        run(["xcrun", "simctl", "delete", udid], check=False)


def wait_for_web_url(url: str, timeout_seconds: float = DEFAULT_WEB_READY_TIMEOUT_SECONDS) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error = ""
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as response:
                if response.status < 500:
                    return
                last_error = f"HTTP {response.status}"
        except (OSError, urllib.error.URLError) as exc:
            last_error = str(exc)
        time.sleep(1)
    raise SystemExit(f"Web/PWA server did not become reachable at {url}: {last_error}")


def warm_ios_browser(udid: str) -> None:
    run(["xcrun", "simctl", "launch", udid, "com.apple.mobilesafari"], check=False)
    time.sleep(2)


def open_ios_url(
    udid: str,
    url: str,
    *,
    attempts: int = DEFAULT_IOS_OPEN_URL_ATTEMPTS,
    retry_delay_seconds: float = DEFAULT_IOS_OPEN_URL_RETRY_DELAY_SECONDS,
) -> None:
    if attempts < 1:
        raise SystemExit("--ios-open-url-attempts must be at least 1")
    last_error = ""
    for attempt in range(1, attempts + 1):
        result = run(["xcrun", "simctl", "openurl", udid, url], check=False)
        if result.returncode == 0:
            return
        last_error = result.stderr.strip()
        print(
            f"iOS simulator openurl attempt {attempt}/{attempts} failed: {last_error}",
            file=sys.stderr,
        )
        if attempt < attempts:
            run(["xcrun", "simctl", "bootstatus", udid, "-b"], check=False)
            warm_ios_browser(udid)
            time.sleep(retry_delay_seconds)
    raise SystemExit(f"iOS simulator failed to open {url} after {attempts} attempts: {last_error}")


def latest_ios_runtime() -> dict[str, Any]:
    result = run(["xcrun", "simctl", "list", "runtimes", "--json"])
    runtimes = json.loads(result.stdout).get("runtimes", [])
    ios_runtimes = [
        runtime
        for runtime in runtimes
        if runtime.get("isAvailable")
        and (
            "iOS" in str(runtime.get("name", ""))
            or "iOS" in str(runtime.get("identifier", ""))
        )
    ]
    if not ios_runtimes:
        raise SystemExit("No available iOS simulator runtime found")
    return max(ios_runtimes, key=lambda runtime: version_key(str(runtime.get("version", ""))))


def preferred_iphone_device_type() -> str:
    result = run(["xcrun", "simctl", "list", "devicetypes", "--json"])
    device_types = json.loads(result.stdout).get("devicetypes", [])
    identifiers = [str(item.get("identifier", "")) for item in device_types]
    preferred = (
        "com.apple.CoreSimulator.SimDeviceType.iPhone-16",
        "com.apple.CoreSimulator.SimDeviceType.iPhone-15",
        "com.apple.CoreSimulator.SimDeviceType.iPhone-14",
    )
    for identifier in preferred:
        if identifier in identifiers:
            return identifier
    for identifier in identifiers:
        if ".iPhone-" in identifier:
            return identifier
    raise SystemExit("No iPhone simulator device type found")


def version_key(value: str) -> tuple[int, ...]:
    parts: list[int] = []
    for raw in value.split("."):
        try:
            parts.append(int(raw))
        except ValueError:
            parts.append(0)
    return tuple(parts)


def require_tool(name: str) -> None:
    if shutil.which(name) is None:
        raise SystemExit(f"Required mobile smoke tool not found on PATH: {name}")


def run(
    args: list[str],
    *,
    check: bool = True,
    text: bool = True,
) -> subprocess.CompletedProcess[str] | subprocess.CompletedProcess[bytes]:
    result = subprocess.run(
        args,
        check=False,
        capture_output=True,
        text=text,
    )
    if check and result.returncode != 0:
        stderr = result.stderr.strip() if isinstance(result.stderr, str) else result.stderr.decode(errors="replace")
        raise SystemExit(f"{' '.join(args)} failed with exit {result.returncode}: {stderr}")
    return result


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
