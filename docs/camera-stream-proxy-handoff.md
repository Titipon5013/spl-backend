# CAMT camera proxy security handoff

Apply this at the production reverse proxy that serves the frontend and camera
streams. Backend changes alone do not protect the four HLS routes unless the
reverse proxy routes them through the backend's protected stream proxy.

An anonymous production probe returned `200` for `license`, `license1`, and
`parking` manifests with `Cache-Control: max-age=30`, and HTML `502` for both
inference endpoints. That differs from this backend's expected responses
(`401` for anonymous requests and `no-store` headers) and indicates the active
production proxy is not reaching the protected backend path. A frontend static
file rebuild alone will not update a separate CAMT-managed proxy.

## Nginx routing

If Nginx serves the frontend and API, route API and camera requests to the
backend service. The frontend repository's `nginx.conf` contains this routing.
If CAMT terminates these paths in another Nginx instance, apply equivalent
locations there and replace `backend:8000` with the backend's reachable service
name and port:

```nginx
location ^~ /api/ {
    proxy_pass http://backend:8000;
    proxy_set_header Authorization $http_authorization;
    proxy_set_header Cookie $http_cookie;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_cache off;
    proxy_no_cache 1;
    proxy_hide_header Cache-Control;
    add_header Cache-Control "private, no-store" always;
}

location ~ ^/(license1|license2|parking1|parking2|license|parking)(/|$) {
    proxy_pass http://backend:8000;
    proxy_set_header Cookie $http_cookie;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_buffering off;
    proxy_cache off;
    proxy_no_cache 1;
    proxy_hide_header Cache-Control;
    add_header Cache-Control "private, no-store" always;
}
```

Do not configure a direct-to-edge location for these camera prefixes. Keep the
edge source private so the backend is the only route to stream data.

## Required behavior

- Route **every request** under `/parking/`, `/parking2/`, `/license/`, and
  `/license1/` to the backend's protected stream proxy. Cover playlists, nested
  playlists, segments, and encryption keys. Do not limit routing to
  `index.m3u8`.
- Preserve the request path when forwarding to the backend. The backend checks
  the `parking_stream_session` cookie on each request, then fetches the matching
  path from `EDGE_BASE_URL`. Do not route these locations directly to the edge.
- Keep the edge upstream inaccessible from the public network where practical,
  so clients cannot bypass the protected backend proxy.
- If production must continue proxying directly to the edge, configure an auth
  subrequest to `GET /api/parking/stream-auth` for every request and forward the
  cookie. Permit only `204`; deny `401` and `403`; never cache auth responses.
- Disable public caching of manifests, segments, keys, and authorization
  responses. Return `Cache-Control: private, no-store` on stream content.
- Serve the frontend and proxy over HTTPS. The backend sets the session cookie
  as `Secure`, `HttpOnly`, `SameSite=None`, and `Path=/`.

The frontend first posts its existing bearer token to
`POST /api/parking/stream-session`. The backend sets a stream cookie lasting at
most five minutes and never beyond the bearer token expiry. The frontend refreshes
the cookie every four minutes while the camera page is open. The proxy must
forward requests and cookies as described above and must not expose or append
bearer tokens to stream URLs.

## Deployment checks

After deploying backend, frontend, and proxy changes, verify anonymously that
all four path prefixes reject playlists, segments, and keys; verify both
`/api/parking/inference` and `/api/parking/inference2` return `401`; then sign in
as approved operator and admin accounts and confirm HLS playback and gate
controls work. Revoke or unapprove a test account and confirm new stream
requests fail. Check the browser network panel to confirm no URL contains a
token. Backend and frontend repositories do not contain the production CAMT
proxy configuration, so this server-side work remains a deployment handoff.

Never verify gate auth by sending a production request to
`GET /api/parking/open`: that endpoint opens the gate when authorized. Confirm
route wiring from configuration and use the backend regression test that
asserts anonymous requests return `401` without calling the edge service.
