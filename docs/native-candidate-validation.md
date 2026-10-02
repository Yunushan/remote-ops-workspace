# Native candidate validation

The `Native PR candidate validation` workflow builds and tests unreleased native
packages. Its token has read access, and its outputs are Actions artifacts.
Passing this workflow does not approve publication or establish publisher trust.

## Run a candidate

Changes to native build inputs run Windows x64 validation on the exact pull
request head commit. The workflow records the event commit separately, along
with the checkout tree, file hashes, workflow identity and run attempt.

Apply the `native-all-modern` label to the pull request to request all seven
modern targets. Once the workflow is available on the default branch, its manual
run also offers `windows-x64` and `all-modern` scopes and accepts an exact source
commit. The broad scope uses hosted Windows, macOS and Linux runners.

| Targets | Packaged runtime contract |
| --- | --- |
| Windows x64 and ARM64 | CLI, EXE/MSI installation, and native Qt GUI startup/profile selection/paint |
| macOS x64 and ARM64 | DMG/PKG installation and native Qt GUI startup/profile selection/paint |
| Windows x86 | CLI and EXE/MSI installation; maintained vault backends unavailable and fail closed |
| Linux x86_64 and aarch64 | CLI and DEB/RPM/AppImage installation; these packages do not include Qt |

## Read the evidence

Candidate artifacts include source fingerprints, realized Python distributions,
native package hashes, PyInstaller archive inventories and native smoke results.
Windows smoke compares executable bytes in portable, EXE and MSI locations to
the inspected build outputs before launching them. Modern macOS smoke compares
the executable in each DMG and PKG copy to the original signed app executable
before its runtime and GUI probes. Modern Linux smoke compares installed DEB and
RPM executables to the original PyInstaller executable before each probe.

AppImage smoke checks the copied AppImage bytes before extraction, then checks
the extracted executable and AppRun before invoking that same extracted AppRun.
The launcher is also bound to its generated build source. The existing 32-bit
Linux smoke keeps its separate runtime method and makes no new binding claim.
`finish.json` requires the binding report for every modern target, including all
required install and same-candidate reinstall probes. A successful smoke with
missing or mismatched binding evidence fails validation.

These are candidate-produced hashes taken immediately before launch. They do
not protect against a hostile file replacement between checking and launching,
or establish a complete external runtime inventory or independent license
approval. Parsing the original PyInstaller archive has the same limits.

Windows commands run hidden in an owned Job Object with bounded cleanup. A
failed original GUI smoke remains failed when a separate console diagnostic is
built; the diagnostic has its own filename, hash, outcome and logs.

Full Windows installer smoke refuses local and self-hosted execution and an
existing application installation. Its directory removal checks stay within the
checkout's smoke directory. Successful runs verify their normal uninstalls.
Failure or timeout relies on disposal of the hosted runner; an incomplete run
does not prove installer rollback or successful cleanup outside the owned Job.
macOS and Linux failure cleanup has the same hosted-runner disposal boundary.

## Remaining production requirements

The existing reinstall smoke repeats the same candidate. Genuine upgrade and
rollback from a previous native release require a separate transition drill.
The Windows x64 lane includes a guarded Inno drill using the pinned v1.0.24
installer and portable executable bytes. It checks actual previous/candidate/
previous CLI state and vault reads, encrypted full-state backup and recovery,
and unchanged source/package bytes. Its dry regressions do not establish a
successful native transition; read `native-upgrade-rollback.json` and its owned
cleanup result from the actual runner. Only sanitized reports are uploaded.
The private synthetic state and installer logs stay outside artifact paths.
MSI, ARM, macOS and Linux previous-version transitions remain separate work.
macOS uses ad-hoc signing here, without publisher identity or notarization.
These checks do not establish Windows Smart App Control acceptance, independent
redistribution approval, complete supported-host workflows, or production
readiness of published v1.0.27. Existing unsigned self-service releases remain
available through the versioned unsigned release workflow.
