## Caddy security headers (recommended)

Add these headers to your Caddy site block to harden the public UI.

Example `/etc/caddy/Caddyfile`:

```caddyfile
yournexus.duckdns.org {
    encode zstd gzip

    header {
        # Basic hardening
        X-Content-Type-Options "nosniff"
        X-Frame-Options "DENY"
        Referrer-Policy "no-referrer"
        Permissions-Policy "camera=(), microphone=()"

        # CSP (relaxed but useful; tighten as you add external resources)
        # NOTE: The Nexus UI is a single-file app with inline <script>.
        # If you block inline scripts, the console (including sign-in) will not work.
        Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline'; img-src 'self' data:; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; connect-src 'self';"
    }

    reverse_proxy 127.0.0.1:8001
}
```

Then:

```bash
sudo systemctl reload caddy
```

