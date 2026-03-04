import aiohttp
import asyncio
import logging

# Set up logging to display the traffic
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    trace_config = aiohttp.TraceConfig()

    async def on_request_start(session, trace_config_ctx, params):
        logger.info(f"Starting request: {params.method} {params.url}")

    async def on_response_chunk_received(session, trace_config_ctx, params):
        logger.info(f"Received chunk: {params.chunk}")

    trace_config.on_request_start.append(on_request_start)
    trace_config.on_response_chunk_received.append(on_response_chunk_received)

    async with aiohttp.ClientSession(trace_configs=[trace_config]) as session:
        async with session.get('http://httpbin.org/get') as resp:
            print(await resp.text())

asyncio.run(main())
