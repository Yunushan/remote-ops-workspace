"""Bounded nonexecuting CfT acquisition and separately pinned root provisioning.

HTTPS origin evidence and locally observed hashes are not vendor signatures.
No network/filesystem/vendor process operation occurs at module import.
"""
import hashlib
import json
import os
import re
import ssl
import stat
import struct
import time
import unicodedata
import urllib.request
import zipfile
import zlib
from contextlib import contextmanager
from pathlib import Path

VERSION = '154.0.8037.92'
METADATA_URL = 'https://googlechromelabs.github.io/chrome-for-testing/154.0.8037.92.json'
ASSETS = ('chrome', 'chromedriver')
PLATFORM = 'linux64'
MAX_METADATA = 65536
MAX_ARCHIVE = 536870912
MAX_UNPACKED = 1073741824
MAX_ENTRIES = 4096
MAX_CENTRAL = 2097152
MAX_NAME = 512
MAX_PUBLIC = 2097152
CHUNK = 65536
ROOT_PARENT = Path('/opt')
EXECUTABLES = {'chrome': 'chrome-linux64/chrome', 'chromedriver': 'chromedriver-linux64/chromedriver'}


class BundleRefusal(ValueError):
    pass


def need(value, code='cft-contract-refused'):
    if not value:
        raise BundleRefusal(code)


def packed(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii')


def hashed(raw):
    return hashlib.sha256(raw).hexdigest()


def exact(value, keys):
    need(type(value) is dict and set(value) == set(keys))


def integer(value, maximum, minimum=0):
    need(type(value) is int and minimum <= value <= maximum)


def digest(value):
    need(type(value) is str and re.fullmatch(r'[0-9a-f]{64}', value) is not None)


def pairs(rows):
    result = {}
    for key, value in rows:
        need(key not in result, 'cft-json-duplicate-key')
        result[key] = value
    return result


def constant(_value):
    raise BundleRefusal('cft-json-nonfinite')


def decode(raw, maximum):
    need(type(raw) is bytes and 0 < len(raw) <= maximum)
    try:
        return json.loads(raw.decode('utf-8', errors='strict'), object_pairs_hook=pairs,
            parse_constant=constant)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise BundleRefusal('cft-json-refused') from exc


def asset_url(version, asset):
    need(type(version) is str and len(version) <= 48
         and re.fullmatch(r'(?:0|[1-9][0-9]{0,9})(?:\.(?:0|[1-9][0-9]{0,9})){3}', version) is not None)
    need(asset in ASSETS)
    return f'https://storage.googleapis.com/chrome-for-testing-public/{version}/linux64/{asset}-linux64.zip'


def policy(raw, *, enabled):
    value = decode(raw, MAX_METADATA)
    exact(value, {'schema', 'enabled', 'version', 'platform', 'metadata_url', 'metadata', 'archives',
        'origin_evidence', 'independent_vendor_signature', 'publisher_license_approval', 'sandbox_policy'})
    need(value['schema'] == 'row.cft-provider-policy.v1' and type(value['enabled']) is bool)
    need(value['enabled'] is enabled and value['version'] == VERSION and value['platform'] == PLATFORM)
    need(value['metadata_url'] == METADATA_URL
         and value['origin_evidence'] == 'certificate-and-hostname-verified-official-HTTPS'
         and value['independent_vendor_signature'] is False and value['publisher_license_approval'] is False
         and value['sandbox_policy'] == 'unchanged-default-no-fallback')
    exact(value['archives'], ASSETS)
    if enabled:
        exact(value['metadata'], {'bytes', 'sha256'})
        integer(value['metadata']['bytes'], MAX_METADATA, 1)
        digest(value['metadata']['sha256'])
        for asset in ASSETS:
            row = value['archives'][asset]
            exact(row, {'url', 'bytes', 'sha256', 'inventory_sha256', 'entries', 'files', 'unpacked_bytes'})
            need(row['url'] == asset_url(VERSION, asset))
            integer(row['bytes'], MAX_ARCHIVE, 22)
            integer(row['entries'], MAX_ENTRIES, 1)
            integer(row['files'], row['entries'], 1)
            integer(row['unpacked_bytes'], MAX_UNPACKED, 1)
            digest(row['sha256'])
            digest(row['inventory_sha256'])
    else:
        need(value['metadata'] is None and all(value['archives'][asset] is None for asset in ASSETS),
             'cft-disabled-policy-cannot-confer-pins')
    return value


def select_metadata(raw, expected_version):
    selected = decode(raw, MAX_METADATA)
    exact(selected, {'version', 'revision', 'downloads'})
    need(selected['version'] == expected_version == VERSION,
         'cft-exact-version-unavailable')
    need(type(selected['revision']) is str and re.fullmatch(r'[0-9]{1,16}', selected['revision']))
    downloads = selected['downloads']
    need(type(downloads) is dict and set(ASSETS).issubset(downloads)
         and set(downloads).issubset({'chrome', 'chromedriver', 'chrome-headless-shell', 'mojojs'}))
    result = {}
    for asset in ASSETS:
        rows = downloads[asset]
        need(type(rows) is list and 1 <= len(rows) <= 8)
        platforms = set()
        for row in rows:
            exact(row, {'platform', 'url'})
            need(type(row['platform']) is str and row['platform'] in
                 {'linux64', 'linux-arm64', 'mac-arm64', 'mac-x64', 'win32', 'win64'}
                 and row['platform'] not in platforms)
            platforms.add(row['platform'])
            need(type(row['url']) is str and len(row['url']) <= 256)
            if row['platform'] == PLATFORM:
                need(row['url'] == asset_url(expected_version, asset), 'cft-download-URL-refused')
                result[asset] = row['url']
        need(asset in result)
    return result


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        return None


def remaining(deadline):
    result = deadline - time.monotonic()
    need(result > 0, 'cft-deadline-refused')
    return min(20, result)


def fetch(url, destination, deadline, *, maximum, expected=None):
    need(url == METADATA_URL or url in {asset_url(VERSION, asset) for asset in ASSETS})
    need(not any(key.upper() in {'SSL_CERT_FILE', 'SSL_CERT_DIR', 'SSLKEYLOGFILE'} and value
                 for key, value in os.environ.items()), 'cft-TLS-environment-override-refused')
    context = ssl.create_default_context()
    need(context.check_hostname is True and context.verify_mode == ssl.CERT_REQUIRED,
         'cft-TLS-verification-refused')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect(),
        urllib.request.HTTPSHandler(context=context))
    request = urllib.request.Request(url, headers={'Accept-Encoding': 'identity'}, method='GET')
    digest_state = hashlib.sha256()
    received = 0
    try:
        with opener.open(request, timeout=remaining(deadline)) as response:
            need(response.status == 200 and response.geturl() == url, 'cft-response-origin-refused')
            need(response.headers.get('Content-Encoding') in (None, 'identity')
                 and response.headers.get('Transfer-Encoding') is None, 'cft-response-encoding-refused')
            length = response.headers.get('Content-Length', '')
            need(type(length) is str and re.fullmatch(r'[1-9][0-9]{0,9}', length), 'cft-response-length-refused')
            declared = int(length)
            integer(declared, maximum, 1)
            if expected is not None:
                need(declared == expected['bytes'], 'cft-pinned-response-length-refused')
            fd = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, 'wb') as stream:
                while True:
                    remaining(deadline)
                    chunk = response.read(min(CHUNK, declared - received + 1))
                    remaining(deadline)
                    need(type(chunk) is bytes and len(chunk) <= CHUNK)
                    if not chunk:
                        break
                    received += len(chunk)
                    need(received <= declared, 'cft-response-overlong')
                    stream.write(chunk)
                    digest_state.update(chunk)
                need(received == declared, 'cft-response-truncated')
                if expected is not None:
                    need(digest_state.hexdigest() == expected['sha256'], 'cft-pinned-archive-hash-refused')
                stream.flush()
                os.fsync(stream.fileno())
                os.fchmod(stream.fileno(), 0o400)
    except BundleRefusal:
        raise
    except Exception as exc:
        raise BundleRefusal('cft-transport-or-write-refused') from exc
    return {'bytes': received, 'sha256': digest_state.hexdigest()}


def member_name(raw, flags, asset):
    need(type(raw) is bytes and 1 <= len(raw) <= MAX_NAME and b'\0' not in raw)
    try:
        value = raw.decode('utf-8' if flags & 0x800 else 'ascii', errors='strict')
    except UnicodeError as exc:
        raise BundleRefusal('cft-member-name-refused') from exc
    need(unicodedata.normalize('NFC', value) == value and value.isprintable() and '\\' not in value
         and not any(ord(char) < 32 or ord(char) == 127 for char in value))
    body = value[:-1] if value.endswith('/') else value
    parts = body.split('/')
    need(parts[0] == asset + '-linux64' and all(part not in ('', '.', '..') for part in parts)
         and all(':' not in part and not part.endswith((' ', '.')) for part in parts))
    return value


def inert_extra_metadata(raw, *, central, code):
    """Validate bounded Info-ZIP UT/UX metadata; never apply times or identities."""
    need(type(raw) is bytes and len(raw) <= 64, code)
    result = {}
    offset = 0
    while offset < len(raw):
        need(len(raw) - offset >= 4, code)
        tag, size = struct.unpack_from('<2H', raw, offset)
        offset += 4
        need(tag in (0x5455, 0x7875) and tag not in result and offset + size <= len(raw), code)
        body = raw[offset:offset + size]
        offset += size
        if tag == 0x5455:
            need(len(body) >= 1 and body[0] in (1, 3, 5, 7), code)
            flags = body[0]
            if central:
                # Central flags describe LOCAL times; only mtime is stored here.
                need(flags & 1 and len(body) == 5, code)
            else:
                need(len(body) == 1 + 4 * flags.bit_count(), code)
            result[tag] = (flags, body[1:5])
        else:
            need(len(body) >= 5 and body[0] == 1 and 1 <= body[1] <= 8, code)
            gid_offset = 2 + body[1]
            need(gid_offset < len(body) and 1 <= body[gid_offset] <= 8, code)
            need(len(body) == gid_offset + 1 + body[gid_offset], code)
            result[tag] = body
    return result


def central_plan(footer, central, total, asset):
    need(asset in ASSETS and type(footer) is bytes and len(footer) == 22, 'cft-central-input-shape-refused')
    integer(total, MAX_ARCHIVE, 22)
    end = struct.unpack('<4s4H2IH', footer)
    need(end[0] == b'PK\x05\x06' and end[1] == end[2] == end[7] == 0
         and end[3] == end[4] and 1 <= end[4] <= MAX_ENTRIES
         and end[5] == len(central) <= MAX_CENTRAL and end[6] + end[5] + 22 == total,
         'cft-ZIP-footer-refused')
    result = []
    seen = set()
    offset = 0
    expanded = 0
    while offset < len(central):
        need(len(central) - offset >= 46, 'cft-central-header-size-refused')
        row = struct.unpack('<4s6H3I5H2I', central[offset:offset + 46])
        need(row[0] == b'PK\x01\x02', 'cft-central-signature-refused')
        need(row[1] >> 8 == 3, 'cft-central-creator-system-refused')
        need(row[2] <= 20, 'cft-central-extract-version-refused')
        for bit in (0, 1, 2, 4, 5, 6, 7, 8, 9, 10, 12, 13, 14, 15):
            # APPNOTE 4.4.4: bits 1/2 encode Deflate compression options.
            need(row[3] & (1 << bit) == 0 or (row[4] == 8 and bit in (1, 2)),
                 f'cft-central-stored-flag-bit-{bit}-refused' if row[4] == 0 and bit in (1, 2)
                 else f'cft-central-flag-bit-{bit}-refused')
        need(row[4] in (0, 8), 'cft-central-compression-refused')
        need(row[12] == 0, 'cft-central-comment-refused')
        need(row[13] == 0, 'cft-central-disk-refused')
        # APPNOTE 4.4.14.1: bit 0 is an advisory text hint, never a byte conversion.
        need(row[14] in (0, 1), 'cft-central-internal-attributes-refused')
        extra_len = row[11]
        need(extra_len == 0 or (4 <= extra_len <= 64
             and offset + 46 + row[10] + extra_len <= len(central)), 'cft-central-extra-field-refused')
        name_len = row[10]
        need(1 <= name_len <= MAX_NAME and offset + 46 + name_len <= len(central), 'cft-central-name-span-refused')
        name_raw = central[offset + 46:offset + 46 + name_len]
        extra = inert_extra_metadata(central[offset + 46 + name_len:offset + 46 + name_len + extra_len],
            central=True, code='cft-central-extra-field-refused')
        name = member_name(name_raw, row[3], asset)
        alias = name.rstrip('/').casefold()
        need(alias not in seen, 'cft-member-alias-refused')
        seen.add(alias)
        mode = row[15] >> 16
        directory = name.endswith('/')
        need(stat.S_IFMT(mode) == (stat.S_IFDIR if directory else stat.S_IFREG)
             and mode & 0o7000 == 0, 'cft-member-type-or-special-mode-refused')
        integer(row[8], MAX_ARCHIVE)
        integer(row[9], MAX_UNPACKED)
        need(row[8] != 0xFFFFFFFF and row[9] != 0xFFFFFFFF and row[16] != 0xFFFFFFFF, 'cft-central-ZIP64-refused')
        if directory:
            need(row[7] == row[8] == row[9] == 0 and row[4] == 0, 'cft-directory-data-layout-refused')
        else:
            need(row[4] != 0 or row[8] == row[9], 'cft-stored-member-size-refused')
            need(row[9] <= max(1, row[8]) * 200, 'cft-decompression-ratio-refused')
            expanded += row[9]
            need(expanded <= MAX_UNPACKED, 'cft-expanded-total-bound-refused')
        result.append({'path': name, 'raw_name': name_raw, 'flags': row[3], 'method': row[4],
            'crc32': row[7], 'compressed_size': row[8], 'size': row[9], 'mode': stat.S_IMODE(mode),
            'offset': row[16], 'kind': 'directory' if directory else 'file'})
        if extra:
            result[-1]['extra_metadata'] = extra
        offset += 46 + name_len + extra_len
    need(offset == len(central) and len(result) == end[4], 'cft-central-entry-count-refused')
    by_name = {row['path'].rstrip('/').casefold(): row['kind'] for row in result}
    for row in result:
        parts = row['path'].rstrip('/').casefold().split('/')
        for index in range(1, len(parts)):
            need(by_name.get('/'.join(parts[:index])) != 'file', 'cft-file-directory-collision')
    offsets = sorted(row['offset'] for row in result)
    need(len(set(offsets)) == len(offsets) and offsets[0] == 0 and offsets[-1] < end[6], 'cft-member-offset-layout-refused')
    need(any(row['path'] == EXECUTABLES[asset] and row['kind'] == 'file'
             and row['size'] > 0 and row['mode'] & 0o111 for row in result), 'cft-expected-executable-unobserved')
    return result, end[6]


def identity(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns, info.st_nlink, info.st_mode, info.st_uid)


def member_chunks(stream, row, deadline):
    stream.seek(row['data_start'])
    left = row['compressed_size']
    decoder = zlib.decompressobj(-15) if row['method'] == 8 else None
    while left:
        remaining(deadline)
        block = stream.read(min(CHUNK, left))
        need(type(block) is bytes and 0 < len(block) <= min(CHUNK, left))
        left -= len(block)
        if decoder is None:
            yield block
        else:
            pending = block
            while pending:
                old_length = len(pending)
                chunk = decoder.decompress(pending, CHUNK)
                pending = decoder.unconsumed_tail
                need(not decoder.unused_data and (chunk or len(pending) < old_length),
                     'cft-deflate-tail-or-progress-refused')
                if chunk:
                    yield chunk
    need(decoder is None or (decoder.eof and not decoder.unused_data and not decoder.unconsumed_tail),
         'cft-deflate-eof-refused')


def inventory(path, asset, deadline, *, expected_pin):
    before = Path(path).lstat()
    need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and 22 <= before.st_size <= MAX_ARCHIVE, 'cft-inventory-input-file-shape-refused')
    exact(expected_pin, {'bytes', 'sha256', 'identity'})
    integer(expected_pin['bytes'], MAX_ARCHIVE, 22)
    digest(expected_pin['sha256'])
    need(type(expected_pin['identity']) is list and len(expected_pin['identity']) == 8
         and list(identity(before)) == expected_pin['identity']
         and before.st_size == expected_pin['bytes'], 'cft-inventory-path-pin-refused')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as stream:
        need(archive_stream_pin(stream, before, deadline) == expected_pin,
             'cft-inventory-opened-source-pin-refused')
        need(identity(Path(path).lstat()) == identity(before), 'cft-inventory-after-hash-path-identity-refused')
        stream.seek(-22, 2)
        footer = stream.read(22)
        end = struct.unpack('<4s4H2IH', footer)
        need(end[5] <= MAX_CENTRAL and end[6] + end[5] + 22 == before.st_size, 'cft-inventory-footer-span-refused')
        stream.seek(end[6])
        central = stream.read(end[5])
        plan, central_start = central_plan(footer, central, before.st_size, asset)
        ordered = sorted(plan, key=lambda row: row['offset'])
        for index, row in enumerate(ordered):
            remaining(deadline)
            stream.seek(row['offset'])
            local_raw = stream.read(30)
            need(len(local_raw) == 30, 'cft-local-header-size-refused')
            local = struct.unpack('<4s5H3I2H', local_raw)
            need(local[0] == b'PK\x03\x04' and local[1] <= 20
                 and local[2] == row['flags'] and local[3] == row['method']
                 and local[9] == len(row['raw_name']) and local[10] <= 64, 'cft-local-header-layout-refused')
            need(stream.read(local[9]) == row['raw_name'], 'cft-local-name-refused')
            next_offset = ordered[index + 1]['offset'] if index + 1 < len(ordered) else central_start
            row['data_start'] = row['offset'] + 30 + local[9] + local[10]
            need(row['data_start'] <= next_offset, 'cft-local-header-layout-refused')
            local_extra_raw = stream.read(local[10])
            need(len(local_extra_raw) == local[10], 'cft-local-header-layout-refused')
            local_extra = inert_extra_metadata(local_extra_raw, central=False, code='cft-local-header-layout-refused')
            central_extra = row.get('extra_metadata', {})
            need(all(local_extra.get(tag) == value for tag, value in central_extra.items()),
                 'cft-local-header-layout-refused')
            local_ut = local_extra.get(0x5455)
            need((local_ut is not None and bool(local_ut[0] & 1)) == (0x5455 in central_extra),
                 'cft-local-header-layout-refused')
            data_end = row['data_start'] + row['compressed_size']
            trailer_size = next_offset - data_end
            if row['flags'] & 8:
                need(tuple(local[6:9]) in ((0, 0, 0), (row['crc32'], row['compressed_size'], row['size'])), 'cft-descriptor-local-values-refused')
                need(trailer_size in (12, 16), 'cft-descriptor-span-refused')
                stream.seek(data_end)
                trailer = stream.read(trailer_size)
                if trailer_size == 16:
                    need(trailer[:4] == b'PK\x07\x08', 'cft-descriptor-signature-refused')
                    trailer = trailer[4:]
                need(struct.unpack('<3I', trailer) == (row['crc32'], row['compressed_size'], row['size']), 'cft-descriptor-values-refused')
            else:
                need(tuple(local[6:9]) == (row['crc32'], row['compressed_size'], row['size']) and trailer_size == 0, 'cft-local-values-or-trailer-layout-refused')
        rows = []
        with zipfile.ZipFile(stream) as archive:
            infos = archive.infolist()
            need(len(infos) == len(plan), 'cft-zip-info-count-refused')
            for expected, info in zip(plan, infos, strict=True):
                need(info.orig_filename == expected['path'] and info.filename == expected['path']
                     and info.header_offset == expected['offset'] and info.flag_bits == expected['flags']
                     and info.compress_type == expected['method'] and info.CRC == expected['crc32']
                     and info.compress_size == expected['compressed_size'] and info.file_size == expected['size'], 'cft-zip-info-layout-refused')
                digest_state = hashlib.sha256()
                crc = 0
                size = 0
                if expected['kind'] == 'file':
                    for chunk in member_chunks(stream, expected, deadline):
                        remaining(deadline)
                        need(len(chunk) <= CHUNK, 'cft-member-chunk-bound-refused')
                        size += len(chunk)
                        need(size <= expected['size'], 'cft-member-size-overrun-refused')
                        digest_state.update(chunk)
                        crc = zlib.crc32(chunk, crc)
                    need(size == expected['size'] and crc & 0xFFFFFFFF == expected['crc32'], 'cft-member-size-or-crc-refused')
                rows.append({key: expected[key] for key in ('path', 'kind', 'size', 'compressed_size', 'mode')}
                            | {'sha256': digest_state.hexdigest() if expected['kind'] == 'file' else None})
        need(archive_stream_pin(stream, before, deadline) == expected_pin,
             'cft-inventory-final-source-pin-refused')
    need(identity(Path(path).lstat()) == identity(before), 'cft-inventory-final-path-identity-refused')
    rows.sort(key=lambda row: row['path'])
    encoded = packed(rows)
    need(len(encoded) <= MAX_PUBLIC, 'cft-inventory-public-size-refused')
    return {'entries': len(rows), 'files': sum(row['kind'] == 'file' for row in rows),
        'unpacked_bytes': sum(row['size'] for row in rows), 'inventory_sha256': hashed(encoded), 'inventory': rows}


def acquire(policy_raw, private, deadline, *, require_pins=False, progress=None):
    selected = policy(policy_raw, enabled=require_pins)
    private = Path(private)
    need(private.is_dir() and not private.is_symlink() and private.stat().st_uid == os.getuid()
         and stat.S_IMODE(private.stat().st_mode) == 0o700)
    blobs = private / 'cft-blobs'
    blobs.mkdir(mode=0o700)
    metadata_path = blobs / 'metadata.json'
    if progress is not None:
        progress('metadata-fetch')
    meta = fetch(METADATA_URL, metadata_path, deadline, maximum=MAX_METADATA, expected=selected['metadata'])
    metadata = metadata_path.read_bytes()
    need(len(metadata) == meta['bytes'] and hashed(metadata) == meta['sha256'])
    if progress is not None:
        progress('metadata-select')
    urls = select_metadata(metadata, VERSION)
    assets = {}
    for asset in ASSETS:
        expected = selected['archives'][asset]
        path = blobs / (asset + '.zip')
        if progress is not None:
            progress(asset + '-download')
        downloaded = fetch(urls[asset], path, deadline, maximum=MAX_ARCHIVE, expected=expected)
        if progress is not None:
            progress(asset + '-inventory')
        observed = bound_inventory(path, asset, downloaded, deadline)
        if require_pins:
            need(all(observed[key] == expected[key] for key in ('entries', 'files', 'unpacked_bytes', 'inventory_sha256')))
        assets[asset] = {'url': urls[asset], **downloaded, **observed}
    public = {'version': VERSION, 'platform': PLATFORM, 'metadata': meta, 'archives': assets,
        'policy_sha256': hashed(policy_raw), 'origin_evidence': 'certificate-and-hostname-verified-official-HTTPS',
        'independent_vendor_signature': False, 'publisher_license_approval': False,
        'vendor_binary_executed': False, 'sandbox_policy_changed': False,
        'genuine_browser_qualification': False, 'readiness_credit': 0}
    need(len(packed(public)) <= MAX_PUBLIC)
    return public


def root_ancestors(path):
    path = Path(path)
    need(path.is_absolute() and path.parent == ROOT_PARENT
         and re.fullmatch(r'row-cft-[0-9a-f]{32}', path.name), 'cft-root-location-refused')
    for parent in (Path('/'), ROOT_PARENT):
        info = parent.lstat()
        need(stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o022,
             'cft-root-ancestor-refused')
    return path


@contextmanager
def root_directory_lease(destination, *, create):
    """Hold no-follow ancestor/root fds and check observed directory identity.

    Creation is relative to the held /opt descriptor. Subsequent trusted-host
    writes stay beneath a root-owned non-writable tree; this does not claim an
    atomic defense against another hostile root process or kernel compromise.
    """
    root = root_ancestors(destination)
    held = []
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    try:
        for parent in (Path('/'), ROOT_PARENT):
            before = parent.lstat()
            descriptor = os.open(parent, directory_flags)
            held.append((parent, descriptor, before))
            need(identity(os.fstat(descriptor)) == identity(before))
        if create:
            # O_EXCL-equivalent directory creation: an existing name refuses.
            os.mkdir(root.name, mode=0o755, dir_fd=held[-1][1])
        before = root.lstat()
        need(stat.S_ISDIR(before.st_mode) and before.st_uid == 0
             and stat.S_IMODE(before.st_mode) in (0o755, 0o555))
        descriptor = os.open(root.name, directory_flags, dir_fd=held[-1][1])
        held.append((root, descriptor, before))
        need(identity(os.fstat(descriptor)) == identity(before))
        yield root
    finally:
        try:
            for path, descriptor, before in held:
                current = path.lstat()
                observed = os.fstat(descriptor)
                need(identity(current) == identity(observed))
                need((current.st_dev, current.st_ino, current.st_uid)
                     == (before.st_dev, before.st_ino, before.st_uid))
                need(stat.S_ISDIR(current.st_mode) and current.st_uid == 0
                     and not current.st_mode & 0o022)
        finally:
            for _path, descriptor, _before in reversed(held):
                os.close(descriptor)


def stable_file(path, maximum, deadline, *, root_owned=False, raw=False):
    path = Path(path)
    before = path.lstat()
    need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and 0 <= before.st_size <= maximum
         and not before.st_mode & 0o022 and (not root_owned or before.st_uid == 0))
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    digest_state = hashlib.sha256()
    collected = bytearray()
    observed = 0
    with os.fdopen(fd, 'rb') as stream:
        need(identity(os.fstat(stream.fileno())) == identity(before))
        while True:
            remaining(deadline)
            chunk = stream.read(CHUNK)
            if not chunk:
                break
            observed += len(chunk)
            need(observed <= before.st_size)
            digest_state.update(chunk)
            if raw:
                collected.extend(chunk)
        need(observed == before.st_size and identity(os.fstat(stream.fileno())) == identity(before))
    need(identity(path.lstat()) == identity(before))
    result = {'bytes': observed, 'sha256': digest_state.hexdigest(), 'identity': list(identity(before))}
    return (result, bytes(collected)) if raw else result


def expected_layout(rows):
    directories = set()
    files = {}
    for row in rows:
        path = row['path'].rstrip('/')
        parts = path.split('/')
        directories.update('/'.join(parts[:index]) for index in range(1, len(parts)))
        if row['kind'] == 'directory':
            directories.add(path)
        else:
            need(path not in files)
            files[path] = row
    need(not directories.intersection(files))
    return directories, files


def binding_contract(value):
    exact(value, {'source_head', 'source_tree', 'source_bytes_sha256', 'workflow_sha256', 'event_sha',
        'run_id', 'run_attempt'})
    for key in ('source_head', 'source_tree', 'event_sha'):
        need(type(value[key]) is str and re.fullmatch(r'[0-9a-f]{40}', value[key]))
    for key in ('source_bytes_sha256', 'workflow_sha256'):
        digest(value[key])
    for key in ('run_id', 'run_attempt'):
        need(type(value[key]) is str and re.fullmatch(r'[1-9][0-9]{0,19}', value[key]))
    return value


def install_pinned(policy_raw, private, destination, deadline, binding):
    """Later root-only preparation; never starts a vendor executable.

    Inputs must have been acquired by this root operation after independently
    reviewed source pins were enabled. Only a fresh root-owned /opt subtree is
    written. Refusal retains it for disposable-host destruction; no broad delete.
    """
    selected = policy(policy_raw, enabled=True)
    binding_contract(binding)
    need(os.getuid() == 0 and os.geteuid() == 0, 'cft-root-owner-required')
    private = Path(private)
    private_info = private.lstat()
    need(stat.S_ISDIR(private_info.st_mode) and private_info.st_uid == 0
         and stat.S_IMODE(private_info.st_mode) == 0o700)
    root = root_ancestors(destination)
    need(not root.exists() and not root.is_symlink(), 'cft-fresh-root-required')
    metadata_pin, metadata_raw = stable_file(private / 'cft-blobs' / 'metadata.json', MAX_METADATA,
        deadline, root_owned=True, raw=True)
    need({key: metadata_pin[key] for key in ('bytes', 'sha256')} == selected['metadata'])
    select_metadata(metadata_raw, VERSION)
    verified = {}
    for asset in ASSETS:
        archive_path = private / 'cft-blobs' / (asset + '.zip')
        archive_pin = stable_file(archive_path, MAX_ARCHIVE, deadline, root_owned=True)
        expected = selected['archives'][asset]
        need(archive_pin['bytes'] == expected['bytes'] and archive_pin['sha256'] == expected['sha256'])
        observed = inventory(archive_path, asset, deadline, expected_pin=archive_pin)
        need(all(observed[key] == expected[key] for key in ('entries', 'files', 'unpacked_bytes', 'inventory_sha256')))
        verified[asset] = observed
    all_rows = [row for asset in ASSETS for row in verified[asset]['inventory']]
    directories, files = expected_layout(all_rows)
    with root_directory_lease(root, create=True) as root:
        root_info = root.lstat()
        need(root_info.st_uid == 0 and stat.S_IMODE(root_info.st_mode) == 0o755)
        for name in sorted(directories, key=lambda value: (value.count('/'), value)):
            (root / name).mkdir(mode=0o755)
        for asset in ASSETS:
            archive_path = private / 'cft-blobs' / (asset + '.zip')
            # Recheck full source bytes/identity immediately before copying members.
            pinned_source = stable_file(archive_path, MAX_ARCHIVE, deadline, root_owned=True)
            need(pinned_source['sha256'] == selected['archives'][asset]['sha256'])
            fd = os.open(archive_path, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(fd, 'rb') as source:
                need(list(identity(os.fstat(source.fileno()))) == pinned_source['identity'])
                with zipfile.ZipFile(source) as archive:
                    for row in verified[asset]['inventory']:
                        if row['kind'] != 'file':
                            continue
                        remaining(deadline)
                        target = root / row['path']
                        descriptor = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
                        with os.fdopen(descriptor, 'wb') as output, archive.open(row['path']) as member:
                            size = 0
                            digest_state = hashlib.sha256()
                            while True:
                                remaining(deadline)
                                chunk = member.read(CHUNK)
                                if not chunk:
                                    break
                                size += len(chunk)
                                need(size <= row['size'])
                                output.write(chunk)
                                digest_state.update(chunk)
                            need(size == row['size'] and digest_state.hexdigest() == row['sha256'])
                            output.flush()
                            os.fsync(output.fileno())
                            # Fresh files only: never chmod/copy an image Chrome/driver.
                            os.fchmod(output.fileno(), 0o555 if row['mode'] & 0o111 else 0o444)
                need(list(identity(os.fstat(source.fileno()))) == pinned_source['identity'])
            need(stable_file(archive_path, MAX_ARCHIVE, deadline, root_owned=True) == pinned_source)
        manifest = {'schema': 'row.cft-root-complete-inventory.v1', 'version': VERSION,
            'binding': binding,
            'policy_sha256': hashed(policy_raw), 'metadata': selected['metadata'],
            'archives': {asset: {key: selected['archives'][asset][key] for key in
                ('bytes', 'sha256', 'inventory_sha256', 'entries', 'files', 'unpacked_bytes')} for asset in ASSETS},
            'inventory': all_rows, 'vendor_binary_executed': False,
            'sandbox_policy': 'unchanged-default-no-fallback', 'readiness_credit': 0}
        raw = packed(manifest)
        need(len(raw) <= MAX_PUBLIC)
        descriptor = os.open(root / 'cft-root-manifest.json', os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
            os.fchmod(stream.fileno(), 0o444)
        for name in sorted(directories, key=lambda value: (-value.count('/'), value)):
            os.chmod(root / name, 0o555, follow_symlinks=False)
        os.chmod(root, 0o555, follow_symlinks=False)
        return verify_installed(policy_raw, root, deadline, binding)


def verify_installed(policy_raw, destination, deadline, binding):
    selected = policy(policy_raw, enabled=True)
    binding_contract(binding)
    root = root_ancestors(destination)
    with root_directory_lease(root, create=False) as root:
        info = root.lstat()
        need(stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and stat.S_IMODE(info.st_mode) == 0o555)
        manifest_pin, raw = stable_file(root / 'cft-root-manifest.json', MAX_PUBLIC, deadline, root_owned=True, raw=True)
        manifest = decode(raw, MAX_PUBLIC)
        exact(manifest, {'schema', 'version', 'binding', 'policy_sha256', 'metadata', 'archives', 'inventory',
            'vendor_binary_executed', 'sandbox_policy', 'readiness_credit'})
        need(manifest['schema'] == 'row.cft-root-complete-inventory.v1' and manifest['version'] == VERSION
             and manifest['binding'] == binding
             and manifest['policy_sha256'] == hashed(policy_raw) and manifest['metadata'] == selected['metadata']
             and manifest['vendor_binary_executed'] is False
             and manifest['sandbox_policy'] == 'unchanged-default-no-fallback'
             and type(manifest['readiness_credit']) is int and manifest['readiness_credit'] == 0)
        exact(manifest['archives'], ASSETS)
        rows = manifest['inventory']
        need(type(rows) is list and 2 <= len(rows) <= MAX_ENTRIES * 2)
        by_asset = {asset: [] for asset in ASSETS}
        seen = set()
        for row in rows:
            exact(row, {'path', 'kind', 'size', 'compressed_size', 'mode', 'sha256'})
            need(type(row['path']) is str and len(row['path'].encode('utf-8')) <= MAX_NAME)
            asset = row['path'].split('-linux64/', 1)[0]
            need(asset in ASSETS and member_name(row['path'].encode('utf-8'), 0x800, asset) == row['path'])
            need(row['path'].rstrip('/').casefold() not in seen)
            seen.add(row['path'].rstrip('/').casefold())
            need(row['kind'] in ('file', 'directory') and (row['kind'] == 'directory') == row['path'].endswith('/'))
            integer(row['size'], MAX_UNPACKED)
            integer(row['compressed_size'], MAX_ARCHIVE)
            integer(row['mode'], 0o777)
            if row['kind'] == 'file':
                digest(row['sha256'])
            else:
                need(row['size'] == row['compressed_size'] == 0 and row['sha256'] is None)
            by_asset[asset].append(row)
        for asset in ASSETS:
            selected_rows = sorted(by_asset[asset], key=lambda row: row['path'])
            expected = selected['archives'][asset]
            expected_summary = {key: expected[key] for key in ('bytes', 'sha256', 'inventory_sha256', 'entries', 'files', 'unpacked_bytes')}
            need(manifest['archives'][asset] == expected_summary
                 and hashed(packed(selected_rows)) == expected['inventory_sha256']
                 and len(selected_rows) == expected['entries']
                 and sum(row['kind'] == 'file' for row in selected_rows) == expected['files']
                 and sum(row['size'] for row in selected_rows) == expected['unpacked_bytes'])
            need(any(row['path'] == EXECUTABLES[asset] and row['kind'] == 'file'
                     and row['size'] > 0 and row['mode'] & 0o111 for row in selected_rows))
        directories, files = expected_layout(rows)
        observed_files = set()
        observed_directories = set()
        pins = []
        for path in root.rglob('*'):
            remaining(deadline)
            need(len(observed_files) + len(observed_directories) <= MAX_ENTRIES * 4)
            relative = path.relative_to(root).as_posix()
            current = path.lstat()
            need(current.st_uid == 0 and current.st_mode & 0o022 == 0)
            if stat.S_ISDIR(current.st_mode):
                need(relative in directories and stat.S_IMODE(current.st_mode) == 0o555)
                observed_directories.add(relative)
            else:
                need(stat.S_ISREG(current.st_mode) and current.st_nlink == 1)
                observed_files.add(relative)
                if relative == 'cft-root-manifest.json':
                    need(stat.S_IMODE(current.st_mode) == 0o444)
                    continue
                need(relative in files)
                expected = files[relative]
                need(stat.S_IMODE(current.st_mode) == (0o555 if expected['mode'] & 0o111 else 0o444))
                actual = stable_file(path, MAX_UNPACKED, deadline, root_owned=True)
                need(actual['bytes'] == expected['size'] and actual['sha256'] == expected['sha256'])
                pins.append({'path': relative, **actual})
        need(observed_files == set(files) | {'cft-root-manifest.json'} and observed_directories == directories)
        need(stable_file(root / 'cft-root-manifest.json', MAX_PUBLIC, deadline, root_owned=True) == manifest_pin)
        need(identity(root.lstat()) == identity(info))
        return {'version': VERSION, 'policy_sha256': hashed(policy_raw),
            'manifest_sha256': manifest_pin['sha256'], 'bundle_inventory_sha256': hashed(packed(manifest['archives'])),
            'complete_installed_inventory_sha256': hashed(packed(sorted(pins, key=lambda row: row['path']))),
            'files': len(files), 'directories': len(directories), 'root_owned': True,
            'sandbox_policy': 'unchanged-default-no-fallback', 'independent_vendor_signature': False,
            'publisher_license_approval': False, 'readiness_credit': 0}


ACQUISITION_PHASES = ('source-checks', 'policy', 'metadata-fetch', 'metadata-select', 'chrome-download',
    'chrome-inventory', 'chromedriver-download', 'chromedriver-inventory', 'source-readback', 'cleanup')


INVENTORY_PHASES = ('chrome-inventory', 'chromedriver-inventory')
INVENTORY_REFUSAL_CODES = frozenset((
    'cft-ZIP-footer-refused',
    'cft-ZIP-member-format-refused',
    'cft-central-signature-refused',
    'cft-central-creator-system-refused',
    'cft-central-extract-version-refused',
    'cft-central-flags-refused',
    'cft-central-flag-bit-0-refused',
    'cft-central-flag-bit-1-refused',
    'cft-central-flag-bit-2-refused',
    'cft-central-stored-flag-bit-1-refused',
    'cft-central-stored-flag-bit-2-refused',
    'cft-central-flag-bit-4-refused',
    'cft-central-flag-bit-5-refused',
    'cft-central-flag-bit-6-refused',
    'cft-central-flag-bit-7-refused',
    'cft-central-flag-bit-8-refused',
    'cft-central-flag-bit-9-refused',
    'cft-central-flag-bit-10-refused',
    'cft-central-flag-bit-12-refused',
    'cft-central-flag-bit-13-refused',
    'cft-central-flag-bit-14-refused',
    'cft-central-flag-bit-15-refused',
    'cft-central-compression-refused',
    'cft-central-comment-refused',
    'cft-central-disk-refused',
    'cft-central-internal-attributes-refused',
    'cft-central-extra-field-refused',
    'cft-central-ZIP64-refused',
    'cft-central-entry-count-refused',
    'cft-central-header-size-refused',
    'cft-central-input-shape-refused',
    'cft-central-name-span-refused',
    'cft-contract-refused',
    'cft-deadline-refused',
    'cft-decompression-ratio-refused',
    'cft-deflate-eof-refused',
    'cft-deflate-tail-or-progress-refused',
    'cft-descriptor-local-values-refused',
    'cft-descriptor-signature-refused',
    'cft-descriptor-span-refused',
    'cft-descriptor-values-refused',
    'cft-directory-data-layout-refused',
    'cft-download-inventory-binding-refused',
    'cft-expanded-total-bound-refused',
    'cft-expected-executable-unobserved',
    'cft-file-directory-collision',
    'cft-inventory-after-hash-path-identity-refused',
    'cft-inventory-final-path-identity-refused',
    'cft-inventory-final-source-pin-refused',
    'cft-inventory-footer-span-refused',
    'cft-inventory-input-file-shape-refused',
    'cft-inventory-opened-source-pin-refused',
    'cft-inventory-path-pin-refused',
    'cft-inventory-public-size-refused',
    'cft-inventory-runtime-refused',
    'cft-inventory-source-readback-refused',
    'cft-local-header-layout-refused',
    'cft-local-header-size-refused',
    'cft-local-name-refused',
    'cft-local-values-or-trailer-layout-refused',
    'cft-member-alias-refused',
    'cft-member-chunk-bound-refused',
    'cft-member-name-refused',
    'cft-member-offset-layout-refused',
    'cft-member-size-or-crc-refused',
    'cft-member-size-overrun-refused',
    'cft-member-type-or-special-mode-refused',
    'cft-stored-member-size-refused',
    'cft-zip-info-count-refused',
    'cft-zip-info-layout-refused',
))


def inventory_refusal_code(error, phase):
    """Fixed public predicate only; never stringify an exception or expose paths."""
    if type(phase) is not str or phase not in INVENTORY_PHASES:
        return 'cft-acquisition-refused'
    if type(error) is BundleRefusal and len(error.args) == 1:
        code = error.args[0]
        if type(code) is str and code in INVENTORY_REFUSAL_CODES:
            return code
    return 'cft-inventory-runtime-refused'


def public_bytes(raw, policy_raw):
    """Pure allowlist only; validation grants no official-host or publisher trust."""
    value = decode(raw, MAX_PUBLIC)
    required = {'schema', 'status', 'complete', 'phase', 'vendor_binary_executed', 'genuine_browser_qualification',
        'independent_vendor_signature', 'publisher_license_approval', 'sandbox_policy_changed', 'readiness_credit'}
    final_flags = {'forced_cleanup_attempted', 'all_retained_zero_reaped', 'observed_groups_gone', 'complete_OS_descendants_proved'}
    optional = {'binding', 'acquisition', 'source_unchanged', 'private_acquisition_root_removed', 'elapsed_ms', 'refusal_code'} | final_flags
    need(type(value) is dict and required <= set(value) <= required | optional)
    need(value['schema'] == 'row.cft-acquisition.v1' and type(value['phase']) is str
         and value['phase'] in ACQUISITION_PHASES and type(value['complete']) is bool)
    for key in ('vendor_binary_executed', 'genuine_browser_qualification', 'independent_vendor_signature',
                'publisher_license_approval', 'sandbox_policy_changed'):
        need(value[key] is False)
    if 'complete_OS_descendants_proved' in value:
        need(value['complete_OS_descendants_proved'] is False)
    integer(value['readiness_credit'], 0)
    for key in ('forced_cleanup_attempted', 'all_retained_zero_reaped', 'observed_groups_gone'):
        if key in value:
            need(type(value[key]) is bool)
    for key in ('source_unchanged', 'private_acquisition_root_removed'):
        if key in value:
            need(type(value[key]) is bool)
    if 'elapsed_ms' in value:
        integer(value['elapsed_ms'], 299999)
    if 'binding' in value:
        binding = value['binding']
        exact(binding, {'source_head', 'source_tree', 'source_bytes_sha256', 'workflow_sha256', 'event_sha',
            'run_id', 'run_attempt', 'image_version', 'image_os'})
        binding_contract({key: binding[key] for key in ('source_head', 'source_tree', 'source_bytes_sha256',
            'workflow_sha256', 'event_sha', 'run_id', 'run_attempt')})
        need(binding['image_os'] == 'ubuntu24' and type(binding['image_version']) is str
             and re.fullmatch(r'[0-9.]{1,64}', binding['image_version']))
    if value['complete']:
        need(set(value) == required | final_flags | {'binding', 'acquisition', 'source_unchanged', 'private_acquisition_root_removed', 'elapsed_ms'}
             and value['status'] == 'acquisition-complete-unqualified' and value['phase'] == 'cleanup'
             and value['source_unchanged'] is True and value['private_acquisition_root_removed'] is True
             and value['forced_cleanup_attempted'] is False and value['all_retained_zero_reaped'] is True
             and value['observed_groups_gone'] is True)
        acquired = value['acquisition']
        exact(acquired, {'version', 'platform', 'metadata', 'archives', 'policy_sha256', 'origin_evidence',
            'independent_vendor_signature', 'publisher_license_approval', 'vendor_binary_executed',
            'sandbox_policy_changed', 'genuine_browser_qualification', 'readiness_credit'})
        need(acquired['version'] == VERSION and acquired['platform'] == PLATFORM
             and acquired['policy_sha256'] == hashed(policy_raw)
             and acquired['origin_evidence'] == 'certificate-and-hostname-verified-official-HTTPS')
        policy(policy_raw, enabled=False)
        for key in ('independent_vendor_signature', 'publisher_license_approval', 'vendor_binary_executed',
                    'sandbox_policy_changed', 'genuine_browser_qualification'):
            need(acquired[key] is False)
        integer(acquired['readiness_credit'], 0)
        exact(acquired['metadata'], {'bytes', 'sha256'})
        integer(acquired['metadata']['bytes'], MAX_METADATA, 1)
        digest(acquired['metadata']['sha256'])
        exact(acquired['archives'], ASSETS)
        for asset in ASSETS:
            item = acquired['archives'][asset]
            exact(item, {'url', 'bytes', 'sha256', 'entries', 'files', 'unpacked_bytes', 'inventory_sha256', 'inventory'})
            need(item['url'] == asset_url(VERSION, asset))
            integer(item['bytes'], MAX_ARCHIVE, 22)
            digest(item['sha256'])
            digest(item['inventory_sha256'])
            integer(item['entries'], MAX_ENTRIES, 1)
            integer(item['files'], item['entries'], 1)
            integer(item['unpacked_bytes'], MAX_UNPACKED, 1)
            rows = item['inventory']
            need(type(rows) is list and len(rows) == item['entries'])
            aliases = set()
            for row in rows:
                exact(row, {'path', 'kind', 'size', 'compressed_size', 'mode', 'sha256'})
                need(type(row['path']) is str and member_name(row['path'].encode('utf-8'), 0x800, asset) == row['path'])
                alias = row['path'].rstrip('/').casefold()
                need(alias not in aliases)
                aliases.add(alias)
                need(row['kind'] in ('file', 'directory') and (row['kind'] == 'directory') == row['path'].endswith('/'))
                integer(row['size'], MAX_UNPACKED)
                integer(row['compressed_size'], MAX_ARCHIVE)
                integer(row['mode'], 0o777)
                if row['kind'] == 'file':
                    digest(row['sha256'])
                else:
                    need(row['size'] == row['compressed_size'] == 0 and row['sha256'] is None)
            expected_layout(rows)
            need(rows == sorted(rows, key=lambda row: row['path']) and hashed(packed(rows)) == item['inventory_sha256']
                 and sum(row['kind'] == 'file' for row in rows) == item['files']
                 and sum(row['size'] for row in rows) == item['unpacked_bytes']
                 and any(row['path'] == EXECUTABLES[asset] and row['kind'] == 'file'
                         and row['size'] > 0 and row['mode'] & 0o111 for row in rows))
    else:
        need(value['status'] == 'refused' and 'acquisition' not in value
             and ('refusal_code' not in value or value['refusal_code'] == 'cft-acquisition-refused'
                  or (value['phase'] in INVENTORY_PHASES and type(value['refusal_code']) is str
                      and value['refusal_code'] in INVENTORY_REFUSAL_CODES)))
    return raw


def archive_stream_pin(stream, before, deadline):
    """Hash the complete archive through the same retained no-follow descriptor."""
    need(identity(os.fstat(stream.fileno())) == identity(before))
    stream.seek(0)
    digest_state = hashlib.sha256()
    observed = 0
    while True:
        remaining(deadline)
        chunk = stream.read(CHUNK)
        need(type(chunk) is bytes and len(chunk) <= CHUNK)
        if not chunk:
            break
        observed += len(chunk)
        need(observed <= before.st_size)
        digest_state.update(chunk)
    need(observed == before.st_size and identity(os.fstat(stream.fileno())) == identity(before))
    return {'bytes': observed, 'sha256': digest_state.hexdigest(), 'identity': list(identity(before))}


def bound_inventory(path, asset, downloaded, deadline, *, root_owned=False):
    """Bind download hashes to the exact archive descriptor and final pathname."""
    exact(downloaded, {'bytes', 'sha256'})
    integer(downloaded['bytes'], MAX_ARCHIVE, 22)
    digest(downloaded['sha256'])
    pinned = stable_file(path, MAX_ARCHIVE, deadline, root_owned=root_owned)
    need({key: pinned[key] for key in ('bytes', 'sha256')} == downloaded,
         'cft-download-inventory-binding-refused')
    observed = inventory(path, asset, deadline, expected_pin=pinned)
    need(stable_file(path, MAX_ARCHIVE, deadline, root_owned=root_owned) == pinned,
         'cft-inventory-source-readback-refused')
    return observed


def finish_acquisition(record, acquired, policy_raw):
    """Return validated completion only after the durable incomplete checkpoint."""
    public_bytes(packed(record), policy_raw)
    need(record['complete'] is False and record['phase'] == 'cleanup')
    candidate = dict(record)
    candidate.update(status='acquisition-complete-unqualified', complete=True, acquisition=acquired)
    candidate.pop('refusal_code', None)
    public_bytes(packed(candidate), policy_raw)
    return candidate
