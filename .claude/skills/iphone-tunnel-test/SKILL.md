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
4. **Builds** the frontend (`npm run build`) with `NEXT_PUBLIC_API_URL` set
   to the API's tunnel URL, then starts it with `npm run start` —
   **production mode, not `npm run dev`** (see Common Mistakes below for why
   this is not optional).
5. On exit (Ctrl+C), kills all processes.

Verified end-to-end: both tunnels route correctly to their local ports, a
live CORS preflight from the frontend tunnel's origin to the API tunnel
returns the correct `Access-Control-Allow-Origin`, and — critically — a real
click on "Démarrer la caméra" through the tunnel actually reaches React's
click handler in production mode (confirmed via `__reactFiber`/`__reactProps`
keys appearing on the button, and a real iPhone successfully starting the
camera through this exact flow on 2026-09-15).

## Common Mistakes

- **Using `npm run dev` instead of `npm run build && npm run start` — this
  silently breaks the entire page, not just hot-reload.** Dev mode's client
  bootstrap depends on the HMR (hot module reload) WebSocket succeeding as
  part of finishing React hydration. Cloudflare Quick Tunnels reliably fail
  to proxy that WebSocket upgrade (`WebSocket connection ... failed: La
  réponse du serveur est erronée` in the console, every time). The result
  isn't a broken hot-reload with a working app underneath — hydration itself
  never completes: the server-rendered HTML displays normally (title,
  layout, button all visible and looking correct), but **no button, link, or
  interactive element responds to any input, silently, with zero console
  errors.** Confirmed by direct inspection on a real iPhone (via Safari's
  Web Inspector over USB) on 2026-09-15: `document.querySelector('button').click()`
  did nothing, and `Object.keys(button).filter(k => k.includes('react'))`
  returned `[]` — proof React never attached to the DOM at all. Meanwhile
  browser APIs typed directly into the console (e.g. `getUserMedia`) worked
  perfectly, which is what made this confusing to diagnose: the browser and
  permissions were never the problem, only React's own client bootstrap
  silently stalling on the dead HMR socket. Production mode has no HMR
  client and isn't affected. If you ever modify this script to go back to
  `npm run dev` "for faster iteration," you will reintroduce this exact
  failure mode with no error message to point at it.
- **`NEXT_PUBLIC_API_URL` must be set at *build* time, not start time** — the
  script builds the frontend fresh on every run (few seconds) after learning
  the API tunnel's URL, precisely because this Next.js env var convention
  gets inlined into the client bundle at build time and can't be overridden
  by setting it only before `npm run start`.
- **A `next-server` process survives after Ctrl+C.** `npm run start` spawns
  a child process that doesn't receive the signal sent to the `npm run
  start` process itself — the script's cleanup explicitly `pkill -f`s it
  too. If a previous run left port 3000 stuck, that's why:
  `pkill -f "next-server \(v"`.
- **Tunnel URLs are ephemeral.** A fresh pair is generated every run — don't
  reuse or hardcode a URL from a previous session.
- **Nothing printed after ~30s.** Check the log file path in the error
  message (temp dir printed on failure) — cloudflared may be slow to
  register, or a firewall/VPN is interfering with the outbound tunnel.
