# Team sync proof-of-concept

The `team-sync` CLI provides a versioned shared profile catalogue for a mounted
directory such as an SMB share, a cloud-synchronised team folder or a controlled
WebDAV mount. It is a metadata-only proof-of-concept: credentials, private-key
paths and sensitive option values do not leave the local workspace.

```powershell
row team-sync status --root \\fileserver\remote-ops-team --team operators
row team-sync push --root \\fileserver\remote-ops-team --team operators --expected-version 0
row team-sync pull --root \\fileserver\remote-ops-team --team operators
```

Publishing uses optimistic version control. A client must push the version it
read; if another client has published first, the stale client receives a
conflict and must pull before retrying. A short cross-platform lock file also
serializes the check-and-write phase, preventing two writers from publishing
the same version concurrently.

Normal pulls merge remote metadata by profile name while retaining local
credential references and identity-file paths. `--replace` deliberately
replaces the local profile collection and should only be used when local-only
profiles have been backed up.
