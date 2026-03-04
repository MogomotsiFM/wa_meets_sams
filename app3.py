import os
import asyncio
import logging

from Messangers.wa_wrapper import WhatsAppWrapper

from dotenv import load_dotenv
load_dotenv()

WA_SAMS_TOKEN = os.getenv("WA_SAMS_TOKEN")
WA_SAMS_PHONE_ID = os.getenv("WA_SAMS_PHONE_ID")

logging.basicConfig(level=logging.INFO)
payload = {
    "messaging_product": "whatsapp",   
    "recipient_type": "individual",
    "to": "27731948818",
    "type": "text",
    "text": {
        "preview_url": False,
        "body": "Heartbeat"
    }
}

async def run():   
    wa = WhatsAppWrapper(WA_SAMS_TOKEN, WA_SAMS_PHONE_ID)
    response = await wa._send_message("POST", payload)
    logging.getLogger().info("Response: ", response)
    print(f"Response: {response}")
    await wa.close()

if __name__ == "__main__":
    asyncio.run(run(), debug=True)
