from __future__ import annotations

import configparser
import json
import shlex
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

from . import command_safety as safe
from .models import Profile
from .storage import ProfileStore


SUPPORTED_IMPORT_FORMATS = {"auto", "row", "remmina", "mremoteng", "termius", "mobaxterm"}


@dataclass(slots=True)
class ProfileImportResult:
    source_format: str
    profiles: list[Profile]
    warnings: list[str] = field(default_factory=list)


def import_profiles(
    path: Path,
    source_format: str = "auto",
) -> ProfileImportResult:
    source_format = source_format.lower()
    if source_format not in SUPPORTED_IMPORT_FORMATS:
        raise ValueError(f"unsupported import format: {source_format}")
    if not path.exists():
        raise ValueError(f"import path does not exist: {path}")
    resolved_format = detect_import_format(path) if source_format == "auto" else source_format
    if resolved_format == "row":
        result = _load_row_bundle(path)
    elif resolved_format == "remmina":
        result = _load_remmina(path)
    elif resolved_format == "mremoteng":
        result = _load_mremoteng(path)
    elif resolved_format == "termius":
        result = _load_termius(path)
    elif resolved_format == "mobaxterm":
        result = _load_mobaxterm(path)
    else:
        raise ValueError(f"unsupported import format: {resolved_format}")
    if not result.profiles:
        raise ValueError(f"no profiles found in {path}")
    return result


def import_profiles_into_store(
    path: Path,
    store: ProfileStore | None = None,
    *,
    source_format: str = "auto",
    replace: bool = False,
) -> ProfileImportResult:
    result = import_profiles(path, source_format=source_format)
    target = store or ProfileStore()
    for profile in result.profiles:
        target.add(profile, replace=replace)
    return result


def detect_import_format(path: Path) -> str:
    if path.is_dir():
        if list(path.glob("*.remmina")):
            return "remmina"
        if list(path.glob("*.mxtsessions")) or (path / "MobaXterm.ini").exists():
            return "mobaxterm"
        raise ValueError(f"cannot auto-detect import format for directory: {path}")

    suffix = path.suffix.lower()
    if suffix == ".remmina":
        return "remmina"
    if suffix == ".xml":
        return "mremoteng"
    if suffix in {".mxtsessions", ".ini"}:
        text = _read_text(path)
        if "[bookmarks" in text.lower() or "mobaxterm" in text.lower():
            return "mobaxterm"
    if suffix == ".json":
        data = json.loads(_read_text(path))
        if isinstance(data, dict) and isinstance(data.get("profiles"), list):
            return "row"
        return "termius"

    text = _read_text(path)
    stripped = text.lstrip()
    if stripped.startswith("{") or stripped.startswith("["):
        data = json.loads(text)
        if isinstance(data, dict) and isinstance(data.get("profiles"), list):
            return "row"
        return "termius"
    if stripped.startswith("<"):
        return "mremoteng"
    if "[remmina]" in text.lower():
        return "remmina"
    if "[bookmarks" in text.lower():
        return "mobaxterm"
    raise ValueError(f"cannot auto-detect import format for file: {path}")


def _load_row_bundle(path: Path) -> ProfileImportResult:
    data = json.loads(_read_text(path))
    profiles = [Profile.from_dict(item) for item in data.get("profiles", [])]
    return ProfileImportResult(source_format="row", profiles=_dedupe_profiles(profiles))


def _load_remmina(path: Path) -> ProfileImportResult:
    files = sorted(path.glob("*.remmina")) if path.is_dir() else [path]
    profiles: list[Profile] = []
    warnings: list[str] = []
    for file in files:
        data = _read_remmina_file(file)
        if not data:
            continue
        name = data.get("name") or file.stem
        protocol = _map_protocol(data.get("protocol") or data.get("plugin") or "ssh", default="ssh")
        host, port = _server_and_port(data.get("server") or data.get("ssh_server") or data.get("host"), protocol)
        url = data.get("url") if protocol in {"http", "https"} else None
        if not host and url:
            host = urlparse(url).hostname
        options = _remmina_options(protocol, data)
        description = data.get("notes") or data.get("description") or "Imported from Remmina."
        profile = _profile(
            name=name,
            protocol=protocol,
            host=host,
            port=port,
            username=data.get("username") or data.get("user"),
            group=data.get("group") or "imported/remmina",
            description=description,
            url=url,
            options=options,
            tags=["imported", "remmina"],
        )
        profiles.append(profile)
        _warn_if_secret_fields(data, warnings, f"Remmina profile {profile.name}")
    return ProfileImportResult(source_format="remmina", profiles=_dedupe_profiles(profiles), warnings=warnings)


def _load_mremoteng(path: Path) -> ProfileImportResult:
    root = ET.fromstring(_read_text(path))
    profiles: list[Profile] = []
    warnings: list[str] = []

    def walk(element: ET.Element, groups: list[str]) -> None:
        attrs = _attrs(element)
        if _local_name(element.tag).lower() == "node":
            node_type = attrs.get("type", "").lower()
            name = attrs.get("name") or attrs.get("displayname") or "imported"
            if node_type in {"container", "folder"}:
                next_groups = [*groups, name]
                for child in element:
                    walk(child, next_groups)
                return
            protocol_raw = attrs.get("protocol")
            host = attrs.get("hostname") or attrs.get("host") or attrs.get("address")
            if protocol_raw and host:
                protocol = _map_protocol(protocol_raw, default="ssh")
                port = _int_or_none(attrs.get("port"))
                options: dict[str, str] = {}
                domain = attrs.get("domain")
                if domain and protocol == "rdp":
                    options["domain"] = safe.clean_text(domain, "mRemoteNG domain")
                profile = _profile(
                    name=name,
                    protocol=protocol,
                    host=host,
                    port=port,
                    username=attrs.get("username") or attrs.get("user"),
                    group="/".join(groups) if groups else "imported/mremoteng",
                    description=attrs.get("description") or "Imported from mRemoteNG.",
                    options=options,
                    tags=["imported", "mremoteng"],
                )
                profiles.append(profile)
                _warn_if_secret_fields(attrs, warnings, f"mRemoteNG profile {profile.name}")
                return
        for child in element:
            walk(child, groups)

    walk(root, [])
    return ProfileImportResult(source_format="mremoteng", profiles=_dedupe_profiles(profiles), warnings=warnings)


def _load_termius(path: Path) -> ProfileImportResult:
    data = json.loads(_read_text(path))
    profiles: list[Profile] = []
    warnings: list[str] = []
    for item in _iter_host_dicts(data):
        protocol = _map_protocol(_first(item, "protocol", "type", "service") or "ssh", default="ssh")
        host = _first(item, "address", "hostname", "host", "ip")
        if not host:
            continue
        name = _first(item, "label", "name", "title", "alias") or host
        options: dict[str, str] = {}
        if protocol == "mosh":
            mosh_port = _first(item, "mosh_port", "moshPorts")
            if mosh_port:
                options["mosh_port"] = safe.clean_text(mosh_port, "Termius mosh_port")
        identity_file = _first(item, "identity_file", "identityFile", "key_path", "keyPath")
        group = _group_from_json(item) or "imported/termius"
        tags = ["imported", "termius", *_json_tags(item)]
        profile = _profile(
            name=name,
            protocol=protocol,
            host=host,
            port=_int_or_none(_first(item, "port")),
            username=_first(item, "username", "user", "login"),
            group=group,
            description=_first(item, "description", "notes") or "Imported from Termius-style JSON.",
            identity_file=identity_file,
            options=options,
            tags=tags,
        )
        profiles.append(profile)
        _warn_if_secret_fields(item, warnings, f"Termius profile {profile.name}")
    return ProfileImportResult(source_format="termius", profiles=_dedupe_profiles(profiles), warnings=warnings)


def _load_mobaxterm(path: Path) -> ProfileImportResult:
    files = _mobaxterm_files(path)
    profiles: list[Profile] = []
    warnings: list[str] = []
    for file in files:
        parser = _parse_ini_like(_read_text(file), default_section="Bookmarks")
        for section in parser.sections():
            if not section.lower().startswith("bookmarks"):
                continue
            group = parser.get(section, "SubRep", fallback="") or "imported/mobaxterm"
            for name, value in parser.items(section):
                if name.lower().startswith("subrep") or not value.strip():
                    continue
                profile = _mobaxterm_profile(name, value, group)
                if profile:
                    profiles.append(profile)
                elif _has_secret_field(name) or _has_secret_field(value):
                    warnings.append(f"MobaXterm entry {name}: skipped secret-like field")
    return ProfileImportResult(source_format="mobaxterm", profiles=_dedupe_profiles(profiles), warnings=warnings)


def _read_remmina_file(path: Path) -> dict[str, str]:
    parser = _parse_ini_like(_read_text(path), default_section="remmina")
    section = "remmina" if parser.has_section("remmina") else parser.sections()[0] if parser.sections() else ""
    if not section:
        return {}
    return {key.lower(): value for key, value in parser.items(section)}


def _parse_ini_like(text: str, *, default_section: str) -> configparser.ConfigParser:
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.optionxform = str
    content = text if text.lstrip().startswith("[") else f"[{default_section}]\n{text}"
    parser.read_string(content)
    return parser


def _remmina_options(protocol: str, data: dict[str, str]) -> dict[str, str]:
    options: dict[str, str] = {}
    resolution = data.get("resolution")
    if resolution and resolution.lower() not in {"default", "use client resolution"}:
        options["geometry"] = safe.clean_text(resolution, "Remmina resolution")
    if protocol == "rdp":
        domain = data.get("domain")
        if domain:
            options["domain"] = safe.clean_text(domain, "Remmina domain")
        if _truthy(data.get("ignore-cert") or data.get("ignore_certificate")):
            options["cert_ignore"] = "true"
        if _truthy(data.get("disableclipboard")):
            options["clipboard"] = "false"
        if _truthy(data.get("sharefolder")) and data.get("sharefolder_name") and data.get("sharefolder_path"):
            options["drive"] = f"{data['sharefolder_name']},{data['sharefolder_path']}"
    if protocol == "vnc":
        if _truthy(data.get("viewonly")):
            options["view_only"] = "true"
        for key in ("quality", "compression"):
            if data.get(key):
                options[key] = safe.clean_text(data[key], f"Remmina {key}")
    if protocol == "ssh" and data.get("ssh_tunnel_server"):
        host, _port = _server_and_port(data["ssh_tunnel_server"], "ssh")
        if host:
            options["proxy_jump"] = host
    return options


def _mobaxterm_files(path: Path) -> list[Path]:
    if path.is_dir():
        files = sorted(path.glob("*.mxtsessions"))
        ini = path / "MobaXterm.ini"
        if ini.exists():
            files.append(ini)
        return files
    return [path]


def _mobaxterm_profile(name: str, value: str, group: str) -> Profile | None:
    command_profile = _command_like_profile(name, value, group, "mobaxterm")
    if command_profile:
        return command_profile
    if "%" not in value:
        return None
    fields = [field.strip() for field in value.split("%")]
    if len(fields) < 3:
        return None
    protocol = _mobaxterm_protocol(name, fields[0])
    host_index = _first_host_index(fields)
    if host_index is None:
        return None
    host = fields[host_index]
    port = _int_or_none(fields[host_index + 1] if host_index + 1 < len(fields) else None)
    username = fields[host_index + 2] if host_index + 2 < len(fields) and fields[host_index + 2] else None
    return _profile(
        name=name,
        protocol=protocol,
        host=host,
        port=port,
        username=username,
        group=group or "imported/mobaxterm",
        description="Imported from MobaXterm session export.",
        tags=["imported", "mobaxterm"],
    )


def _command_like_profile(name: str, value: str, group: str, source: str) -> Profile | None:
    try:
        parts = shlex.split(value)
    except ValueError:
        return None
    if not parts:
        return None
    protocol = _map_protocol(parts[0], default="")
    if not protocol:
        return None
    if protocol == "ssh":
        return _ssh_command_profile(name, parts[1:], group, source)
    target = parts[1] if len(parts) > 1 else ""
    if "://" in target:
        parsed = urlparse(target)
        host = parsed.hostname
        port = parsed.port
    else:
        host, port = _server_and_port(target, protocol)
    if not host:
        return None
    return _profile(
        name=name,
        protocol=protocol,
        host=host,
        port=port,
        group=group or f"imported/{source}",
        description=f"Imported from {source} command entry.",
        tags=["imported", source],
    )


def _ssh_command_profile(name: str, parts: list[str], group: str, source: str) -> Profile | None:
    port: int | None = None
    username: str | None = None
    host: str | None = None
    identity_file: str | None = None
    index = 0
    while index < len(parts):
        part = parts[index]
        if part == "-p" and index + 1 < len(parts):
            port = _int_or_none(parts[index + 1])
            index += 2
            continue
        if part == "-i" and index + 1 < len(parts):
            identity_file = parts[index + 1]
            index += 2
            continue
        if not part.startswith("-"):
            target = part
            if "@" in target:
                username, host = target.split("@", 1)
            else:
                host = target
            break
        index += 1
    if not host:
        return None
    return _profile(
        name=name,
        protocol="ssh",
        host=host,
        port=port,
        username=username,
        group=group or f"imported/{source}",
        description=f"Imported from {source} SSH command entry.",
        identity_file=identity_file,
        tags=["imported", source],
    )


def _iter_host_dicts(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, list):
        for item in value:
            yield from _iter_host_dicts(item)
        return
    if not isinstance(value, dict):
        return
    if _looks_like_host_dict(value):
        yield value
    for key, item in value.items():
        if key.lower() in {"credentials", "credential", "password", "secrets"}:
            continue
        if isinstance(item, (dict, list)):
            yield from _iter_host_dicts(item)


def _looks_like_host_dict(value: dict[str, Any]) -> bool:
    keys = {str(key).lower() for key in value}
    return bool(keys & {"address", "hostname", "host", "ip"}) and bool(keys & {"label", "name", "title", "alias"})


def _group_from_json(item: dict[str, Any]) -> str | None:
    group = _first(item, "group", "folder", "folderName", "groupLabel")
    if isinstance(group, dict):
        return _first(group, "label", "name", "title")
    if group:
        return safe.clean_text(group, "JSON group")
    return None


def _json_tags(item: dict[str, Any]) -> list[str]:
    raw = item.get("tags") or item.get("labels") or []
    if isinstance(raw, str):
        return [safe.clean_text(raw, "JSON tag")]
    if isinstance(raw, list):
        return [safe.clean_text(str(tag), "JSON tag") for tag in raw if str(tag)]
    return []


def _profile(
    *,
    name: str,
    protocol: str,
    host: str | None = None,
    port: int | None = None,
    username: str | None = None,
    group: str = "imported",
    description: str = "",
    url: str | None = None,
    identity_file: str | None = None,
    options: dict[str, str] | None = None,
    tags: list[str] | None = None,
) -> Profile:
    clean_host = _clean_host(host, protocol)
    clean_port = safe.port(port, f"{protocol} port") if port is not None else None
    return Profile(
        name=_profile_name(name),
        protocol=protocol,
        host=clean_host,
        port=clean_port,
        username=_clean_optional(username, "username"),
        group=_clean_group(group),
        tags=_dedupe_strings(tags or []),
        description=safe.clean_text(description, "description", allow_empty=True),
        url=safe.url(url) if url else None,
        identity_file=safe.path_arg(identity_file, "identity file") if identity_file else None,
        options={str(key): safe.clean_text(str(value), f"option {key}") for key, value in (options or {}).items()},
    )


def _server_and_port(value: str | None, protocol: str) -> tuple[str | None, int | None]:
    if not value:
        return None, None
    text = safe.clean_text(value, "server").strip()
    if "://" in text:
        parsed = urlparse(text)
        return parsed.hostname, parsed.port
    if text.startswith("[") and "]" in text:
        host, _, rest = text[1:].partition("]")
        port = _int_or_none(rest[1:] if rest.startswith(":") else None)
        return host, port
    if ":" in text and text.count(":") == 1:
        host, port_text = text.rsplit(":", 1)
        port = _int_or_none(port_text)
        if port is not None:
            return host, port
    return text, None


def _map_protocol(value: str | None, *, default: str) -> str:
    if not value:
        return default
    normalized = str(value).strip().lower().replace("_", "").replace("-", "")
    mapping = {
        "browser": "https",
        "citrix": "ica",
        "ftp": "ftp",
        "http": "http",
        "https": "https",
        "ica": "ica",
        "mosh": "mosh",
        "nx": "x2go",
        "raw": "raw",
        "rdp": "rdp",
        "rlogin": "rlogin",
        "rsh": "rsh",
        "serial": "serial",
        "sftp": "sftp",
        "spice": "spice",
        "ssh": "ssh",
        "ssh1": "ssh",
        "ssh2": "ssh",
        "telnet": "telnet",
        "vnc": "vnc",
        "www": "https",
        "xdmcp": "xdmcp",
        "x2go": "x2go",
    }
    return mapping.get(normalized, default)


def _mobaxterm_protocol(name: str, marker: str) -> str:
    text = f"{name} {marker}".lower()
    if "rdp" in text:
        return "rdp"
    if "vnc" in text:
        return "vnc"
    if "telnet" in text:
        return "telnet"
    if "ftp" in text:
        return "ftp"
    return "ssh"


def _first_host_index(fields: list[str]) -> int | None:
    for index, field in enumerate(fields):
        if not field or field.startswith("#") or field.startswith("-"):
            continue
        if _int_or_none(field) is not None:
            continue
        if "." in field or ":" in field or field.lower() == "localhost" or any(char.isalpha() for char in field):
            return index
    return None


def _clean_host(value: str | None, protocol: str) -> str | None:
    if not value:
        return None
    if protocol == "serial":
        return None
    return safe.host(value, f"{protocol} host")


def _clean_optional(value: Any, label: str) -> str | None:
    if value in (None, ""):
        return None
    return safe.option_value(str(value), label)


def _clean_group(value: str) -> str:
    group = safe.clean_text(value or "imported", "group").strip()
    return group.replace("\\", "/") or "imported"


def _profile_name(value: str) -> str:
    name = safe.clean_text(value, "profile name").strip()
    name = name.replace("/", "_").replace("\\", "_")
    return name or "imported"


def _dedupe_profiles(profiles: list[Profile]) -> list[Profile]:
    counts: dict[str, int] = {}
    result: list[Profile] = []
    for profile in profiles:
        count = counts.get(profile.name, 0)
        counts[profile.name] = count + 1
        if count == 0:
            result.append(profile)
            continue
        data = profile.to_dict()
        data["name"] = f"{profile.name}-{count + 1}"
        result.append(Profile.from_dict(data))
    return result


def _dedupe_strings(items: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = safe.clean_text(item, "tag").strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _attrs(element: ET.Element) -> dict[str, str]:
    return {str(key).lower(): str(value) for key, value in element.attrib.items()}


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _first(item: dict[str, Any], *keys: str) -> Any:
    lower = {str(key).lower(): value for key, value in item.items()}
    for key in keys:
        value = lower.get(key.lower())
        if value not in (None, ""):
            return value
    credentials = lower.get("credentials") or lower.get("credential")
    if isinstance(credentials, dict):
        return _first(credentials, *keys)
    return None


def _int_or_none(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(str(value))
    except ValueError:
        return None


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _warn_if_secret_fields(data: dict[str, Any], warnings: list[str], context: str) -> None:
    if any(_has_secret_field(key) and value not in (None, "") for key, value in data.items()):
        warnings.append(f"{context}: password/passphrase fields were not imported")


def _has_secret_field(value: Any) -> bool:
    text = str(value).lower()
    return any(token in text for token in ("password", "passphrase", "secret"))


def _read_text(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-16", "cp1252"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeError:
            continue
    return path.read_text(encoding="utf-8", errors="replace")
