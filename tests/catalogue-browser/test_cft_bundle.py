"""Authored, unexecuted pure/mocked CfT guards; synthetic ZIPs confer no authority."""
import contextlib
import io
import ssl
import stat
import struct
import unittest
import urllib.request
import zipfile
import zlib
from pathlib import Path, PurePosixPath, PureWindowsPath
from types import SimpleNamespace
from unittest import mock

import cft_bundle as bundle


def disabled():
    return {'schema': 'row.cft-provider-policy.v1', 'enabled': False, 'version': bundle.VERSION,
        'platform': 'linux64', 'metadata_url': bundle.METADATA_URL, 'metadata': None,
        'archives': {'chrome': None, 'chromedriver': None},
        'origin_evidence': 'certificate-and-hostname-verified-official-HTTPS',
        'independent_vendor_signature': False, 'publisher_license_approval': False,
        'sandbox_policy': 'unchanged-default-no-fallback'}


def metadata():
    return {'version': bundle.VERSION, 'revision': '1689415', 'downloads': {
        asset: [{'platform': 'linux64', 'url': bundle.asset_url(bundle.VERSION, asset)}]
        for asset in bundle.ASSETS}}


def synthetic_zip(*, asset='chrome', names=None, compression=zipfile.ZIP_STORED):
    memory = io.BytesIO()
    names = names or [(bundle.EXECUTABLES[asset], stat.S_IFREG | 0o755, b'\x7fELFsynthetic')]
    with zipfile.ZipFile(memory, 'w', compression=compression) as archive:
        for name, mode, raw in names:
            info = zipfile.ZipInfo(name)
            info.create_system = 3
            info.external_attr = mode << 16
            info.compress_type = compression
            archive.writestr(info, raw)
    return memory.getvalue()


def plan(raw, asset='chrome'):
    footer = raw[-22:]
    end = struct.unpack('<4s4H2IH', footer)
    return bundle.central_plan(footer, raw[end[6]:end[6] + end[5]], len(raw), asset)


def with_entry_extras(raw, local_extras, central_extras):
    """Insert synthetic metadata while preserving payload bytes and exact offsets."""
    end = list(struct.unpack('<4s4H2IH', raw[-22:]))
    assert end[3] == end[4] == len(local_extras) == len(central_extras)
    headers = []
    cursor = end[6]
    for _ in local_extras:
        central = list(struct.unpack_from('<4s6H3I5H2I', raw, cursor))
        assert central[11] == central[12] == 0
        name = raw[cursor + 46:cursor + 46 + central[10]]
        headers.append((central, name))
        cursor += 46 + central[10]
    assert cursor == end[6] + end[5]
    locals_out, centrals_out = [], []
    local_cursor = 0
    for index, ((central, name), local_extra, central_extra) in enumerate(zip(headers, local_extras, central_extras, strict=True)):
        old_offset = central[16]
        local = list(struct.unpack_from('<4s5H3I2H', raw, old_offset))
        assert local[10] == 0 and raw[old_offset + 30:old_offset + 30 + local[9]] == name
        old_end = headers[index + 1][0][16] if index + 1 < len(headers) else end[6]
        payload = raw[old_offset + 30 + local[9]:old_end]
        local[10], central[11], central[16] = len(local_extra), len(central_extra), local_cursor
        local_bytes = struct.pack('<4s5H3I2H', *local) + name + local_extra + payload
        locals_out.append(local_bytes)
        local_cursor += len(local_bytes)
        centrals_out.append(struct.pack('<4s6H3I5H2I', *central) + name + central_extra)
    local_bytes, central_bytes = b''.join(locals_out), b''.join(centrals_out)
    end[5], end[6] = len(central_bytes), len(local_bytes)
    return local_bytes + central_bytes + struct.pack('<4s4H2IH', *end)


def with_single_entry_extras(raw, local_extra, central_extra):
    return with_entry_extras(raw, [local_extra], [central_extra])


def extra_field(tag, body):
    return struct.pack('<2H', tag, len(body)) + body


def timestamp_extras(flags=7):
    times = (b'\x01\x02\x03\x04', b'\x05\x06\x07\x08', b'\x09\x0a\x0b\x0c')
    local = extra_field(0x5455, bytes([flags]) + b''.join(value for bit, value in enumerate(times) if flags & (1 << bit)))
    central = extra_field(0x5455, bytes([flags]) + times[0]) if flags & 1 else b''
    return local, central


class Response:
    def __init__(self, body, url, *, declared=None, status=200, headers=None):
        self.body = io.BytesIO(body)
        self.status = status
        self.url = url
        self.closed = False
        self.headers = {'Content-Length': str(len(body) if declared is None else declared), **(headers or {})}

    def geturl(self):
        return self.url

    def read(self, count):
        return self.body.read(count)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.closed = True


class Output(io.BytesIO):
    def fileno(self):
        return 71

    def close(self):
        # Retain synthetic output bytes solely for the fixture's assertions.
        self.was_closed = True


def fixture_path_io_refused(*_args, **_kwargs):
    raise AssertionError('cft-fixture-unmocked-path-IO')


class UbuntuFixturePath(PurePosixPath):
    """Ubuntu lexical paths, with filesystem methods available only as mocks."""

    lstat = stat = mkdir = exists = is_symlink = is_dir = open = read_bytes = fixture_path_io_refused
    write_bytes = read_text = write_text = unlink = rename = replace = resolve = fixture_path_io_refused


class CFTPureFixtureCase(unittest.TestCase):
    def setUp(self):
        super().setUp()
        lease = contextlib.ExitStack()
        # Register first so a refusal midway through setup restores prior patches.
        self.addCleanup(lease.close)
        lease.enter_context(mock.patch.dict(globals(), {'Path': UbuntuFixturePath}))
        lease.enter_context(mock.patch.object(bundle, 'Path', UbuntuFixturePath))
        lease.enter_context(mock.patch.object(bundle, 'ROOT_PARENT', UbuntuFixturePath('/opt')))


class FixtureBootstrapTests(unittest.TestCase):
    def bootstrap_case(self):
        class BootstrapOnlyCase(CFTPureFixtureCase):
            def runTest(self):
                raise AssertionError('fixture-bootstrap-body-dispatch-refused')

        return BootstrapOnlyCase('runTest')

    def test_actual_bootstrap_uses_POSIX_paths_with_windows_originals_and_restores(self):
        original = (Path, bundle.Path, bundle.ROOT_PARENT)
        with mock.patch.dict(globals(), {'Path': PureWindowsPath}), \
             mock.patch.object(bundle, 'Path', PureWindowsPath), \
             mock.patch.object(bundle, 'ROOT_PARENT', PureWindowsPath('/opt')):
            simulated = (Path, bundle.Path, bundle.ROOT_PARENT)
            case = self.bootstrap_case()
            try:
                case.setUp()
                self.assertIs(Path, UbuntuFixturePath)
                self.assertIs(bundle.Path, UbuntuFixturePath)
                self.assertEqual(bundle.ROOT_PARENT, UbuntuFixturePath('/opt'))
                self.assertTrue(Path('/opt/row-cft-' + 'a' * 32).is_absolute())
                self.assertFalse(PureWindowsPath('/opt/row-cft-' + 'a' * 32).is_absolute())
                with self.assertRaisesRegex(AssertionError, '^cft-fixture-unmocked-path-IO$'):
                    Path('/synthetic-never-opened').open('rb')
                with mock.patch.object(bundle.Path, 'lstat', return_value='mock-only'):
                    self.assertEqual(Path('/synthetic-never-opened').lstat(), 'mock-only')
            finally:
                case.doCleanups()
            self.assertEqual((Path, bundle.Path, bundle.ROOT_PARENT), simulated)
        self.assertEqual((Path, bundle.Path, bundle.ROOT_PARENT), original)

    def test_mid_setup_refusal_restores_every_previous_path_provider(self):
        original = (Path, bundle.Path, bundle.ROOT_PARENT)
        actual_object_patch = mock.patch.object
        entered = []

        def refuse_root_parent(target, name, *args, **kwargs):
            if target is bundle:
                entered.append(name)
                if name == 'ROOT_PARENT':
                    self.assertIs(Path, UbuntuFixturePath)
                    self.assertIs(bundle.Path, UbuntuFixturePath)
                    raise RuntimeError('cft-fixture-bootstrap-refused')
            return actual_object_patch(target, name, *args, **kwargs)

        case = self.bootstrap_case()
        with mock.patch.object(mock.patch, 'object', side_effect=refuse_root_parent):
            try:
                with self.assertRaises(RuntimeError):
                    case.setUp()
            finally:
                case.doCleanups()
        self.assertEqual(entered, ['Path', 'ROOT_PARENT'])
        self.assertEqual((Path, bundle.Path, bundle.ROOT_PARENT), original)


class PurePolicyAndMetadataTests(CFTPureFixtureCase):
    def test_disabled_template_cannot_enable_provisioning(self):
        raw = bundle.packed(disabled())
        self.assertFalse(bundle.policy(raw, enabled=False)['enabled'])
        with self.assertRaises(bundle.BundleRefusal):
            bundle.policy(raw, enabled=True)

    def test_disabled_policy_cannot_carry_unreviewed_hashes(self):
        value = disabled()
        value['archives']['chrome'] = {'sha256': '0' * 64}
        with self.assertRaises(bundle.BundleRefusal):
            bundle.policy(bundle.packed(value), enabled=False)

    def test_policy_never_promotes_signature_license_or_sandbox(self):
        for key, value in (('independent_vendor_signature', True), ('publisher_license_approval', True),
                           ('sandbox_policy', 'no-sandbox'), ('enabled', 0), ('platform', 'win64')):
            with self.subTest(key=key):
                record = disabled()
                record[key] = value
                with self.assertRaises(bundle.BundleRefusal):
                    bundle.policy(bundle.packed(record), enabled=False)

    def test_duplicate_keys_nonfinite_and_unknown_schema_refuse(self):
        for raw in (b'{"version":"a","version":"b"}', b'{"version":NaN}', b'{"version":Infinity}'):
            with self.subTest(raw_hash=bundle.hashed(raw)):
                with self.assertRaises(bundle.BundleRefusal):
                    bundle.decode(raw, 65536)
        value = disabled()
        value['unexpected'] = True
        with self.assertRaises(bundle.BundleRefusal):
            bundle.policy(bundle.packed(value), enabled=False)

    def test_exact_same_version_official_urls_selected(self):
        value = bundle.select_metadata(bundle.packed(metadata()), bundle.VERSION)
        self.assertEqual(value, {asset: bundle.asset_url(bundle.VERSION, asset) for asset in bundle.ASSETS})

    def test_wrong_version_alias_duplicate_platform_and_URL_refuse(self):
        variants = []
        version = metadata()
        version['version'] = '154.0.8037.93'
        variants.append(version)
        duplicate = metadata()
        duplicate['downloads']['chrome'] *= 2
        variants.append(duplicate)
        for suffix in ('?token=private', '#alias', '/../chrome-linux64.zip'):
            value = metadata()
            value['downloads']['chrome'][0]['url'] += suffix
            variants.append(value)
        other = metadata()
        other['downloads']['chrome'][0]['url'] = 'https://storage.googleapis.com.evil.invalid/archive.zip'
        variants.append(other)
        for ordinal, value in enumerate(variants):
            with self.subTest(ordinal=ordinal):
                with self.assertRaises(bundle.BundleRefusal):
                    bundle.select_metadata(bundle.packed(value), bundle.VERSION)

    def test_version_token_is_bounded_and_canonical(self):
        for value in ('154.0.8037.092', '154.0.8037.92/../a', '1.' * 32, True, '154.0.8037.92?x'):
            with self.subTest(type_name=type(value).__name__):
                with self.assertRaises(bundle.BundleRefusal):
                    bundle.asset_url(value, 'chrome')


class PureZIPPlanTests(CFTPureFixtureCase):
    def test_complete_regular_plan_preserves_expected_executable(self):
        raw = synthetic_zip()
        rows, central = plan(raw)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['path'], bundle.EXECUTABLES['chrome'])
        self.assertEqual(rows[0]['kind'], 'file')
        self.assertGreater(central, rows[0]['offset'])

    def test_alias_path_unicode_and_link_members_refuse(self):
        bad_names = ['chrome-linux64/../chrome', '/chrome-linux64/chrome', 'chrome-linux64//chrome',
            'chrome-linux64/chrome.', 'chrome-linux64/chrome\\alias', 'chrome-linux64/\u200bhidden',
            'chrome-linux64/e\u0301', 'chromedriver-linux64/chrome', 'chrome-linux64/C:private']
        for name in bad_names:
            with self.subTest(name_hash=bundle.hashed(name.encode())):
                with self.assertRaises(bundle.BundleRefusal):
                    bundle.member_name(name.encode(), 0x800, 'chrome')
        for mode in (stat.S_IFLNK | 0o777, stat.S_IFREG | 0o4755, stat.S_IFREG | 0o2755):
            with self.subTest(mode=mode):
                with self.assertRaises(bundle.BundleRefusal):
                    plan(synthetic_zip(names=[(bundle.EXECUTABLES['chrome'], mode, b'fake')]))

    def test_case_alias_and_file_directory_collision_refuse(self):
        cases = [
            [(bundle.EXECUTABLES['chrome'], stat.S_IFREG | 0o755, b'x'),
             ('chrome-linux64/Chrome', stat.S_IFREG | 0o755, b'y')],
            [(bundle.EXECUTABLES['chrome'], stat.S_IFREG | 0o755, b'x'),
             ('chrome-linux64/a', stat.S_IFREG | 0o444, b'x'),
             ('chrome-linux64/a/child', stat.S_IFREG | 0o444, b'x')]]
        for names in cases:
            with self.subTest(member_count=len(names)):
                with self.assertRaises(bundle.BundleRefusal):
                    plan(synthetic_zip(names=names))

    def test_footer_count_comment_ZIP64_and_central_bounds_refuse(self):
        raw = synthetic_zip()
        footer = list(struct.unpack('<4s4H2IH', raw[-22:]))
        end = struct.unpack('<4s4H2IH', raw[-22:])
        central = raw[end[6]:end[6] + end[5]]
        for field, value in ((1, 1), (4, 65535), (7, 1), (5, bundle.MAX_CENTRAL + 1), (6, 0xFFFFFFFF)):
            with self.subTest(field=field):
                values = footer.copy()
                values[field] = value
                with self.assertRaises(bundle.BundleRefusal):
                    bundle.central_plan(struct.pack('<4s4H2IH', *values), central, len(raw), 'chrome')

    def test_encryption_unsupported_method_and_false_plain_int_refuse(self):
        raw = synthetic_zip()
        end = struct.unpack('<4s4H2IH', raw[-22:])
        central = raw[end[6]:end[6] + end[5]]
        for field, value in ((3, 1), (4, 99), (2, 45), (16, 0xFFFFFFFF)):
            with self.subTest(field=field):
                header = list(struct.unpack('<4s6H3I5H2I', central[:46]))
                header[field] = value
                with self.assertRaises(bundle.BundleRefusal):
                    bundle.central_plan(raw[-22:], struct.pack('<4s6H3I5H2I', *header) + central[46:], len(raw), 'chrome')
        with self.assertRaises(bundle.BundleRefusal):
            bundle.central_plan(raw[-22:], central, True, 'chrome')

    def test_bounded_raw_deflate_full_EOF_and_no_extra_tail(self):
        source = b'content' * 1000
        compressor = zlib.compressobj(wbits=-15)
        raw = compressor.compress(source) + compressor.flush()
        row = {'data_start': 0, 'compressed_size': len(raw), 'method': 8}
        with mock.patch.object(bundle.time, 'monotonic', return_value=1):
            blocks = list(bundle.member_chunks(io.BytesIO(raw), row, 30))
        self.assertEqual(b''.join(blocks), source)
        self.assertTrue(all(len(block) <= bundle.CHUNK for block in blocks))
        for broken in (raw + b'PRIVATE', raw[:-1]):
            with self.subTest(length=len(broken)):
                row = {'data_start': 0, 'compressed_size': len(broken), 'method': 8}
                with mock.patch.object(bundle.time, 'monotonic', return_value=1):
                    with self.assertRaises(bundle.BundleRefusal):
                        list(bundle.member_chunks(io.BytesIO(broken), row, 30))


class MockHTTPTests(CFTPureFixtureCase):
    def fetch(self, response, *, expected=None, tls=None):
        output = Output()
        context = tls or SimpleNamespace(check_hostname=True, verify_mode=ssl.CERT_REQUIRED)
        opener = mock.Mock()
        opener.open.return_value = response
        with mock.patch.object(bundle.ssl, 'create_default_context', return_value=context), \
             mock.patch.object(bundle.urllib.request, 'build_opener', return_value=opener) as build, \
             mock.patch.object(bundle.os, 'open', return_value=71), \
             mock.patch.object(bundle.os, 'O_NOFOLLOW', 0x20000, create=True), \
             mock.patch.object(bundle.os, 'fdopen', return_value=output), \
             mock.patch.object(bundle.os, 'fsync') as fsync, mock.patch.object(bundle.os, 'fchmod', create=True) as mode, \
             mock.patch.object(bundle.time, 'monotonic', return_value=1):
            result = bundle.fetch(bundle.asset_url(bundle.VERSION, 'chrome'), Path('/synthetic/never-created'), 30,
                maximum=1000, expected=expected)
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, response.url)
        self.assertEqual(request.header_items(), [('Accept-encoding', 'identity')])
        self.assertIsInstance(build.call_args.args[0], urllib.request.ProxyHandler)
        self.assertEqual(build.call_args.args[0].proxies, {})
        self.assertIsInstance(build.call_args.args[1], bundle.NoRedirect)
        fsync.assert_called_once_with(71)
        mode.assert_called_once_with(71, 0o400)
        self.assertTrue(response.closed)
        return result, output.getvalue()

    def test_complete_credential_free_pinned_response(self):
        body = b'synthetic ZIP only'
        expected = {'bytes': len(body), 'sha256': bundle.hashed(body)}
        observed, raw = self.fetch(Response(body, bundle.asset_url(bundle.VERSION, 'chrome')), expected=expected)
        self.assertEqual(observed, expected)
        self.assertEqual(raw, body)

    def test_redirect_header_compression_and_wrong_origin_refuse(self):
        url = bundle.asset_url(bundle.VERSION, 'chrome')
        cases = [Response(b'x', url, status=302), Response(b'x', url + '?private'),
            Response(b'x', url, headers={'Content-Encoding': 'gzip'}),
            Response(b'x', url, headers={'Transfer-Encoding': 'chunked'})]
        for response in cases:
            with self.subTest(status=response.status):
                with self.assertRaises(bundle.BundleRefusal):
                    self.fetch(response)
                self.assertTrue(response.closed)

    def test_truncated_overlong_and_pinned_hash_mismatch_refuse(self):
        url = bundle.asset_url(bundle.VERSION, 'chrome')
        cases = [(Response(b'x', url, declared=2), None), (Response(b'xx', url, declared=1), None),
            (Response(b'x', url), {'bytes': 1, 'sha256': '0' * 64}),
            (Response(b'x', url), {'bytes': 2, 'sha256': bundle.hashed(b'x')})]
        for response, expected in cases:
            with self.subTest(declared=response.headers['Content-Length']):
                with self.assertRaises(bundle.BundleRefusal):
                    self.fetch(response, expected=expected)
                self.assertTrue(response.closed)

    def test_missing_certificate_or_hostname_checks_refuse_before_open(self):
        for context in (SimpleNamespace(check_hostname=False, verify_mode=ssl.CERT_REQUIRED),
                        SimpleNamespace(check_hostname=True, verify_mode=ssl.CERT_NONE)):
            with self.subTest(hostname=context.check_hostname):
                with mock.patch.object(bundle.ssl, 'create_default_context', return_value=context), \
                     mock.patch.object(bundle.urllib.request, 'build_opener') as opener:
                    with self.assertRaises(bundle.BundleRefusal):
                        bundle.fetch(bundle.METADATA_URL, Path('/unused'), 30, maximum=100)
                    opener.assert_not_called()

    def test_transport_message_never_becomes_public_refusal(self):
        opener = mock.Mock()
        opener.open.side_effect = OSError('PRIVATE URL TOKEN PATH')
        context = SimpleNamespace(check_hostname=True, verify_mode=ssl.CERT_REQUIRED)
        with mock.patch.object(bundle.ssl, 'create_default_context', return_value=context), \
             mock.patch.object(bundle.urllib.request, 'build_opener', return_value=opener), \
             mock.patch.object(bundle.time, 'monotonic', return_value=1):
            with self.assertRaises(bundle.BundleRefusal) as observed:
                bundle.fetch(bundle.METADATA_URL, Path('/unused'), 30, maximum=100)
        self.assertEqual(str(observed.exception), 'cft-transport-or-write-refused')
        self.assertIsInstance(observed.exception.__cause__, OSError)

    def test_inherited_CA_override_or_TLS_keylog_refuses_before_context(self):
        for key in ('SSL_CERT_FILE', 'SSL_CERT_DIR', 'SSLKEYLOGFILE', 'ssl_cert_file'):
            with self.subTest(key=key):
                with mock.patch.dict(bundle.os.environ, {key: 'PRIVATE'}, clear=True), \
                     mock.patch.object(bundle.ssl, 'create_default_context') as context:
                    with self.assertRaises(bundle.BundleRefusal):
                        bundle.fetch(bundle.METADATA_URL, Path('/unused'), 30, maximum=100)
                    context.assert_not_called()


class WriterBoundaryTests(CFTPureFixtureCase):
    def test_root_lease_holds_no_follow_fds_and_creates_only_relative_name(self):
        info = SimpleNamespace(st_dev=1, st_ino=2, st_size=4096, st_mtime_ns=3,
            st_ctime_ns=4, st_nlink=2, st_mode=stat.S_IFDIR | 0o755, st_uid=0)
        root = Path('/opt/row-cft-' + 'a' * 32)
        with mock.patch.object(bundle.Path, 'lstat', return_value=info), \
             mock.patch.object(bundle.os, 'open', side_effect=[71, 72, 73]) as opened, \
             mock.patch.object(bundle.os, 'fstat', return_value=info), \
             mock.patch.object(bundle.os, 'O_DIRECTORY', 0x10000, create=True), \
             mock.patch.object(bundle.os, 'O_NOFOLLOW', 0x20000, create=True), \
             mock.patch.object(bundle.os, 'mkdir') as created, \
             mock.patch.object(bundle.os, 'close') as closed:
            with bundle.root_directory_lease(root, create=True) as observed:
                self.assertEqual(observed, root)
                closed.assert_not_called()
            created.assert_called_once_with(root.name, mode=0o755, dir_fd=72)
            self.assertTrue(all(call.args[1] & 0x30000 == 0x30000 for call in opened.call_args_list))
            self.assertEqual(closed.call_args_list, [mock.call(73), mock.call(72), mock.call(71)])

    def test_root_lease_identity_refusal_still_closes_every_acquired_fd(self):
        info = SimpleNamespace(st_dev=1, st_ino=2, st_size=4096, st_mtime_ns=3,
            st_ctime_ns=4, st_nlink=2, st_mode=stat.S_IFDIR | 0o755, st_uid=0)
        other = SimpleNamespace(**vars(info) | {'st_ino': 8})
        with mock.patch.object(bundle.Path, 'lstat', return_value=info), \
             mock.patch.object(bundle.os, 'open', return_value=71), \
             mock.patch.object(bundle.os, 'fstat', return_value=other), \
             mock.patch.object(bundle.os, 'O_DIRECTORY', 0x10000, create=True), \
             mock.patch.object(bundle.os, 'O_NOFOLLOW', 0x20000, create=True), \
             mock.patch.object(bundle.os, 'close') as closed:
            with self.assertRaises(bundle.BundleRefusal):
                with bundle.root_directory_lease(Path('/opt/row-cft-' + 'a' * 32), create=False):
                    self.fail('identity mismatch reached root operation')
            closed.assert_called_once_with(71)

    def test_nonroot_install_refuses_before_new_root_write(self):
        with mock.patch.object(bundle, 'policy', return_value={}), \
             mock.patch.object(bundle, 'binding_contract', return_value={}), \
             mock.patch.object(bundle.os, 'getuid', return_value=1000, create=True), \
             mock.patch.object(bundle.os, 'geteuid', return_value=1000, create=True), \
             mock.patch.object(bundle.Path, 'mkdir') as create:
            with self.assertRaises(bundle.BundleRefusal):
                bundle.install_pinned(b'fixture no authority', Path('/unused'), Path('/opt/row-cft-' + 'a' * 32), 30, {})
            create.assert_not_called()

    def test_root_destination_and_ancestor_writer_contract(self):
        directory = SimpleNamespace(st_mode=stat.S_IFDIR | 0o755, st_uid=0)
        with mock.patch.object(bundle.Path, 'lstat', return_value=directory):
            expected = Path('/opt/row-cft-' + 'a' * 32)
            self.assertEqual(bundle.root_ancestors(expected), expected)
            for path in (Path('/tmp/row-cft-' + 'a' * 32), Path('/opt/google/chrome'),
                         Path('/opt/row-cft-' + 'a' * 32 + '/child')):
                with self.subTest(path_hash=bundle.hashed(str(path).encode())):
                    with self.assertRaises(bundle.BundleRefusal):
                        bundle.root_ancestors(path)
        for mode, uid in ((stat.S_IFDIR | 0o777, 0), (stat.S_IFLNK | 0o755, 0), (stat.S_IFDIR | 0o755, 1000)):
            with self.subTest(mode=mode, uid=uid):
                with mock.patch.object(bundle.Path, 'lstat', return_value=SimpleNamespace(st_mode=mode, st_uid=uid)):
                    with self.assertRaises(bundle.BundleRefusal):
                        bundle.root_ancestors(Path('/opt/row-cft-' + 'a' * 32))

    def test_complete_layout_keeps_implicit_directories_and_zero_resource(self):
        rows = [{'path': 'chrome-linux64/locales/empty', 'kind': 'file', 'size': 0},
                {'path': 'chromedriver-linux64/', 'kind': 'directory', 'size': 0}]
        directories, files = bundle.expected_layout(rows)
        self.assertEqual(directories, {'chrome-linux64', 'chrome-linux64/locales', 'chromedriver-linux64'})
        self.assertEqual(set(files), {'chrome-linux64/locales/empty'})


class PurePublicAcquisitionTests(CFTPureFixtureCase):
    def checkpoint(self):
        return {'schema': 'row.cft-acquisition.v1', 'status': 'refused', 'complete': False,
            'phase': 'chrome-inventory', 'vendor_binary_executed': False, 'genuine_browser_qualification': False,
            'independent_vendor_signature': False, 'publisher_license_approval': False,
            'sandbox_policy_changed': False, 'readiness_credit': 0}

    def test_checkpoint_missing_final_cleanup_keeps_unknown_fields_absent(self):
        raw = bundle.packed(self.checkpoint())
        self.assertEqual(bundle.public_bytes(raw, bundle.packed(disabled())), raw)
        self.assertNotIn(b'forced_cleanup_attempted', raw)
        self.assertNotIn(b'complete_OS_descendants_proved', raw)

    def test_private_error_paths_argv_or_unknown_fields_always_refuse(self):
        for key in ('exception', 'argv', 'path', 'private_output', 'authorization', 'approval'):
            with self.subTest(field=key):
                value = self.checkpoint()
                value[key] = 'PRIVATE'
                with self.assertRaises(bundle.BundleRefusal):
                    bundle.public_bytes(bundle.packed(value), bundle.packed(disabled()))

    def test_partial_checkpoint_never_promotes_complete_credit_or_binary_execution(self):
        for key, value in (('complete', True), ('readiness_credit', 1), ('vendor_binary_executed', True),
                           ('genuine_browser_qualification', True), ('independent_vendor_signature', True),
                           ('sandbox_policy_changed', True)):
            with self.subTest(field=key):
                record = self.checkpoint()
                record[key] = value
                with self.assertRaises(bundle.BundleRefusal):
                    bundle.public_bytes(bundle.packed(record), bundle.packed(disabled()))


class MockInventoryBindingTests(CFTPureFixtureCase):
    def source_pin(self):
        return {'bytes': 64, 'sha256': 'a' * 64, 'identity': [1, 2, 64, 3, 4, 1, stat.S_IFREG | 0o400, 1000]}

    def test_bound_inventory_uses_exact_source_pin_and_post_readback(self):
        before = self.source_pin()
        observed = {'fixture': 'no vendor authority'}
        path = Path('/synthetic/archive.zip')
        with mock.patch.object(bundle, 'stable_file', side_effect=[before, before]) as read, \
             mock.patch.object(bundle, 'inventory', return_value=observed) as inventory:
            self.assertIs(bundle.bound_inventory(path, 'chrome', {key: before[key] for key in ('bytes', 'sha256')}, 30), observed)
            inventory.assert_called_once_with(path, 'chrome', 30, expected_pin=before)
            self.assertEqual(len(read.call_args_list), 2)

    def test_fetch_hash_or_size_mismatch_refuses_before_member_inventory(self):
        before = self.source_pin()
        for changed in ({'bytes': 65, 'sha256': before['sha256']}, {'bytes': 64, 'sha256': 'b' * 64}):
            with self.subTest(field_count=len(changed)):
                with mock.patch.object(bundle, 'stable_file', return_value=before), \
                     mock.patch.object(bundle, 'inventory') as inventory:
                    with self.assertRaises(bundle.BundleRefusal):
                        bundle.bound_inventory(Path('/synthetic/archive.zip'), 'chrome', changed, 30)
                    inventory.assert_not_called()

    def test_archive_change_after_member_inventory_refuses(self):
        before = self.source_pin()
        changes = [dict(before) | {'sha256': 'b' * 64}, dict(before) | {'bytes': 65},
            dict(before) | {'identity': [1, 8, 64, 3, 4, 1, stat.S_IFREG | 0o400, 1000]}]
        for changed in changes:
            with self.subTest(field_count=len(changed)):
                with mock.patch.object(bundle, 'stable_file', side_effect=[before, changed]), \
                     mock.patch.object(bundle, 'inventory', return_value={'fixture': True}):
                    with self.assertRaises(bundle.BundleRefusal):
                        bundle.bound_inventory(Path('/synthetic/archive.zip'), 'chrome',
                            {key: before[key] for key in ('bytes', 'sha256')}, 30)


class ArchiveInput(io.BytesIO):
    def fileno(self):
        return 71


class RetainedInventoryFDTests(CFTPureFixtureCase):
    def input_info(self, raw):
        return SimpleNamespace(st_dev=1, st_ino=2, st_size=len(raw), st_mtime_ns=3,
            st_ctime_ns=4, st_nlink=1, st_mode=stat.S_IFREG | 0o400, st_uid=1000)

    def source_pin(self, raw):
        info = self.input_info(raw)
        return {'bytes': len(raw), 'sha256': bundle.hashed(raw), 'identity': list(bundle.identity(info))}

    def read_inventory(self, raw, expected, *, fd_info=None):
        info = self.input_info(raw)
        with mock.patch.object(bundle.Path, 'lstat', return_value=info), \
             mock.patch.object(bundle.os, 'open', return_value=71), \
             mock.patch.object(bundle.os, 'O_NOFOLLOW', 0x20000, create=True), \
             mock.patch.object(bundle.os, 'fdopen', return_value=ArchiveInput(raw)), \
             mock.patch.object(bundle.os, 'fstat', return_value=fd_info or info), \
             mock.patch.object(bundle.time, 'monotonic', return_value=1):
            return bundle.inventory(Path('/synthetic/archive.zip'), 'chrome', 30, expected_pin=expected)

    def test_inert_timestamp_and_identity_metadata_preserves_actual_binary_inventory(self):
        payload = b'\x7fELF\x00literal\r\nbinary\n\xff'
        for compression in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
            original = synthetic_zip(compression=compression,
                names=[(bundle.EXECUTABLES['chrome'], stat.S_IFREG | 0o755, payload)])
            baseline = self.read_inventory(original, self.source_pin(original))
            for flags in (1, 3, 5, 7):
                local_ut, central_ut = timestamp_extras(flags)
                for width in (1, 4, 8):
                    ux = extra_field(0x7875, bytes([1, width]) + b'\xff' * width + bytes([width]) + b'\x00' * width)
                    for central_ux in (b'', ux):
                        with self.subTest(compression=compression, flags=flags, width=width, central_ux=bool(central_ux)):
                            raw = with_single_entry_extras(original, local_ut + ux, central_ut + central_ux)
                            result = self.read_inventory(raw, self.source_pin(raw))
                            self.assertEqual(result, baseline)
                            self.assertEqual(result['inventory'][0]['sha256'], bundle.hashed(payload))
                            self.assertNotIn('extra_metadata', result['inventory'][0])

    def test_local_only_metadata_has_no_payload_or_inventory_authority(self):
        original = synthetic_zip()
        baseline = self.read_inventory(original, self.source_pin(original))
        ux = extra_field(0x7875, b'\x01\x01\xff\x01\x00')
        for local_extra in (b'', ux):
            with self.subTest(local_extra=local_extra):
                raw = with_single_entry_extras(original, local_extra, b'')
                self.assertEqual(self.read_inventory(raw, self.source_pin(raw)), baseline)

    def test_malformed_or_unsupported_extras_refuse_before_payload_enumeration(self):
        original = synthetic_zip()
        ut, central_ut = timestamp_extras(1)
        ux = extra_field(0x7875, b'\x01\x01\xff\x01\x00')
        bad = (b'x', b'xyz', b'x' * 65, struct.pack('<2H', 0x5455, 9) + b'\x01',
            extra_field(1, b''), extra_field(0x7075, b''), extra_field(0x5455, b''),
            extra_field(0x5455, b'\x00'), extra_field(0x5455, b'\x81' + b'x' * 4),
            *(timestamp_extras(flags)[0] for flags in (2, 4, 6)),
            extra_field(0x5455, b'\x01' + b'x' * 3),
            extra_field(0x7875, b'\x02\x01x\x01y'), extra_field(0x7875, b'\x01\x00\x01y'),
            extra_field(0x7875, b'\x01\x09' + b'x' * 9 + b'\x01y'),
            extra_field(0x7875, b'\x01\x01x\x00'), extra_field(0x7875, b'\x01\x01x\x09' + b'y' * 9),
            extra_field(0x7875, b'\x01\x01x\x01'), extra_field(0x7875, b'\x01\x01x\x01yz'),
            ux + ux, ut + ut)
        for central in (False, True):
            for extra in bad:
                with self.subTest(central=central, extra=extra):
                    raw = with_single_entry_extras(original, ut if central else extra, extra if central else central_ut)
                    code = 'cft-central-extra-field-refused' if central else 'cft-local-header-layout-refused'
                    with mock.patch.object(bundle.zipfile, 'ZipFile') as enumerated, \
                         mock.patch.object(bundle, 'member_chunks') as chunks:
                        with self.assertRaisesRegex(bundle.BundleRefusal, '^' + code + '$'):
                            self.read_inventory(raw, self.source_pin(raw))
                        enumerated.assert_not_called()
                        chunks.assert_not_called()

    def test_cross_header_metadata_mismatch_refuses_before_payload(self):
        original = synthetic_zip()
        local_ut, central_ut = timestamp_extras(7)
        ux = extra_field(0x7875, b'\x01\x01x\x01y')
        pairs = ((b'', central_ut), (local_ut, b''), (b'', ux),
            (local_ut, central_ut[:-1] + b'z'), (timestamp_extras(1)[0], central_ut),
            (ux, extra_field(0x7875, b'\x01\x01x\x01z')),
            (ux, extra_field(0x7875, b'\x01\x02x\x00\x01y')))
        for local_extra, central_extra in pairs:
            with self.subTest(local_extra=local_extra, central_extra=central_extra):
                raw = with_single_entry_extras(original, local_extra, central_extra)
                with mock.patch.object(bundle.zipfile, 'ZipFile') as enumerated, \
                     mock.patch.object(bundle, 'member_chunks') as chunks:
                    with self.assertRaisesRegex(bundle.BundleRefusal, '^cft-local-header-layout-refused$'):
                        self.read_inventory(raw, self.source_pin(raw))
                    enumerated.assert_not_called()
                    chunks.assert_not_called()

    def test_multiple_entries_preserve_offsets_modes_binary_and_text_inventory(self):
        names = [(bundle.EXECUTABLES['chrome'], stat.S_IFREG | 0o755, b'\x7fELF\x00binary\r\n\xff'),
                 ('chrome-linux64/README.txt', stat.S_IFREG | 0o644, b'literal\r\ntext\n')]
        ux = extra_field(0x7875, b'\x01\x01x\x01y')
        for compression in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
            original = synthetic_zip(names=names, compression=compression)
            baseline = self.read_inventory(original, self.source_pin(original))
            for first_metadata in (False, True):
                local_ut, central_ut = timestamp_extras(7)
                local = [local_ut + ux, b''] if first_metadata else [b'', local_ut + ux]
                central = [central_ut, b''] if first_metadata else [b'', central_ut + ux]
                with self.subTest(compression=compression, first_metadata=first_metadata):
                    raw = with_entry_extras(original, local, central)
                    result = self.read_inventory(raw, self.source_pin(raw))
                    self.assertEqual(result, baseline)
                    self.assertEqual([row['sha256'] for row in result['inventory']],
                        [bundle.hashed(payload) for _name, _mode, payload in sorted(names)])
                    self.assertEqual([row['mode'] for row in result['inventory']], [0o644, 0o755])

    def test_inert_metadata_never_bypasses_actual_payload_crc(self):
        for compression in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
            with self.subTest(compression=compression):
                original = synthetic_zip(compression=compression)
                raw = bytearray(with_single_entry_extras(original, *timestamp_extras()))
                end = struct.unpack('<4s4H2IH', raw[-22:])
                wrong_crc = struct.unpack_from('<I', raw, 14)[0] ^ 1
                struct.pack_into('<I', raw, 14, wrong_crc)
                struct.pack_into('<I', raw, end[6] + 16, wrong_crc)
                raw = bytes(raw)
                with self.assertRaisesRegex(bundle.BundleRefusal, '^cft-member-size-or-crc-refused$'):
                    self.read_inventory(raw, self.source_pin(raw))

    def test_actual_retained_inventory_fd_hashes_all_synthetic_source_bytes(self):
        raw = synthetic_zip()
        result = self.read_inventory(raw, self.source_pin(raw))
        self.assertEqual(result['entries'], 1)
        self.assertEqual(result['files'], 1)
        self.assertEqual(result['inventory'][0]['sha256'], bundle.hashed(b'\x7fELFsynthetic'))
        self.assertEqual(result['inventory_sha256'], bundle.hashed(bundle.packed(result['inventory'])))

    def test_download_A_and_source_B_same_identity_refuse_before_ZIP_enumeration(self):
        raw = synthetic_zip()
        expected = self.source_pin(raw)
        expected['sha256'] = bundle.hashed(raw[:-1] + bytes([raw[-1] ^ 1]))
        with mock.patch.object(bundle.zipfile, 'ZipFile') as enumerated:
            with self.assertRaises(bundle.BundleRefusal):
                self.read_inventory(raw, expected)
            enumerated.assert_not_called()

    def test_matching_path_pin_with_changed_opened_fd_identity_refuses(self):
        raw = synthetic_zip()
        other = SimpleNamespace(**vars(self.input_info(raw)) | {'st_ino': 8})
        with mock.patch.object(bundle.zipfile, 'ZipFile') as enumerated:
            with self.assertRaises(bundle.BundleRefusal):
                self.read_inventory(raw, self.source_pin(raw), fd_info=other)
            enumerated.assert_not_called()


    def test_changed_full_source_readback_refuses_after_actual_member_inventory(self):
        raw = synthetic_zip()
        expected = self.source_pin(raw)
        changed = dict(expected) | {'sha256': 'b' * 64}
        with mock.patch.object(bundle, 'archive_stream_pin', side_effect=[expected, changed]) as source:
            with self.assertRaises(bundle.BundleRefusal):
                self.read_inventory(raw, expected)
            self.assertEqual(source.call_count, 2)


    def test_corrupt_local_header_gets_fixed_inventory_code_with_matching_source_pin(self):
        raw = bytearray(synthetic_zip())
        raw[:4] = b'BAD!'
        raw = bytes(raw)
        with self.assertRaisesRegex(bundle.BundleRefusal, '^cft-local-header-layout-refused$') as failure:
            self.read_inventory(raw, self.source_pin(raw))
        code = bundle.inventory_refusal_code(failure.exception, 'chrome-inventory')
        self.assertEqual(code, 'cft-local-header-layout-refused')
        record = PurePublicAcquisitionTests.checkpoint(self)
        record['refusal_code'] = code
        public = bundle.packed(record)
        self.assertEqual(bundle.public_bytes(public, bundle.packed(disabled())), public)
        self.assertFalse(record['complete'])
        self.assertFalse(record['vendor_binary_executed'])
        self.assertEqual(record['readiness_credit'], 0)

    def test_deflate_option_archives_keep_full_inventory_and_payload_hashes(self):
        original = synthetic_zip(compression=zipfile.ZIP_DEFLATED)
        baseline = self.read_inventory(original, self.source_pin(original))
        for options in (0, 2, 4, 6):
            for base in (0, 0x800):
                with self.subTest(options=options, base=base):
                    raw = bytearray(original)
                    end = struct.unpack('<4s4H2IH', raw[-22:])
                    struct.pack_into('<H', raw, 6, base | options)
                    struct.pack_into('<H', raw, end[6] + 8, base | options)
                    raw = bytes(raw)
                    result = self.read_inventory(raw, self.source_pin(raw))
                    self.assertEqual(result, baseline)
                    self.assertEqual(result['inventory'][0]['sha256'], bundle.hashed(b'\x7fELFsynthetic'))

    def test_deflate_options_do_not_allow_local_and_central_flag_mismatch(self):
        for options in (0, 2, 4, 6):
            with self.subTest(options=options):
                raw = bytearray(synthetic_zip(compression=zipfile.ZIP_DEFLATED))
                end = struct.unpack('<4s4H2IH', raw[-22:])
                struct.pack_into('<H', raw, 6, options ^ 2)
                struct.pack_into('<H', raw, end[6] + 8, options)
                raw = bytes(raw)
                with self.assertRaisesRegex(bundle.BundleRefusal, '^cft-local-header-layout-refused$'):
                    self.read_inventory(raw, self.source_pin(raw))

    def test_deflate_options_do_not_bypass_actual_payload_crc_validation(self):
        for options in (0, 2, 4, 6):
            with self.subTest(options=options):
                raw = bytearray(synthetic_zip(compression=zipfile.ZIP_DEFLATED))
                end = struct.unpack('<4s4H2IH', raw[-22:])
                wrong_crc = struct.unpack_from('<I', raw, 14)[0] ^ 1
                struct.pack_into('<H', raw, 6, options)
                struct.pack_into('<H', raw, end[6] + 8, options)
                struct.pack_into('<I', raw, 14, wrong_crc)
                struct.pack_into('<I', raw, end[6] + 16, wrong_crc)
                raw = bytes(raw)
                with self.assertRaisesRegex(bundle.BundleRefusal, '^cft-member-size-or-crc-refused$'):
                    self.read_inventory(raw, self.source_pin(raw))

    def test_internal_text_hint_preserves_full_binary_and_text_payload_inventory(self):
        names = [(bundle.EXECUTABLES['chrome'], stat.S_IFREG | 0o755,
                  b'\x7fELF\x00literal\r\nbinary\n\xff'),
                 ('chrome-linux64/README.txt', stat.S_IFREG | 0o644, b'literal\r\ntext\n')]
        for compression in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
            original = synthetic_zip(names=names, compression=compression)
            expected = self.read_inventory(original, self.source_pin(original))
            for hint in (0, 1):
                with self.subTest(compression=compression, hint=hint):
                    raw = bytearray(original)
                    end = struct.unpack('<4s4H2IH', raw[-22:])
                    offset = end[6]
                    for _ in names:
                        header = struct.unpack_from('<4s6H3I5H2I', raw, offset)
                        struct.pack_into('<H', raw, offset + 36, hint)
                        offset += 46 + header[10] + header[11] + header[12]
                    self.assertEqual(offset, end[6] + end[5])
                    raw = bytes(raw)
                    result = self.read_inventory(raw, self.source_pin(raw))
                    self.assertEqual(result, expected)
                    self.assertEqual([row['sha256'] for row in result['inventory']],
                                     [bundle.hashed(payload) for _name, _mode, payload in sorted(names)])

    def test_internal_text_hint_does_not_bypass_actual_payload_crc_validation(self):
        for compression in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
            with self.subTest(compression=compression):
                raw = bytearray(synthetic_zip(compression=compression))
                end = struct.unpack('<4s4H2IH', raw[-22:])
                wrong_crc = struct.unpack_from('<I', raw, 14)[0] ^ 1
                struct.pack_into('<H', raw, end[6] + 36, 1)
                struct.pack_into('<I', raw, 14, wrong_crc)
                struct.pack_into('<I', raw, end[6] + 16, wrong_crc)
                raw = bytes(raw)
                with self.assertRaisesRegex(bundle.BundleRefusal, '^cft-member-size-or-crc-refused$'):
                    self.read_inventory(raw, self.source_pin(raw))


class FinalAcquisitionRecordTests(CFTPureFixtureCase):
    def checkpoint(self):
        return PurePublicAcquisitionTests.checkpoint(self)
    def final_input(self):
        record = self.checkpoint()
        record.update(phase='cleanup', source_unchanged=True, private_acquisition_root_removed=True,
            forced_cleanup_attempted=False, all_retained_zero_reaped=True, observed_groups_gone=True,
            complete_OS_descendants_proved=False, elapsed_ms=1,
            binding={'source_head': '1' * 40, 'source_tree': '2' * 40, 'event_sha': '3' * 40,
                'source_bytes_sha256': '4' * 64, 'workflow_sha256': '5' * 64,
                'run_id': '1', 'run_attempt': '1', 'image_version': '20261006.1', 'image_os': 'ubuntu24'})
        acquired = {'version': bundle.VERSION, 'platform': 'linux64', 'metadata': {'bytes': 2, 'sha256': '0' * 64},
            'policy_sha256': bundle.hashed(bundle.packed(disabled())),
            'origin_evidence': 'certificate-and-hostname-verified-official-HTTPS',
            'independent_vendor_signature': False, 'publisher_license_approval': False,
            'vendor_binary_executed': False, 'sandbox_policy_changed': False,
            'genuine_browser_qualification': False, 'readiness_credit': 0, 'archives': {}}
        for asset in bundle.ASSETS:
            rows = [{'path': bundle.EXECUTABLES[asset], 'kind': 'file', 'size': 1,
                'compressed_size': 1, 'mode': 0o755, 'sha256': 'a' * 64}]
            acquired['archives'][asset] = {'url': bundle.asset_url(bundle.VERSION, asset), 'bytes': 22,
                'sha256': 'b' * 64, 'entries': 1, 'files': 1, 'unpacked_bytes': 1,
                'inventory': rows, 'inventory_sha256': bundle.hashed(bundle.packed(rows))}
        return record, acquired

    def test_completion_requires_final_cleanup_and_validates_before_promoting(self):
        record, acquired = self.final_input()
        original = dict(record)
        final = bundle.finish_acquisition(record, acquired, bundle.packed(disabled()))
        self.assertTrue(final['complete'])
        self.assertEqual(bundle.public_bytes(bundle.packed(final), bundle.packed(disabled())), bundle.packed(final))
        self.assertEqual(record, original)

    def test_interrupted_or_failed_cleanup_retains_valid_incomplete_checkpoint(self):
        for key in ('private_acquisition_root_removed', 'all_retained_zero_reaped', 'observed_groups_gone', 'elapsed_ms'):
            with self.subTest(field=key):
                record, acquired = self.final_input()
                record.pop(key)
                original = dict(record)
                with self.assertRaises(bundle.BundleRefusal):
                    bundle.finish_acquisition(record, acquired, bundle.packed(disabled()))
                self.assertEqual(record, original)
                self.assertFalse(record['complete'])
                self.assertNotIn('acquisition', record)
                self.assertEqual(bundle.public_bytes(bundle.packed(record), bundle.packed(disabled())), bundle.packed(record))
    def test_failed_final_facts_never_promote_the_input_record(self):
        for key, value in (('source_unchanged', False), ('private_acquisition_root_removed', False),
                ('forced_cleanup_attempted', True), ('all_retained_zero_reaped', False),
                ('observed_groups_gone', False), ('complete_OS_descendants_proved', True),
                ('elapsed_ms', 300000)):
            with self.subTest(field=key):
                record, acquired = self.final_input()
                record[key] = value
                original = dict(record)
                with self.assertRaises(bundle.BundleRefusal):
                    bundle.finish_acquisition(record, acquired, bundle.packed(disabled()))
                self.assertEqual(record, original)
                self.assertFalse(record['complete'])
                self.assertNotIn('acquisition', record)


class InventoryRefusalDiagnosticTests(CFTPureFixtureCase):
    def test_central_format_fields_get_fixed_codes_before_name_parsing(self):
        raw = synthetic_zip()
        footer = raw[-22:]
        end = struct.unpack('<4s4H2IH', footer)
        central = raw[end[6]:end[6] + end[5]]
        original = list(struct.unpack('<4s6H3I5H2I', central[:46]))
        cases = (
            (0, b'BAD!', 'cft-central-signature-refused'),
            (1, 20, 'cft-central-creator-system-refused'),
            (2, 21, 'cft-central-extract-version-refused'),
            (3, 1, 'cft-central-flag-bit-0-refused'),
            (4, 9, 'cft-central-compression-refused'),
            (12, 1, 'cft-central-comment-refused'),
            (13, 1, 'cft-central-disk-refused'),
            (14, 2, 'cft-central-internal-attributes-refused'),
            (11, 1, 'cft-central-extra-field-refused'),
        )
        for index, value, code in cases:
            with self.subTest(field=index):
                header = original.copy()
                header[index] = value
                changed = struct.pack('<4s6H3I5H2I', *header) + central[46:]
                with mock.patch.object(bundle, 'member_name') as member:
                    with self.assertRaisesRegex(bundle.BundleRefusal, '^' + code + '$') as failure:
                        bundle.central_plan(footer, changed, len(raw), 'chrome')
                    member.assert_not_called()
                for phase in bundle.INVENTORY_PHASES:
                    self.assertEqual(bundle.inventory_refusal_code(failure.exception, phase), code)
                    record = PurePublicAcquisitionTests.checkpoint(self)
                    record.update(phase=phase, refusal_code=code)
                    public = bundle.packed(record)
                    self.assertEqual(bundle.public_bytes(public, bundle.packed(disabled())), public)
                    self.assertFalse(record['complete'])
                    self.assertFalse(record['vendor_binary_executed'])
                    self.assertFalse(record['genuine_browser_qualification'])
                    self.assertEqual(record['readiness_credit'], 0)

    def test_central_format_refusals_keep_original_first_failure_order(self):
        raw = synthetic_zip()
        footer = raw[-22:]
        end = struct.unpack('<4s4H2IH', footer)
        central = raw[end[6]:end[6] + end[5]]
        header = list(struct.unpack('<4s6H3I5H2I', central[:46]))
        original = header.copy()
        cases = (
            (0, b'BAD!', 'cft-central-signature-refused'),
            (1, 20, 'cft-central-creator-system-refused'),
            (2, 21, 'cft-central-extract-version-refused'),
            (3, 1, 'cft-central-flag-bit-0-refused'),
            (4, 9, 'cft-central-compression-refused'),
            (12, 1, 'cft-central-comment-refused'),
            (13, 1, 'cft-central-disk-refused'),
            (14, 2, 'cft-central-internal-attributes-refused'),
            (11, 1, 'cft-central-extra-field-refused'),
        )
        for index, value, _code in cases:
            header[index] = value
        for index, _value, code in cases:
            with self.subTest(first_remaining_field=index):
                changed = struct.pack('<4s6H3I5H2I', *header) + central[46:]
                with self.assertRaisesRegex(bundle.BundleRefusal, '^' + code + '$'):
                    bundle.central_plan(footer, changed, len(raw), 'chrome')
                header[index] = original[index]
        self.assertEqual(bundle.central_plan(footer, central, len(raw), 'chrome'), plan(raw))

    def test_central_format_diagnostics_preserve_accepted_header_variants(self):
        raw = synthetic_zip()
        footer = raw[-22:]
        end = struct.unpack('<4s4H2IH', footer)
        central = raw[end[6]:end[6] + end[5]]
        original = list(struct.unpack('<4s6H3I5H2I', central[:46]))
        expected, expected_offset = plan(raw)
        for version in (0, 10, 20):
            for creator_version in (0, 20, 255):
                for flags in (0, 8, 0x800, 0x808):
                    for method in (0, 8):
                        with self.subTest(version=version, creator=creator_version, flags=flags, method=method):
                            header = original.copy()
                            header[1:5] = [(3 << 8) | creator_version, version, flags, method]
                            changed = struct.pack('<4s6H3I5H2I', *header) + central[46:]
                            rows, offset = bundle.central_plan(footer, changed, len(raw), 'chrome')
                            self.assertEqual(offset, expected_offset)
                            self.assertEqual(rows, [dict(expected[0], flags=flags, method=method)])

    def test_internal_text_hint_preserves_binary_central_plans(self):
        for asset in ('chrome', 'chromedriver'):
            for compression in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                original = synthetic_zip(asset=asset, compression=compression)
                expected = plan(original, asset)
                end = struct.unpack('<4s4H2IH', original[-22:])
                for hint in (0, 1):
                    with self.subTest(asset=asset, compression=compression, hint=hint):
                        raw = bytearray(original)
                        struct.pack_into('<H', raw, end[6] + 36, hint)
                        self.assertEqual(plan(bytes(raw), asset), expected)

    def test_other_internal_attribute_bits_refuse_before_name_parsing(self):
        for compression in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
            original = synthetic_zip(compression=compression)
            footer = original[-22:]
            end = struct.unpack('<4s4H2IH', footer)
            central = original[end[6]:end[6] + end[5]]
            for bit in range(1, 16):
                for hint in (0, 1):
                    with self.subTest(compression=compression, bit=bit, hint=hint):
                        changed = bytearray(central)
                        struct.pack_into('<H', changed, 36, hint | (1 << bit))
                        with mock.patch.object(bundle, 'member_name') as member:
                            with self.assertRaisesRegex(bundle.BundleRefusal,
                                    '^cft-central-internal-attributes-refused$'):
                                bundle.central_plan(footer, bytes(changed), len(original), 'chrome')
                            member.assert_not_called()

    def test_all_fixed_inventory_codes_round_trip_only_as_incomplete_inventory_refusals(self):
        self.assertEqual(len(bundle.INVENTORY_REFUSAL_CODES), 70)
        for phase in bundle.INVENTORY_PHASES:
            for code in sorted(bundle.INVENTORY_REFUSAL_CODES):
                with self.subTest(phase=phase, code=code):
                    error = bundle.BundleRefusal(code)
                    self.assertEqual(bundle.inventory_refusal_code(error, phase), code)
                    record = PurePublicAcquisitionTests.checkpoint(self)
                    record.update(phase=phase, refusal_code=code)
                    raw = bundle.packed(record)
                    self.assertEqual(bundle.public_bytes(raw, bundle.packed(disabled())), raw)
                    self.assertFalse(record['complete'])
                    self.assertFalse(record['genuine_browser_qualification'])
                    self.assertEqual(record['readiness_credit'], 0)

    def test_unknown_nonexact_or_private_exception_values_never_get_stringified(self):
        class PrivateRuntimeError(RuntimeError):
            def __str__(self):
                raise AssertionError('exception stringification forbidden')
        class DerivedRefusal(bundle.BundleRefusal):
            def __str__(self):
                raise AssertionError('derived exception stringification forbidden')
        class PrivateString(str):
            def __hash__(self):
                raise AssertionError('nonexact string hashing forbidden')
        errors = (PrivateRuntimeError('/PRIVATE/error'), bundle.BundleRefusal('/PRIVATE/path'),
            bundle.BundleRefusal('cft-ZIP-footer-refused', '/PRIVATE/extra'), bundle.BundleRefusal(),
            bundle.BundleRefusal(True), bundle.BundleRefusal(['/PRIVATE/list']),
            bundle.BundleRefusal(PrivateString('cft-ZIP-footer-refused')),
            DerivedRefusal('cft-ZIP-footer-refused'))
        for index, error in enumerate(errors):
            with self.subTest(index=index):
                code = bundle.inventory_refusal_code(error, 'chrome-inventory')
                self.assertEqual(code, 'cft-inventory-runtime-refused')
                record = PurePublicAcquisitionTests.checkpoint(self)
                record['refusal_code'] = code
                raw = bundle.packed(record)
                self.assertEqual(bundle.public_bytes(raw, bundle.packed(disabled())), raw)
                self.assertNotIn(b'PRIVATE', raw)
        for bad in ('/PRIVATE/path', True, None, 5, ['cft-ZIP-footer-refused']):
            with self.subTest(type_name=type(bad).__name__):
                record = PurePublicAcquisitionTests.checkpoint(self)
                record['refusal_code'] = bad
                with self.assertRaises(bundle.BundleRefusal):
                    bundle.public_bytes(bundle.packed(record), bundle.packed(disabled()))

    def test_other_phases_keep_generic_code_and_refuse_inventory_predicate_projection(self):
        for phase in bundle.ACQUISITION_PHASES:
            if phase in bundle.INVENTORY_PHASES:
                continue
            with self.subTest(phase=phase):
                error = bundle.BundleRefusal('cft-local-header-layout-refused')
                self.assertEqual(bundle.inventory_refusal_code(error, phase), 'cft-acquisition-refused')
                record = PurePublicAcquisitionTests.checkpoint(self)
                record.update(phase=phase, refusal_code='cft-local-header-layout-refused')
                with self.assertRaises(bundle.BundleRefusal):
                    bundle.public_bytes(bundle.packed(record), bundle.packed(disabled()))
                record['refusal_code'] = 'cft-acquisition-refused'
                raw = bundle.packed(record)
                self.assertEqual(bundle.public_bytes(raw, bundle.packed(disabled())), raw)
        for phase in (None, True, ['chrome-inventory'], '/PRIVATE/phase'):
            with self.subTest(type_name=type(phase).__name__):
                self.assertEqual(bundle.inventory_refusal_code(error, phase), 'cft-acquisition-refused')

    def test_inventory_diagnostic_cannot_promote_completion_or_any_authority(self):
        for key, value in (('complete', True), ('vendor_binary_executed', True),
                ('genuine_browser_qualification', True), ('independent_vendor_signature', True),
                ('publisher_license_approval', True), ('sandbox_policy_changed', True), ('readiness_credit', 1)):
            with self.subTest(field=key):
                record = PurePublicAcquisitionTests.checkpoint(self)
                record.update(refusal_code='cft-local-header-layout-refused')
                record[key] = value
                with self.assertRaises(bundle.BundleRefusal):
                    bundle.public_bytes(bundle.packed(record), bundle.packed(disabled()))

    def test_central_name_span_fixed_predicate_refuses_before_member_name_parser(self):
        raw = synthetic_zip()
        footer = raw[-22:]
        end = struct.unpack('<4s4H2IH', footer)
        central = raw[end[6]:end[6] + end[5]]
        header = list(struct.unpack('<4s6H3I5H2I', central[:46]))
        header[10] = bundle.MAX_NAME + 1
        changed = struct.pack('<4s6H3I5H2I', *header) + central[46:]
        with mock.patch.object(bundle, 'member_name') as member:
            with self.assertRaisesRegex(bundle.BundleRefusal, '^cft-central-name-span-refused$') as failure:
                bundle.central_plan(footer, changed, len(raw), 'chrome')
            member.assert_not_called()
        self.assertEqual(bundle.inventory_refusal_code(failure.exception, 'chromedriver-inventory'),
            'cft-central-name-span-refused')

    def test_each_forbidden_central_flag_bit_refuses_before_name_parsing(self):
        raw = synthetic_zip()
        footer = raw[-22:]
        end = struct.unpack('<4s4H2IH', footer)
        central = raw[end[6]:end[6] + end[5]]
        original = list(struct.unpack('<4s6H3I5H2I', central[:46]))
        for bit in (0, 1, 2, 4, 5, 6, 7, 8, 9, 10, 12, 13, 14, 15):
            for allowed in (0, 8, 0x800, 0x808):
                with self.subTest(bit=bit, allowed=allowed):
                    header = original.copy()
                    header[3] = allowed | (1 << bit)
                    changed = struct.pack('<4s6H3I5H2I', *header) + central[46:]
                    code = (f'cft-central-stored-flag-bit-{bit}-refused' if bit in (1, 2)
                            else f'cft-central-flag-bit-{bit}-refused')
                    with mock.patch.object(bundle, 'member_name') as member:
                        with self.assertRaisesRegex(bundle.BundleRefusal, '^' + code + '$') as failure:
                            bundle.central_plan(footer, changed, len(raw), 'chrome')
                        member.assert_not_called()
                    for phase in bundle.INVENTORY_PHASES:
                        self.assertEqual(bundle.inventory_refusal_code(failure.exception, phase), code)

    def test_multiple_forbidden_bits_report_lowest_bit_before_compression(self):
        raw = synthetic_zip()
        footer = raw[-22:]
        end = struct.unpack('<4s4H2IH', footer)
        central = raw[end[6]:end[6] + end[5]]
        original = list(struct.unpack('<4s6H3I5H2I', central[:46]))
        for flags, first in ((3, 0), (6, 1), (0xFFF7, 0), (0x9000, 12)):
            with self.subTest(flags=flags):
                header = original.copy()
                header[3:5] = [flags, 9]
                changed = struct.pack('<4s6H3I5H2I', *header) + central[46:]
                with self.assertRaisesRegex(bundle.BundleRefusal, f'^cft-central-flag-bit-{first}-refused$'):
                    bundle.central_plan(footer, changed, len(raw), 'chrome')

    def test_deflate_compression_options_preserve_all_central_flag_combinations(self):
        # Central parsing only; complete local/payload validity is tested separately.
        raw = synthetic_zip(compression=zipfile.ZIP_DEFLATED)
        footer = raw[-22:]
        end = struct.unpack('<4s4H2IH', footer)
        central = raw[end[6]:end[6] + end[5]]
        original = list(struct.unpack('<4s6H3I5H2I', central[:46]))
        for options in (0, 2, 4, 6):
            for base in (0, 8, 0x800, 0x808):
                with self.subTest(options=options, base=base):
                    header = original.copy()
                    header[3] = base | options
                    changed = struct.pack('<4s6H3I5H2I', *header) + central[46:]
                    rows, _ = bundle.central_plan(footer, changed, len(raw), 'chrome')
                    self.assertEqual(rows[0]['flags'], base | options)
                    self.assertEqual(rows[0]['method'], 8)

    def test_deflate_options_never_allow_other_forbidden_bits(self):
        raw = synthetic_zip(compression=zipfile.ZIP_DEFLATED)
        footer = raw[-22:]
        end = struct.unpack('<4s4H2IH', footer)
        central = raw[end[6]:end[6] + end[5]]
        original = list(struct.unpack('<4s6H3I5H2I', central[:46]))
        for bit in (0, 4, 5, 6, 7, 8, 9, 10, 12, 13, 14, 15):
            for options in (0, 2, 4, 6):
                for base in (0, 8, 0x800, 0x808):
                    with self.subTest(bit=bit, options=options, base=base):
                        header = original.copy()
                        header[3] = base | options | (1 << bit)
                        changed = struct.pack('<4s6H3I5H2I', *header) + central[46:]
                        code = f'cft-central-flag-bit-{bit}-refused'
                        with mock.patch.object(bundle, 'member_name') as member:
                            with self.assertRaisesRegex(bundle.BundleRefusal, '^' + code + '$'):
                                bundle.central_plan(footer, changed, len(raw), 'chrome')
                            member.assert_not_called()


if __name__ == '__main__':
    unittest.main()
