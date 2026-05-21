# File Transfer

Remote Ops Workspace uses OpenSSH `sftp` for file browsing, one-shot file
operations and queued transfer batches. Commands are built as argv lists, and
batch operations are sent to `sftp -b -` through stdin.

## One-Shot Actions

```bash
row files open lab-ssh --dry-run
row files ls lab-ssh /var/log --dry-run
row files get lab-ssh /etc/hosts --local ./hosts.copy --dry-run
row files put lab-ssh ./build.tar.gz --remote /tmp/build.tar.gz --dry-run
row files mkdir lab-ssh /tmp/releases --dry-run
row files rename lab-ssh /tmp/old /tmp/new --dry-run
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
