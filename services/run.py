"""Start the three mock services in one process: media :4101, ads :4102, crm :4103."""

import asyncio

import uvicorn

from services.app import APPS, PORTS


async def main():
    servers = [
        uvicorn.Server(uvicorn.Config(APPS[name], host="127.0.0.1", port=port, log_level="warning"))
        for name, port in PORTS.items()
    ]
    await asyncio.gather(*(s.serve() for s in servers))


if __name__ == "__main__":
    asyncio.run(main())
