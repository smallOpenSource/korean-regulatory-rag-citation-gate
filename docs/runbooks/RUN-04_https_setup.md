# RUN-04 — HTTPS Setup & HSTS Configuration

**Scope:** nginx TLS termination, HTTP→HTTPS redirect, HSTS preload submission.  
**Applies to:** Stage 1+ deployments (REG-05 T295).  
**Related:** ADR-003 (dependency gate), OPS-02 (deploy), RUN-05 (PostgreSQL hardening).

---

## 1. Overview

The Harness API operates behind nginx as a TLS-terminating reverse proxy. nginx:

1. Listens on port 80 and issues a **301 redirect** to HTTPS.
2. Listens on port 443, terminates TLS, and proxies requests to the FastAPI app on port 8000.
3. Sets `X-Forwarded-Proto: https` so the `HttpsEnforceMiddleware` knows the protocol.

The FastAPI app enforces HTTPS at the application layer (`core/https_enforce.py`) using the
`X-Forwarded-Proto` header. In non-development profiles (`APP_ENV != development|dev|local|test`),
HTTP requests received without this header are redirected with **308 Permanent Redirect**.

---

## 2. nginx Configuration

### 2.1 HTTP → HTTPS Redirect (port 80)

```nginx
server {
    listen 80;
    listen [::]:80;
    server_name harness.internal.example.com;

    # Allow Let's Encrypt / ACME challenge through plain HTTP
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    # Redirect everything else to HTTPS
    location / {
        return 301 https://$host$request_uri;
    }
}
```

### 2.2 HTTPS Reverse Proxy (port 443)

```nginx
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name harness.internal.example.com;

    # TLS certificate (Let's Encrypt via certbot, or internal PKI)
    ssl_certificate     /etc/letsencrypt/live/harness.internal.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/harness.internal.example.com/privkey.pem;

    # Modern TLS settings (Mozilla Intermediate profile)
    ssl_protocols             TLSv1.2 TLSv1.3;
    ssl_ciphers               ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305:DHE-RSA-AES128-GCM-SHA256;
    ssl_prefer_server_ciphers off;
    ssl_session_timeout       1d;
    ssl_session_cache         shared:MozSSL:10m;
    ssl_session_tickets       off;

    # HSTS — max-age 180 days; upgrade to 1 year after preload verification
    add_header Strict-Transport-Security "max-age=15552000; includeSubDomains; preload" always;

    # Tell FastAPI the original protocol
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
    proxy_set_header Host              $host;

    location / {
        proxy_pass         http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header   Upgrade    $http_upgrade;
        proxy_set_header   Connection "upgrade";
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }

    # Health check — no rate limit, no HTTPS redirect (load balancer probe)
    location /health {
        proxy_pass http://127.0.0.1:8000/health;
        access_log off;
    }
}
```

---

## 3. Secure Cookie Verification

The `harness_refresh_token` cookie **MUST** carry `Secure; HttpOnly; SameSite=Lax` in all
non-development profiles. Verify with:

```bash
# After login, inspect Set-Cookie header
curl -si https://harness.internal.example.com/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"test@example.com","password":"..."}' \
  | grep -i set-cookie

# Expected output includes:
# Set-Cookie: harness_refresh_token=...; HttpOnly; Path=/; SameSite=lax; Secure
```

In the `.env` file:

```dotenv
AUTH_REFRESH_COOKIE_SECURE=true
AUTH_REFRESH_COOKIE_SAMESITE=lax
```

> **Security gate:** The test suite (`tests/test_https_enforce.py`) verifies that
> `HttpsEnforceMiddleware` issues a 308 redirect when `X-Forwarded-Proto: http` is received
> in a non-dev profile, and that the cookie carries the `Secure` attribute.

---

## 4. HSTS Preload Submission

Preload registration makes all browsers enforce HTTPS before the first connection:

1. Confirm `Strict-Transport-Security: max-age=31536000; includeSubDomains; preload`
   (upgrade max-age to 1 year from 180-day staging value before submitting).
2. Submit the domain at **https://hstspreload.org**.
3. Verify status with `curl -s "https://hstspreload.org/api/v2/status?domain=harness.internal.example.com"`.
4. Record submission date in the ops log and set a calendar reminder for the annual renewal check.

> **Warning:** Once a domain is on the HSTS preload list it cannot be trivially removed.
> Ensure HTTPS is permanently viable for the domain before submitting.

---

## 5. Certificate Renewal

Using Let's Encrypt + certbot:

```bash
# Test renewal dry-run
certbot renew --dry-run

# Force renewal
certbot renew --force-renewal

# Reload nginx after renewal (via cron or systemd timer)
systemctl reload nginx
```

Automate with a weekly systemd timer or cron job:

```cron
0 3 * * 0  certbot renew --quiet && systemctl reload nginx
```

---

## 6. Verification Checklist

| Check | Command | Expected |
|-------|---------|----------|
| HTTP redirects to HTTPS | `curl -si http://harness.internal.example.com/ \| grep Location` | `https://...` |
| HSTS header present | `curl -si https://harness.internal.example.com/ \| grep -i strict` | `max-age=15552000` |
| TLS grade | `ssllabs.com` or `testssl.sh` | A+ |
| Refresh cookie Secure | See §3 above | `Secure` attribute present |
| App-layer redirect | `curl -si -H 'X-Forwarded-Proto: http' https://harness.internal.example.com/api/health` | `308` (non-dev only) |
