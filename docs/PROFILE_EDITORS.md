# Profile editor workflows

The desktop profile dialog offers safe protocol presets for SSH, SFTP, RDP,
VNC, SPICE, X2Go, ICA, Mosh, serial and raw-socket profiles. Applying a preset
updates only the port and protocol options; it retains names, hosts, usernames,
groups and credential references already entered by the operator.

Use the **Import** toolbar action to choose an existing ROW, Remmina,
mRemoteNG, Termius-style JSON or MobaXterm export. The client parses it first,
shows each proposed profile with name, protocol, target and group, displays
warnings, and imports only after the operator confirms the preview. Imported
profiles still pass profile validation and the enterprise-policy editor rules.
