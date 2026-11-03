"""SSE helpers: event encoding + 15s heartbeat so proxies don't close idle streams."""
import asyncio
import contextlib
import json
from typing import AsyncGenerator

PING = b": ping\n\n"


def sse_event(event: str, data: dict) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n".encode()


async def with_heartbeat(gen: AsyncGenerator[bytes, None]) -> AsyncGenerator[bytes, None]:
    queue: asyncio.Queue = asyncio.Queue()

    async def pump():
        try:
            async for chunk in gen:
                await queue.put(chunk)
        finally:
            await queue.put(None)

    task = asyncio.create_task(pump())
    try:
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=15.0)
            except asyncio.TimeoutError:
                yield PING
                continue
            if item is None:
                break
            yield item
    finally:
        task.cancel()
        with contextlib.suppress(BaseException):
            await task