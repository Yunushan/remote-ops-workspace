# Plugin Development

Remote Ops Workspace currently supports protocol launch plugins through Python
entry points. A plugin can add a new profile protocol, build a safe argv launch
plan for that protocol, and make the protocol visible to `row profile`,
`row connect`, `row doctor` and the GUI profile editor.

Plugins are trusted local Python code. Install them only from sources you trust.
The core validates the returned launch argv list, but it does not sandbox plugin
import or build-time code.

## Scaffold A Plugin

Create a minimal plugin package:

```bash
row plugins scaffold --out ./row-demo-plugin --name row-demo-plugin --module row_demo_plugin --protocol demo --client demo-client
cd row-demo-plugin
python -m pip install -e .
row plugins list
row plugins validate
```

The scaffold writes:

- `pyproject.toml` with the `remote_ops_workspace.plugins` entry point;
- `src/<module>/plugin.py` with a minimal `Plugin` class;
- `tests/test_plugin.py` with a launch-plan contract test;
- `README.md` with local development commands.

## Entry Point Contract

Register exactly one object per entry point under:

```toml
[project.entry-points."remote_ops_workspace.plugins"]
demo = "row_demo_plugin.plugin:Plugin"
```

The plugin object can be a class or an already-created object. It must expose:

```python
from remote_ops_workspace.launcher import LaunchPlan
from remote_ops_workspace.models import Profile


class Plugin:
    name = "demo protocol plugin"
    protocols = ("demo",)
    executables = ("demo-client",)

    def build(self, profile: Profile) -> LaunchPlan:
        return LaunchPlan(profile.protocol, ["demo-client", profile.host or profile.name], [])
```

Rules:

- `protocols` must contain at least one lowercase, whitespace-free protocol
  name.
- Plugin protocols must not collide with built-in protocols such as `ssh`,
  `sftp`, `rdp`, `vnc`, `serial` or `https`.
- `build(profile)` must return `remote_ops_workspace.launcher.LaunchPlan`.
- `LaunchPlan.command` must be a non-empty argv list. Do not return a shell
  command string.
- `LaunchPlan.protocol` must be one of the plugin's declared protocols.
- `LaunchPlan.notes` must be a list of text notes.

## Validate Locally

List discovered plugins:

```bash
row plugins list
row plugins list --json
```

Validate load-time metadata and sample launch-plan shape:

```bash
row plugins validate
row plugins validate --json
row plugins validate --host plugin.example --username operator --option mode=test
```

`row plugins validate` loads installed entry points, reports discovery failures
and asks every loaded plugin to build a sample plan for each declared protocol.
It does not execute the returned command.

After validation passes, test the profile path:

```bash
row profile add --name sample-demo --protocol demo --host plugin.example --replace
row connect sample-demo --dry-run
```

## Current Boundary

The active plugin boundary is protocol launch planning. Sync backends, terminal
widgets, vault backends and network tools remain future extension points until
they have a caller path and validation workflow equivalent to protocol launch
plugins.
