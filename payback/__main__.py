import asyncio

from payback.main import EXIT_SIGINT, main

try:
    raise SystemExit(asyncio.run(main()))
except KeyboardInterrupt:
    raise SystemExit(EXIT_SIGINT) from None
