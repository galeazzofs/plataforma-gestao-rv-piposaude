# JWT -> HttpOnly Cookie Migration Plan

## Current state (after code review)

Tokens are stored in re-frame app-db (JavaScript heap). XSS would let an
attacker read the access AND refresh tokens via `re_frame.core.get_app_db()`.
The 7-day refresh window means a single XSS gives an attacker a week-long
session.

**Mitigations already shipped:**
- Strict CSP in nginx (script-src 'self'; object-src 'none'; etc.) -
  see `frontend/nginx.conf`
- HSTS, X-Frame-Options=DENY, X-Content-Type-Options=nosniff
- Referrer-Policy strict-origin-when-cross-origin

## Migration target

1. Backend issues `access_token` and `refresh_token` as cookies on
   `/auth/google` and `/auth/dev-login`:
   - `HttpOnly` (JS cannot read)
   - `Secure` (HTTPS only)
   - `SameSite=Strict` (no CSRF from cross-origin requests)
   - `Path=/api/v1/`

2. `@require_auth` decorator reads from `request.cookies['access_token']`
   instead of the Authorization header (or accepts both during transition).

3. CSRF protection: since cookies are sent automatically, add a
   double-submit-cookie pattern OR a per-request CSRF token in a
   `X-CSRF-Token` header that the frontend mirrors from a non-HttpOnly
   `csrf_token` cookie.

4. Frontend stops reading tokens from re-frame app-db. The HTTP layer
   relies on browser auto-sending cookies. `:auth/login-success` only
   stores the user object, not tokens.

5. `/auth/refresh` uses the refresh cookie automatically.

## Estimated effort
- Backend: 1-2 days (cookie issuance + decorator update + CSRF middleware)
- Frontend: 1 day (remove token state, update HTTP interceptor)
- Testing: 1 day (auth flows, CSRF, logout, refresh)
- Rollout: 1 day (zero-downtime via dual-mode period)

## Why deferred
This is a structural change affecting every authenticated request. It was
out of scope for the code-review pass (which targets surgical fixes). The
strict CSP makes XSS-to-token-theft significantly harder in the meantime.
