# row-demo-plugin

Protocol launch plugin for Remote Ops Workspace.

## Develop

```bash
python -m pip install -e .
row plugins list
row plugins validate
row profile add --name sample-demo --protocol demo --host plugin.example --replace
row connect sample-demo --dry-run
```
