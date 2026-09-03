Corp Ops Remote Ops Workspace enterprise customization bundle

Contents:
- branding/branding.json and optional branding/logo.*
- config/settings.json for default application settings
- config/policy.json for locked enterprise policy values
- config/profiles.json for seeded connection profiles
- welcome.txt for the first-run welcome message
- SHA256SUMS.txt and manifest.json for release evidence

Run apply-enterprise-bundle.ps1 on Windows or apply-enterprise-bundle.sh on POSIX hosts.
Set ROW_HOME first to apply into a portable workspace directory.
