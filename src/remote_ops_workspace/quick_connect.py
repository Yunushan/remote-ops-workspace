from __future__ import annotations

import re
from dataclasses import dataclass
from operator import itemgetter
from urllib.parse import urlparse

from .models import Profile

QUICK_CONNECT_PROTOCOLS = {
    "ssh",
    "sftp",
    "scp",
    "rdp",
    "vnc",
    "telnet",
    "ftp",
    "http",
    "https",
    "mosh",
    "x2go",
    "spice",
    "raw",
}
QUICK_CONNECT_DEFAULT_PORTS = {
    "ssh": 22,
    "sftp": 22,
    "scp": 22,
    "rdp": 3389,
    "vnc": 5900,
    "telnet": 23,
    "ftp": 21,
    "mosh": 22,
    "raw": None,
}


@dataclass(frozen=True)
class QuickConnectCandidate:
    kind: str
    label: str
    detail: str
    profile_name: str | None = None
    profile: Profile | None = None


def quick_connect_candidates(
    text: str, profiles: list[Profile], *, limit: int = 6
) -> list[QuickConnectCandidate]:
    query = text.strip()
    if not query:
        return []

    direct = parse_quick_connect_profile(query)
    direct_is_explicit = direct is not None and quick_connect_is_explicit(query)
    matches = profile_quick_connect_matches(query, profiles, limit=limit)
    candidates: list[QuickConnectCandidate] = []
    if direct is not None and direct_is_explicit:
        candidates.append(direct)
    candidates.extend(matches)
    if direct is not None and not direct_is_explicit:
        candidates.append(direct)

    unique: list[QuickConnectCandidate] = []
    seen: set[tuple[str, str]] = set()
    for candidate in candidates:
        key = (candidate.kind, candidate.profile_name or candidate.label)
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
        if len(unique) >= limit:
            break
    return unique


def profile_quick_connect_matches(
    query: str, profiles: list[Profile], *, limit: int
) -> list[QuickConnectCandidate]:
    normalized = query.lower()
    scored: list[tuple[int, str, Profile]] = []
    for profile in profiles:
        fields = [
            profile.name,
            profile.group,
            profile.protocol,
            profile.display_target,
            *profile.tags,
        ]
        haystack = " ".join(str(field) for field in fields if field).lower()
        if normalized not in haystack:
            continue
        score = 30
        if profile.name.lower() == normalized:
            score = 0
        elif profile.name.lower().startswith(normalized):
            score = 5
        elif profile.display_target.lower().startswith(normalized):
            score = 10
        elif profile.group.lower().startswith(normalized):
            score = 20
        scored.append((score, profile.name.lower(), profile))
    return [
        QuickConnectCandidate(
            kind="profile",
            label=f"{profile.protocol.upper()}  {profile.name}",
            detail=profile.display_target,
            profile_name=profile.name,
        )
        for _score, _name, profile in sorted(scored, key=itemgetter(0, 1))[:limit]
    ]


def parse_quick_connect_profile(text: str) -> QuickConnectCandidate | None:
    query = text.strip()
    if not query:
        return None
    if looks_like_url(query):
        return quick_connect_url_candidate(query)
    try:
        parsed_uri = urlparse(query)
    except ValueError:
        return None
    if parsed_uri.scheme.lower() in QUICK_CONNECT_PROTOCOLS and parsed_uri.netloc:
        try:
            parsed_port = parsed_uri.port
        except ValueError:
            return None
        return quick_connect_parsed_endpoint_candidate(
            parsed_uri.scheme.lower(),
            parsed_uri.hostname,
            parsed_port,
            parsed_uri.username,
        )

    parts = query.split(maxsplit=1)
    protocol = "ssh"
    target = query
    if len(parts) == 2 and parts[0].lower() in QUICK_CONNECT_PROTOCOLS:
        protocol = parts[0].lower()
        target = parts[1].strip()
    elif not quick_connect_is_host_like(query):
        return None

    if protocol in {"http", "https"}:
        url = target if looks_like_url(target) else f"{protocol}://{target}"
        return quick_connect_url_candidate(url)

    endpoint = parse_quick_connect_endpoint(target)
    if endpoint is None:
        return None
    host, port, username = endpoint
    return quick_connect_parsed_endpoint_candidate(protocol, host, port, username)


def quick_connect_parsed_endpoint_candidate(
    protocol: str,
    host: str | None,
    port: int | None,
    username: str | None,
) -> QuickConnectCandidate | None:
    if not host:
        return None
    profile = Profile(
        name=quick_connect_profile_name(protocol, host),
        protocol=protocol,
        host=host,
        port=port or QUICK_CONNECT_DEFAULT_PORTS.get(protocol),
        username=username,
        group="quick-connect",
        tags=["quick-connect"],
    )
    return QuickConnectCandidate(
        kind="direct",
        label=f"DIRECT {protocol.upper()}  {profile.display_target}",
        detail="temporary quick-connect target",
        profile=profile,
    )


def quick_connect_url_candidate(url: str) -> QuickConnectCandidate | None:
    try:
        parsed = urlparse(url)
        port = parsed.port
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    if not parsed.hostname or port == 0:
        return None
    profile = Profile(
        name=quick_connect_profile_name(parsed.scheme, parsed.netloc),
        protocol=parsed.scheme,
        url=url,
        group="quick-connect",
        tags=["quick-connect"],
    )
    return QuickConnectCandidate(
        kind="direct",
        label=f"DIRECT {parsed.scheme.upper()}  {parsed.netloc}",
        detail=url,
        profile=profile,
    )


def parse_quick_connect_endpoint(target: str) -> tuple[str, int | None, str | None] | None:
    try:
        parsed = urlparse(f"//{target.strip()}")
        host = parsed.hostname
        port = parsed.port
    except ValueError:
        return None
    if not host:
        return None
    return host, port, parsed.username


def quick_connect_is_explicit(query: str) -> bool:
    first = query.split(maxsplit=1)[0].lower()
    return first in QUICK_CONNECT_PROTOCOLS or "://" in query


def quick_connect_is_host_like(query: str) -> bool:
    return bool(
        "@" in query
        or re.search(r":\d+$", query)
        or re.search(r"\d+\.\d+\.\d+\.\d+", query)
        or "." in query
    )


def looks_like_url(query: str) -> bool:
    return query.lower().startswith(("http://", "https://"))


def quick_connect_profile_name(protocol: str, target: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_.-]+", "-", target).strip("-") or "target"
    return f"quick-{protocol}-{slug}"[:80]
