# Browser profile API

`row serve-web` can provide a local, same-origin profile API for the Web/PWA.
It is disabled unless an API token is supplied and it cannot bind with the API
enabled on a non-loopback interface.

```powershell
$env:ROW_WEB_API_TOKEN = '<a-random-24-plus-character-token>'
row serve-web --host 127.0.0.1 --port 8765 --api-token-env ROW_WEB_API_TOKEN
```

`--api-token` remains available for automation that already protects process
arguments, but `--api-token-env` avoids exposing the token in local process listings.

Endpoints:

- `GET /api/v1/health` returns the API version and profile count and requires
  `Authorization: Bearer <token>`.
- `GET /api/v1/profiles` returns the profile catalogue and requires
  `Authorization: Bearer <token>`.
- `POST /api/v1/profiles` accepts a JSON profile and the same bearer token.

The API accepts only a documented allowlist of declarative connection fields and
options. It does not expose or accept credential references, local paths,
commands, unknown option payloads, URL credentials/paths/query strings, passwords,
secrets or tokens. Browser URLs are restricted to an HTTP(S) origin: paths,
queries and fragments are excluded because they can contain opaque capability
tokens. Port forwards, agent/trusted-X11 forwarding and host-key-check disabling
also remain local. Legacy local profiles are projected through the same safe
serializer before they reach the browser. It has no terminal, shell,
file-transfer or arbitrary-file endpoints. Profile writes use the existing
`web` enterprise policy surface and remain subject to its locked settings and
user-profile rules.

The PWA demo starts read-only until the enterprise-policy response has loaded.
If that response is missing or malformed, profile creation remains blocked
instead of silently treating the policy as inactive. Locks whose names or
values cannot be exposed safely are represented only by
`has_restricted_locks=true`; the PWA then keeps edits blocked and directs the
operator to a trusted native/API surface that can evaluate the complete policy.
