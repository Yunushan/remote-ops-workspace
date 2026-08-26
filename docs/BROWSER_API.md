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

The API does not expose or accept credential references, identity-file paths,
passwords, secrets or tokens. It has no terminal, shell, file-transfer or
arbitrary-file endpoints. Profile writes use the existing `web` enterprise
policy surface and remain subject to its locked settings and user-profile rules.
