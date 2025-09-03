# Exotel ↔ Vapi WebSocket Proxy (Render deploy)

This repository hosts a FastAPI+Uvicorn proxy that exposes a stable WebSocket endpoint (for Exotel) and dynamically connects each call to a per-call WebSocket from Vapi. It also serves HTTP endpoints (root and /healthz) on the same port.

## Features
- Single service/port for HTTP and WebSocket.
- Graceful handling of accidental HTTP requests to `/ws` (returns 426 Upgrade Required).
- Per-call dynamic Vapi WS URL lookup via async REST call.
- Echo mode for testing without Vapi.
- Ready for Render deployment via `render.yaml` or standard “Web Service”.

## Repository layout
- `requirements.txt`: Python dependencies
- `render.yaml`: Render Blueprint definition (optional; you can also create a Web Service manually)
- `app/main.py`: FastAPI app and WS bridge logic

## Local setup (Windows PowerShell)
1) Create venv and install deps:
   - python -m venv .venv
   - .\.venv\Scripts\Activate.ps1
   - pip install -r requirements.txt
2) Optional: create a `.env` and set variables (or set in your shell):
   - VAPI_ECHO_MODE=1 (enables echo server for local tests)
   - LOG_LEVEL=debug
3) Run the server:
   - uvicorn app.main:app --reload
4) Test:
   - Health check: open http://localhost:8000/healthz
   - WebSocket: install wscat (Node.js) then run: wscat -c ws://localhost:8000/ws?call_id=localtest
   - Type messages to see echo responses when VAPI_ECHO_MODE=1.

## Configure Vapi integration
Edit `get_vapi_ws_url` in `app/main.py` to call the correct Vapi REST endpoint that returns a per-call WebSocket URL. Set environment variables:
- `VAPI_API_KEY`
- `VAPI_BASE_URL` (default: https://api.vapi.ai)
- `VAPI_ECHO_MODE` ("1" for echo test, "0" for real Vapi)
- `LOG_LEVEL` (info/debug)

If Vapi requires WS auth headers, pass `extra_headers` in `websockets.connect`.

## Deploy on Render
Option A — Blueprint (uses `render.yaml`):
- Push this repo to GitHub.
- On Render, New → Blueprint, connect the repo, confirm plan/region.
- Render will use `render.yaml` to build and run.

Option B — Web Service:
- New → Web Service → Connect repo.
- Environment: Python
- Build command: pip install -r requirements.txt
- Start command: uvicorn app.main:app --host 0.0.0.0 --port $PORT
- Health check path: /healthz
- Add environment variables: VAPI_API_KEY (secret), VAPI_BASE_URL, LOG_LEVEL, VAPI_ECHO_MODE

After deploy, test:
- https://YOUR-SERVICE.onrender.com/healthz
- wscat -c wss://YOUR-SERVICE.onrender.com/ws?call_id=test

## Configure Exotel
Point Exotel to the stable WS endpoint:
- wss://YOUR-SERVICE.onrender.com/ws?callSid={CALL_SID}&from={FROM}&to={TO}

Make sure your health checks target `/healthz`, not `/ws`.

## Troubleshooting
- ModuleNotFoundError on Render: ensure `requirements.txt` has all deps; clear build cache and redeploy.
- Port issues: bind 0.0.0.0 and use `$PORT` (already handled in start command).
- Invalid handshake/HEAD on /ws: handled by returning 426.
- WS closes (1006/1011): check logs, auth to Vapi, and timeouts. Adjust `ping_interval`/`ping_timeout` in `websockets.connect`.
- Cold starts: use at least Starter plan for production telephony.

## Notes
- This app forwards text and binary frames as-is (low latency). No audio transcoding is performed.
- Add structured logging and correlation IDs (e.g., call_id) for observability.
