# File Transfer

Remote Ops Workspace uses OpenSSH `sftp` for file browsing, one-shot file
operations and queued transfer batches. Commands are built as argv lists, and
batch operations are sent to `sftp -b -` through stdin.

Opening the MobaXterm-style SFTP browser from an SSH profile reuses the same
profile parameters by switching only the protocol to `sftp`. User, host, port,
identity file, proxy jump, certificate file, PKCS#11 provider, smart-card
provider metadata and SSH agent handoff options are preserved in the generated
SFTP launch plan.

## One-Shot Actions

```bash
row files open lab-ssh --dry-run
row files ls lab-ssh /var/log --dry-run
row files get lab-ssh /etc/hosts --local ./hosts.copy --dry-run
row files put lab-ssh ./build.tar.gz --remote /tmp/build.tar.gz --dry-run
row files mkdir lab-ssh /tmp/releases --dry-run
row files rename lab-ssh /tmp/old /tmp/new --dry-run
```

Execution safety:

- `ls`, `open`, previews, `mkdir` and downloads to a new local target do not
  require `--force`.
- `put` always requires `--force` for real execution because OpenSSH `sftp`
  does not provide a no-clobber upload mode.
- `get` requires `--force` only when the local destination already exists or
  when a remote glob makes the local overwrite target unpredictable.
- `rm`, `rmdir`, `rename` and destructive queue batches require `--force` for
  real execution. `--dry-run` can still show the generated batch first.
- Destructive remote paths reject overly broad targets such as `/`, `.`, `~`,
  parent-directory traversal and glob patterns even when `--force` is used.

```bash
row files rm lab-ssh /tmp/old.txt --dry-run
row files rm lab-ssh /tmp/old.txt --force
row files put lab-ssh ./build.tar.gz --remote /tmp/build.tar.gz --force
```

## Transfer Queues

Use `row files queue` when several actions should be reviewed or executed as one
SFTP batch.

```bash
row files queue lab-ssh \
  --op "get /etc/hosts ./hosts.copy" \
  --op "put --recursive ./build /tmp/build" \
  --op "mkdir /tmp/releases" \
  --dry-run
```

Add `--force` only when executing a queue that contains uploads, deletes,
renames, existing local download targets or remote globs:

```bash
row files queue lab-ssh \
  --op "rm /tmp/old.txt" \
  --op "put ./build.tar.gz /tmp/build.tar.gz" \
  --force
```

Supported queue operations:

| Operation | Example |
|---|---|
| `get` | `get /etc/hosts ./hosts.copy` |
| `put` | `put ./build.tar.gz /tmp/build.tar.gz` |
| recursive `get`/`put` | `get --recursive /var/log ./logs` |
| `mkdir` | `mkdir /tmp/releases` |
| `rm` | `rm /tmp/old.txt` |
| `rmdir` | `rmdir /tmp/old-dir` |
| `rename` | `rename /tmp/old /tmp/new` |

Machine-readable queue output:

```bash
row files queue lab-ssh --op "get /etc/hosts ./hosts.copy" --dry-run --json
```

## Previews

Local previews inspect files without launching external tools:

```bash
row files preview-local ./README.md --bytes 2048
row files preview-local ./downloads --entries 25 --json
```

Remote previews use SFTP `ls -la`:

```bash
row files preview-remote lab-ssh /var/log --dry-run
```

The desktop GUI includes a transfer queue preview dialog for SSH/SFTP profiles.
It builds the same queue plan as the CLI, shows the generated SFTP batch commands,
and can preview local files/directories before an operator runs the transfer path.
