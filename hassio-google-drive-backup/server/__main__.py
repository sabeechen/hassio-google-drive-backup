import aiorun
import aiohttp
import asyncio
from .server import Server


async def main():
    async with aiohttp.ClientSession() as session:
        await Server(session).start()


if __name__ == '__main__':
    print("Starting")
    aiorun.run(main())
