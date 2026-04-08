# Domain: Edge & delivery

> How traffic/assets are delivered and routed

## Core Principles

- **Edge Is a Trust Boundary**: Treat ingress/edge components as a trust boundary; inputs are untrusted until verified.
- **No Private Data in Public Caches**: Authenticated or user-specific responses MUST NOT be cached publicly.
- **Security Headers and TLS**: TLS and baseline security headers MUST be enforced where applicable.
- **Rate Limiting and Abuse Controls**: Public endpoints MUST have rate limiting/abuse controls appropriate to risk.
- **Rollbackable Routing Changes**: Traffic routing/cache configuration changes MUST be reversible.
- **Explicit Cache-Control**: Cache behavior MUST be explicit (Cache-Control/Vary), not assumed.
- **Origin Protection**: Origin endpoints MUST be protected from direct abuse (WAF/rate limits/allowlists where appropriate).
- **Cross-Origin Policy**: CORS rules MUST be explicit (allowed origins, methods, headers). Implicit "allow all" is prohibited unless explicitly justified.
- **Session/Cookie Security (If Web)**: If cookies/sessions are used, cookie attributes (Secure, HttpOnly, SameSite) and CSRF posture MUST be explicitly defined and verified.

## Best Practices

- Use CDNs for static assets.
- Implement efficient Gzip/Brotli compression.
- Monitor edge latency across geographies.
- Use explicit cache-control and vary rules; avoid implicit edge caching.
- Keep origin exposure minimal; prefer private origins where possible.
- Monitor edge latency, error rates, cache hit ratio, and origin load.

## Subchecklists

- [ ] Are static assets cached on the edge?
- [ ] Is global latency minimized at the entry point?
- [ ] Are DNS records configured correctly?
- [ ] Are authenticated/private responses excluded from public caching?
- [ ] Are cache-control and vary rules explicit and correct?
- [ ] Are security headers/TLS requirements enforced?
- [ ] Are rate limits/abuse controls defined for public endpoints?
- [ ] Are routing/cache config changes reversible and tested (rollback path exists)?
- [ ] Is origin protected from direct abuse (WAF/rate limits/allowlists where applicable)?
- [ ] Are edge error rates, cache hit ratio, and latency observable?
- [ ] Are CORS rules explicit and least-permissive (origins/methods/headers)?
- [ ] If cookies/sessions exist, are Secure/HttpOnly/SameSite attributes correct and verified?
- [ ] If relevant, is CSRF protection explicitly addressed (token/double-submit/or SameSite strategy)?

## Deterministic Checks

- Run `curl -I <url>` to check cache-control headers.
- Run `dig <domain>` to verify DNS resolution.
- Verify WAF/rate-limit policy is active for public endpoints (where applicable).
- `curl -I` verify CORS + security headers for representative endpoints.
- Verify cookie attributes in a real response (where applicable).