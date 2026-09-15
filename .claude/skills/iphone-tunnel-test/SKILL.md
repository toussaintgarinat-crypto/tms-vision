---
name: iphone-tunnel-test
description: Use when testing the TMS Vision web capture page from an iPhone or any device other than the Mac running the dev servers — needed because getUserMedia requires a secure (HTTPS) context and a plain http://<LAN-IP> address doesn't qualify, so joining the same WiFi and hitting localhost is not enough.
---

# iPhone Tunnel Test

## Overview

Testing the web capture page (`web/`) from a phone needs HTTPS — a LAN IP over
plain `http://` fails `getUserMedia`'s secure-context check, and CORS blocks
the API call anyway (hardcoded to `localhost:3000` by default). This launches
two `cloudflared` tunnels, waits for their URLs, then starts the API and
frontend wired to each other automatically via `ALLOWED_ORIGINS` /
`NEXT_PUBLIC_API_URL`.

## When to Use

- Verifying the capture page works on Safari/iOS (or any non-Mac device)
  before relying on it for the real-human RULA verification.
- Any time "just join the same WiFi and open localhost" doesn't work for
  camera access from a phone.

## Usage

```bash
./.claude/skills/iphone-tunnel-test/launch.sh
```

Prints the URL to open on the phone once both tunnels and both servers are up
(usually well under 30s). Ctrl+C stops everything.

## Requirements

- `cloudflared` installed (`brew install cloudflared`) — no account or login
  needed for these ephemeral quick tunnels.
- Backend venv and `web/node_modules` already set up (README sections 9/10).

## How It Works

1. Starts both `cloudflared tunnel --url http://localhost:<port>` in the
   background, logging to temp files.
2. Polls each log for the `https://*.trycloudflare.com` URL cloudflared
   prints once the tunnel is live (up to 30s timeout).
3. Starts `uvicorn` with `ALLOWED_ORIGINS` set to the frontend's tunnel URL,
   so CORS allows the browser's actual origin.
4. Starts `npm run dev` with `NEXT_PUBLIC_API_URL` set to the API's tunnel
   URL, so the frontend's fetch calls reach the right place.
5. On exit (Ctrl+C), kills all four processes.

Verified end-to-end: both tunnels route correctly to their local ports, and
a live CORS preflight from the frontend tunnel's origin to the API tunnel
returns the correct `Access-Control-Allow-Origin`.

## Common Mistakes

- **A `next-server` process survives after Ctrl+C.** `npm run dev` spawns a
  child process that doesn't receive the signal sent to the `npm run dev`
  process itself — the script's cleanup explicitly `pkill -f`s it too. If a
  previous run left port 3000 stuck, that's why: `pkill -f "next-server \(v"`.
- **Tunnel URLs are ephemeral.** A fresh pair is generated every run — don't
  reuse or hardcode a URL from a previous session.
- **Nothing printed after ~30s.** Check the log file path in the error
  message (temp dir printed on failure) — cloudflared may be slow to
  register, or a firewall/VPN is interfering with the outbound tunnel.
