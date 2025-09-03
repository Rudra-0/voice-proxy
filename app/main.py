from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Response, status
from fastapi.responses import JSONResponse, PlainTextResponse
import asyncio, os, logging
import httpx, websockets

logger = logging.getLogger("proxy")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())

app = FastAPI(title="Exotel-Vapi Proxy")

@app.get("/healthz")
async def healthz():
    return {"status": "ok"}

@app.get("/")
async def root():
    return {"service": "exotel-vapi-proxy", "ws_path": "/ws"}

# Handle accidental HTTP hits to /ws gracefully (no stack traces)
@app.get("/ws")
@app.head("/ws")
async def ws_http_handler():
    return PlainTextResponse("Upgrade Required", status_code=status.HTTP_426_UPGRADE_REQUIRED, headers={"Connection": "Upgrade", "Upgrade": "websocket"})

async def get_vapi_ws_url(params: dict) -> str:
    # For first tests without Vapi, set VAPI_ECHO_MODE=1
    if os.getenv("VAPI_ECHO_MODE", "0") == "1":
        return "wss://echo.websocket.events"
    base = os.getenv("VAPI_BASE_URL", "https://api.vapi.ai").rstrip("/")
    api_key = os.getenv("VAPI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing VAPI_API_KEY")
    # TODO: Adjust to Vapi's actual endpoint and payload to create a session and get a ws URL.
    # Example placeholder:
    url = f"{base}/v1/calls"
    headers = {"Authorization": f"Bearer {api_key}"}
    payload = {"metadata": params}
    timeout = httpx.Timeout(10, connect=10)
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        ws_url = data.get("ws_url") or data.get("websocket_url")
        if not ws_url:
            raise RuntimeError("Vapi response missing ws_url")
        return ws_url

@app.websocket("/ws")
async def websocket_proxy(ws: WebSocket):
    await ws.accept()
    # Extract identifiers from query string for logging and Vapi metadata
    params = {k: v for k, v in ws.query_params.multi_items()}
    call_id = params.get("call_id") or params.get("callSid") or "unknown"
    logger.info(f"Exotel WS connected call_id={call_id}")

    try:
        vapi_ws_url = await get_vapi_ws_url(params)
        ping_interval = 20
        ping_timeout = 20

        async with websockets.connect(
            vapi_ws_url,
            ping_interval=ping_interval,
            ping_timeout=ping_timeout,
            max_size=None,
        ) as vapi_ws:

            logger.info(f"Connected to Vapi WS for call_id={call_id}")

            async def exotel_to_vapi():
                while True:
                    msg = await ws.receive()
                    t = msg.get("type")
                    if t == "websocket.receive":
                        if msg.get("bytes") is not None:
                            await vapi_ws.send(msg["bytes"])
                        elif msg.get("text") is not None:
                            await vapi_ws.send(msg["text"])
                    elif t == "websocket.disconnect":
                        code = msg.get("code")
                        logger.info(f"Exotel disconnected call_id={call_id} code={code}")
                        try:
                            await vapi_ws.close(code=1000)
                        except Exception:
                            pass
                        break

            async def vapi_to_exotel():
                while True:
                    data = await vapi_ws.recv()
                    if isinstance(data, (bytes, bytearray, memoryview)):
                        await ws.send_bytes(bytes(data))
                    elif isinstance(data, str):
                        await ws.send_text(data)
                    else:
                        await ws.send_text(str(data))

            # Run both tasks concurrently, cancel the other on first error/exit
            t1 = asyncio.create_task(exotel_to_vapi())
            t2 = asyncio.create_task(vapi_to_exotel())
            done, pending = await asyncio.wait({t1, t2}, return_when=asyncio.FIRST_COMPLETED)
            for p in pending:
                p.cancel()

    except WebSocketDisconnect as e:
        logger.info(f"Client WS disconnected call_id={call_id} code={getattr(e,'code',None)}")
    except Exception as e:
        logger.exception(f"Error on call_id={call_id}: {e}")
        try:
            await ws.close(code=1011)
        except Exception:
            pass
    finally:
        logger.info(f"Closed proxy for call_id={call_id}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")), reload=True)
