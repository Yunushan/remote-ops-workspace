# Team sync proof-of-concept

The `team-sync` CLI provides a versioned shared profile catalogue for a mounted
directory such as an SMB share, a cloud-synchronised team folder or a controlled
WebDAV mount. It is a metadata-only proof-of-concept: credentials, private-key
and machine-local paths, executable commands, URL credentials/paths/query
strings/fragments, port forwards, agent forwarding, trusted X11 forwarding,
host-key-check disabling, unknown option payloads and sensitive free-form or
option values do not leave the local workspace. Custom, local-shell and serial
profiles are local-only and are therefore omitted from published records.

```powershell
row team-sync status --root \\fileserver\remote-ops-team --team operators
row team-sync push --root \\fileserver\remote-ops-team --team operators --expected-version 0
row team-sync pull --root \\fileserver\remote-ops-team --team operators
```

Publishing uses optimistic version control. A client must push the version it
read; if another client has published first, the stale client receives a
conflict and must pull before retrying. A persistent cross-platform advisory
lock file serializes the check-and-write phase, preventing two writers from
publishing the same version concurrently. The operating system releases the
lock when a process exits, so a crash does not leave a permanent busy sentinel.
The mounted filesystem must provide working `flock` (POSIX) or Windows byte-range
lock semantics; mounts that do not propagate advisory locks are unsupported for
concurrent publishers.

On POSIX, the team root must be provisioned by an administrator before the
first command. It must grant its selected group read/write/traverse access,
carry the setgid bit so every writer inherits the same group, and must not grant
any access to other users (for example, a group-owned `2770` directory). The
root and its parents must already exist; the application creates no POSIX path
components. Remote Ops
Workspace deliberately does not guess or change a team GID. Records and lock
files are `0660`, and every read/write verifies that their GID still matches
the root. A missing, non-setgid or group-inconsistent root fails closed. On
Windows, the backend can create the directory, but the operator remains
responsible for a suitable shared-folder ACL.

Normal pulls merge remote metadata by profile name. A local credential reference
or identity-file path is retained only when the profile's public connection
binding (protocol, host, port, username, URL and routing/options) is unchanged;
changing that binding detaches the local credential instead of silently sending
it to a new endpoint. Pull also refuses a changed/new profile that would inherit
credential material from a local group default. `--replace` deliberately
replaces the local profile collection and should only be used when local-only
profiles have been backed up.

The mounted-directory record is not cryptographically signed. Treat access to
the shared directory as profile-catalogue administration: someone who can
modify it can still change ordinary connection metadata such as a destination
host or username. The reader rejects links, non-regular/oversized files,
non-canonical container metadata and executable or local-only profile fields,
but storage ACLs and an operator review remain the integrity boundary.
