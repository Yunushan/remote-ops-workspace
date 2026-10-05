# Unsigned runtime observations

The native candidate workflow captures observed package, metadata and license
bytes after successful build, smoke and finish checks. The resulting bundle is
**unsigned and unapproved**. It does not authorize release promotion or satisfy
the production compliance gate.

## Public input eligibility

The collection step requires the actual repository event visibility to be
public. The workflow checks out the exact candidate SHA with credentials
disabled and uses a fresh candidate virtual environment. Python installation
uses the existing complete hash locks, pip's isolated mode and an explicit
public PyPI index. Per-platform PIP_CONFIG_FILE equals Python's null-device
spelling (Windows: `nul`; POSIX: `/dev/null`), disabling configuration
files. The project installs directly from its bound public checkout with no
dependency resolution or build isolation.

These pip behaviors are described in the official
[configuration documentation](https://pip.pypa.io/en/stable/topics/configuration/)
and [isolated option](https://pip.pypa.io/en/stable/cli/pip/).
Do not add private package indices, unbound source inputs or local-environment
capture to this lane.

The CLI also requires a GitHub-hosted runner, the current run/attempt identity,
matching target and builder version, unchanged source fingerprints and exact
finish/pip-inspect/CArchive/asset hashes. Known URL fields reject credentials,
queries and fragments; direct source URLs must name the bound checkout.
Upstream pip metadata retains free-form fields, so this is not a universal
metadata sanitizer. Raw transport receipts contribute validated facts/hashes,
not arbitrary extra fields.

## Bundle and verification

Target directories are new and plain; existing output is never overwritten:

```text
candidate-runtime-inventory/<target>/observations.json
candidate-runtime-inventory/<target>/raw/pip-inspect.json
candidate-runtime-inventory/<target>/files/licenses/<content-sha256>.bin
candidate-runtime-inventory/<target>/COMPLETE-OBSERVATIONS-ONLY
```

The final marker means observation writing finished. It does not mean the
runtime inventory is complete or approved. Failed staging lacks the marker.
All actual pip-inspect distributions are retained and checked against installed
metadata. Actual license bytes are copied and content-deduplicated. The existing
compliance checker can verify those copied bytes and exact pip-inspect digest;
it still rejects the collector's incomplete/unapproved inventory.

Every bound source/input/asset is rechecked after parsing. This is a local
receipt/byte check, not an independent hosted attestation or hostile race
guarantee. Windows receipt separators normalize only typed asset/CArchive
receipt paths. Archive, source and output paths keep strict traversal, device,
duplicate, link and alias checks.

## Supported observations and remaining work

- ZIP32, ordinary bounded TAR, DEB ar/data.tar, gzip/xz/bzip2 RPM/CPIO and
  executable CArchive cookie/TOC bytes are parsed without native execution,
  archive commands or filesystem extraction.
- MSI, Inno EXE, DMG, PKG and AppImage are explicitly opaque. RPM zstd, archive
  links, PAX metadata and unsupported codecs remain explicit gaps. Observing a
  companion ZIP/TAR cannot establish the opaque package's contents.
- CPython facts describe the builder; the packaged interpreter identity/version
  remains unverified. CArchive facts do not prove bootloader version, PYZ
  ownership or complete external host dependencies.
- Native PE/ELF/Mach-O files retain content hashes with unknown identities,
  versions, license expressions and bundled/build-only classifications.

Classification, corresponding-source/relink obligations, complete extraction
of every package, exact component versions and genuine independent review
remain required. Every global completeness/classification/approval/signature
flag remains false. No approver key, signature or invented approval is supplied.

The production gate still requires its protected-platform 4/4 and strict
MobaXterm 8/8 accepted records, trusted distribution and immutable exact-artifact
promotion/provenance. Sole-developer unsigned previews retain their existing
self-service release workflow.
