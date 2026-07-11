# Saved layouts

Saved layouts keep pane profiles or commands, orientation, titles and splitter
sizes. When a saved layout is opened in the desktop client, its splitter sizes
are restored. Moving a splitter updates the saved layout immediately, so the
same geometry is available the next time that layout is opened.

The JSON schema validates splitter sizes against the layout tree: horizontal
and vertical layouts persist one splitter; grid layouts persist a pre-order
root-and-row splitter sequence. Invalid, incomplete, non-integer or non-positive
sizes are rejected rather than being applied to the desktop UI.

Use the existing CLI to create and inspect layouts:

```powershell
row layout save triage --orientation horizontal --pane profile:edge-prod --pane command:top
row layout show triage
```
