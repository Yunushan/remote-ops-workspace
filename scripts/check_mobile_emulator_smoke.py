from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

DEFAULT_IOS_OPEN_URL_ATTEMPTS = 3
DEFAULT_IOS_OPEN_URL_RETRY_DELAY_SECONDS = 10.0
DEFAULT_ANDROID_WEB_RESPONSE_ATTEMPTS = 3
DEFAULT_ANDROID_WEB_RESPONSE_RETRY_DELAY_SECONDS = 2.0
DEFAULT_WEB_READY_TIMEOUT_SECONDS = 30.0
HTTP_OK_MARKER = "HTTP/1.0 200 OK"
ANDROID_WEB_REQUEST_PATH = "/data/local/tmp/row-web-pwa-request.txt"
ANDROID_WEB_RESPONSE_PATH = "/data/local/tmp/row-web-pwa-response.txt"
WEB_PWA_RESPONSE_MARKER = "<title>Remote Ops Workspace</title>"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Smoke-test the mobile Web/PWA on an emulator or simulator.")
    parser.add_argument("--platform", choices=("android", "ios"), required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--android-api", type=int)
    parser.add_argument(
        "--skip-web-response",
        action="store_true",
        help="Capture Android emulator boot evidence without fetching the Web/PWA response.",
    )
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
        return check_android(
            api_level=args.android_api,
            url=args.url,
            out_dir=out_dir,
            verify_web_response=not args.skip_web_response,
        )
    return check_ios(url=args.url, out_dir=out_dir, open_url_attempts=args.ios_open_url_attempts)


def check_android(
    *,
    api_level: int,
    url: str,
    out_dir: Path,
    verify_web_response: bool = True,
) -> int:
    require_tool("adb")
    actual_api = run(["adb", "shell", "getprop", "ro.build.version.sdk"]).stdout.strip()
    if actual_api != str(api_level):
        raise SystemExit(f"Android emulator API mismatch: expected {api_level}, got {actual_api!r}")

    if verify_web_response:
        wait_for_web_url(url)
        ensure_android_web_response(url)
    run(["adb", "shell", "input", "keyevent", "82"], check=False)
    time.sleep(5)

    screenshot = run(["adb", "exec-out", "screencap", "-p"], text=False).stdout
    if not screenshot:
        raise SystemExit("Android emulator screenshot was empty")
    target = out_dir / f"android-api-{api_level}-web-pwa.png"
    target.write_bytes(screenshot)
    mode = "Web/PWA network" if verify_web_response else "boot screenshot"
    print(f"Android API {api_level} {mode} smoke passed: {target}")
    return 0


def ensure_android_web_response(
    url: str,
    *,
    attempts: int = DEFAULT_ANDROID_WEB_RESPONSE_ATTEMPTS,
    retry_delay_seconds: float = DEFAULT_ANDROID_WEB_RESPONSE_RETRY_DELAY_SECONDS,
) -> None:
    if attempts < 1:
        raise SystemExit("Android Web/PWA response attempts must be at least 1")
    parsed = urlsplit(url)
    if parsed.scheme != "http" or not parsed.hostname:
        raise SystemExit(f"Android Web/PWA network smoke requires an HTTP URL, got {url!r}")
    if parsed.hostname != "127.0.0.1":
        raise SystemExit("Android Web/PWA network smoke requires adb-reversed emulator loopback")
    port = parsed.port or 80
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    host_header = parsed.netloc
    request = (
        f"GET {path} HTTP/1.0\r\n"
        f"Host: {host_header}\r\n"
        "Connection: close\r\n\r\n"
    )
    request_result: subprocess.CompletedProcess[str] | subprocess.CompletedProcess[bytes] | None = None
    response_result: subprocess.CompletedProcess[str] | subprocess.CompletedProcess[bytes] | None = None
    response = ""
    with tempfile.TemporaryDirectory(prefix="row-android-web-") as temp_dir:
        request_path = Path(temp_dir) / "request.txt"
        request_path.write_bytes(request.encode("ascii"))
        run(["adb", "push", str(request_path), ANDROID_WEB_REQUEST_PATH])
        try:
            for attempt in range(1, attempts + 1):
                run(["adb", "shell", "rm", "-f", ANDROID_WEB_RESPONSE_PATH], check=False)
                request_result = run(
                    [
                        "adb",
                        "shell",
                        f"(cat {ANDROID_WEB_REQUEST_PATH}; sleep 1) | toybox nc -w 10 127.0.0.1 {port} "
                        f"> {ANDROID_WEB_RESPONSE_PATH}",
                    ],
                    check=False,
                )
                response_result = run(
                    ["adb", "exec-out", "cat", ANDROID_WEB_RESPONSE_PATH],
                    check=False,
                )
                response = (
                    response_result.stdout
                    if isinstance(response_result.stdout, str)
                    else response_result.stdout.decode(errors="replace")
                )
                if (
                    request_result.returncode == 0
                    and response_result.returncode == 0
                    and HTTP_OK_MARKER in response
                    and WEB_PWA_RESPONSE_MARKER in response
                ):
                    print(f"Android Web/PWA response verified through emulator: {url}")
                    return
                if attempt < attempts:
                    time.sleep(retry_delay_seconds)
        finally:
            run(
                ["adb", "shell", "rm", "-f", ANDROID_WEB_REQUEST_PATH, ANDROID_WEB_RESPONSE_PATH],
                check=False,
            )

    assert request_result is not None
    assert response_result is not None
    stderr = (
        request_result.stderr.strip()
        if isinstance(request_result.stderr, str)
        else request_result.stderr.decode(errors="replace").strip()
    )
    preview = response[:500].replace("\r", "\\r").replace("\n", "\\n")
    raise SystemExit(
        "Android emulator could not verify the Web/PWA response "
        f"at {url!r} after {attempts} attempts; request_exit={request_result.returncode}; "
        f"response_exit={response_result.returncode}; stderr={stderr!r}; response={preview!r}"
    )


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
