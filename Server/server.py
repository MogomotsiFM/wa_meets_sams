import os
import sys
import hmac
import asyncio
import hashlib
import secrets
import socket
import logging
import json
import redis

from contextlib import asynccontextmanager

import uvicorn

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse, JSONResponse
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from guard.middleware import SecurityMiddleware
from guard.models import SecurityConfig

import ngrok
#from tunnel import create_tunnel
from . import tunnel

from Server.aso_name import get_autonomous_sys_org_name
#from . import aso_name

from Processes import process_incoming_messages as pim

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger()

# WhatsApp Cloud API token and secrets
VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN")
APP_SECRET = os.getenv("WHATSAPP_APP_SECRET")

NGROK_AUTH_TOKEN = os.getenv("NGROK_AUTH_TOKEN")

if not VERIFY_TOKEN or not APP_SECRET:
    logger.error("Environment variables WHATSAPP_VERIFY_TOKEN and WHATSAPP_APP_SECRET must be set")
    raise SystemExit(1)

# Redis channel to store responses to opt-in messages
OPT_IN_RESPONSES = os.getenv("OPT_IN_RESPONSES")

APP_PORT = 4001
subdomain = "mogomotsihs"
# This is beautiful code
@asynccontextmanager
async def lifespan_local_tunnel(app: FastAPI):
    status, tunnel_url, tunnel_process = tunnel.create_tunnel(port=APP_PORT, subdomain=subdomain)
    if status:
        print(f"Tunnel created successfully! URL: {tunnel_url}")
    else:
        print(f"Failed to create tunnel. Error: {tunnel_url}")
        raise ProcessLookupError()
    yield
    r = redis.from_url("redis://localhost")
    r.publish("wa_messages_channel", "STOP")
    r.close()
    tunnel_process.terminate()


@asynccontextmanager
async def lifespan_ngrok(app: FastAPI):
    logger.info("Setting up ngrok Endpoint")
    with open("Server/ngrok_traffic_policy.json") as file:
        traffic_policy = file.read()
        ngrok.forward(addr=APP_PORT, authtoken=NGROK_AUTH_TOKEN, traffic_policy=traffic_policy)
        #logger.info(f"~~ Listening: {listener.url()}")
    yield
    logger.info("Tearing Down ngrok Endpoint")
    r = redis.from_url("redis://localhost")
    r.publish("wa_messages_channel", "STOP")
    r.close()
    ngrok.disconnect()


TUNNEL = os.getenv("TUNNEL")
if TUNNEL == "ngrok":
    lifespan = lifespan_ngrok
elif TUNNEL == "lt":
    lifespan = lifespan_local_tunnel
app = FastAPI(lifespan=lifespan)


# Define your security configuration
config = SecurityConfig(
    #whitelist=["192.168.1.1", "2001:db8::1"],
    blocked_user_agents=["curl", "wget"],
    auto_ban_threshold=5,
    auto_ban_duration=86400,
    rate_limit=100,
    enforce_https=True,
    enable_cors=True,
    cors_allow_origins=["https://graph.facebook.com/"],
    cors_allow_methods=["GET", "POST"],
    cors_allow_headers=["*"],
    cors_allow_credentials=True,
    #cors_expose_headers=["X-Custom-Header"],
    cors_max_age=600,
    #trusted_proxies=["10.0.0.1", "192.168.1.0/24"],  # List of trusted proxy IPs or CIDR ranges
    trusted_proxy_depth=1,                           # How many proxies to expect in chain
    trust_x_forwarded_proto=True,
    enable_penetration_detection=True,
    passive_mode=True,
    custom_log_file="security.log",
    block_cloud_providers={"AWS", "GCP", "Azure"},
)


if TUNNEL == "lt":
    # TODO: Remember the list of trusted IP addresses? Use aiocache?
    @app.middleware("http")
    async def verify_facebook_calling(request: Request, call_next):
        forwarded_for = request.headers.get("x-forwarded-for")
        status, aso_ = get_autonomous_sys_org_name(forwarded_for)

        if status:
            aso = aso_.setdefault("asn", None)
            if aso == None or (not aso in ["32934", "63293"]):
                return JSONResponse(status_code=403, content={"detal": "Hostname not allowed"})
                #raise HTTPException(status_code=403, detail="Hostname not allowed")
        else:
            return JSONResponse(status_code=403, content={"detal": "Hostname not allowed"})
            #raise HTTPException(status_code=403, detail="Hostname not allowed")

        response = await call_next(request)
        return response


def extract_message(raw_msg: str)->list:
    body = json.loads(raw_msg)
    entries = body["entry"]
    entry = entries[0]
    changes = entry["changes"]
    change = changes[0]
    value: dict = change["value"]
    msgs = value.setdefault("messages", [])

    return msgs


def verify_signature(body: bytes, header_sig: str) -> bool:
    if not header_sig:
        return False
    # Header format: "sha256=<hex>"
    if header_sig.startswith("sha256="):
        header_sig = header_sig.split("=", 1)[1]
    mac = hmac.new(APP_SECRET.encode("utf-8"), msg=body, digestmod=hashlib.sha256)
    computed = mac.hexdigest()
    return secrets.compare_digest(computed, header_sig)


@app.get("/webhook")
async def webhook_verify(hub_mode: str, hub_verify_token: str, hub_challenge: str):
    # WhatsApp Cloud API verification flow
    if hub_mode == "subscribe" and hub_verify_token == VERIFY_TOKEN:
        return PlainTextResponse(content=hub_challenge or "", status_code=200)
    raise HTTPException(status_code=403, detail="Verification failed")


@app.post("/webhook")
async def webhook_receive(request: Request):
    raw_body = await request.body()    
    sig = request.headers.get("x-hub-signature-256")
    if not verify_signature(raw_body, sig):
        raise HTTPException(status_code=403, detail="Invalid signature")
    try:
        payload = await request.json()
        logger.debug(f"body: {payload}")
        msgs = extract_message(raw_body)
        if len(msgs) > 0:
            r = redis.from_url("redis://localhost")
            r.publish(OPT_IN_RESPONSES, json.dumps(msgs))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    logger.info("Received webhook event")
    return JSONResponse({"status": "received"})


@app.get("/")
async def root(request: Request):
    return PlainTextResponse("WhatsApp SAMS Server is running.")


async def upload_files():
    from redis.asyncio import Redis
    r = await Redis.from_url("redis://localhost")

    await asyncio.sleep(45)

    img_path = r"C:\Users\GAME\Desktop\Projects\whatsapp_sams\Data\school_emblem.png"
    await r.publish("pending_delivery_filenames", img_path)
    
    await asyncio.sleep(2)

    file_path = r"C:\Users\GAME\Desktop\Projects\whatsapp_sams\Data\Mogomotsi KEAIKITSE - Tel0731948818 - EMailamg.seiphemo@gmail.com.pdf"
    await r.publish("pending_delivery_filenames", file_path)

    await asyncio.sleep(2)
    
    file_path = r"C:\Users\GAME\Desktop\Projects\whatsapp_sams\Data\Segomotsi KEAIKITSE - Tel27731948818 - EMailamg.seiphemo@gmail.com.pdf"
    await r.publish("pending_delivery_filenames", file_path)
    

async def run_helper(port):
    uvi = lambda: uvicorn.run("Server.server:app", port=APP_PORT)
    await asyncio.gather(
        pim.process_messages(),
        asyncio.to_thread(uvi),
        upload_files()
    )


def run(port):
    asyncio.run(run_helper(port))

