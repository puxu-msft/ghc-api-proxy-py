"""Does httpx2's truststore-based default still validate the real upstream certificate chains?

No credentials are sent: a TLS handshake completing (even into a 401) is the whole question.
"""
import asyncio
import ssl

import httpx
import httpx2

TARGETS = ["https://api.githubcopilot.com/models", "https://api.github.com/user"]


async def probe(name, client_factory):
    async with client_factory() as client:
        for url in TARGETS:
            try:
                response = await client.get(url, timeout=20.0)
                print(f"  {name:8s} {url:42s} -> HTTP {response.status_code} (handshake OK)")
            except Exception as error:
                print(f"  {name:8s} {url:42s} -> {type(error).__name__}: {error}")


async def main():
    print(f"httpx {httpx.__version__} default ctx: {type(httpx.create_ssl_context()).__module__}")
    print(f"httpx2 {httpx2.__version__} default ctx: {type(httpx2.create_ssl_context()).__module__}")
    await probe("httpx", lambda: httpx.AsyncClient(http2=True))
    await probe("httpx2", lambda: httpx2.AsyncClient(http2=True))
    # Negative control: prove the probe can actually see a validation failure.
    bad = ssl.create_default_context(cafile="/dev/null") if False else None
    del bad
    try:
        async with httpx2.AsyncClient(verify=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)) as client:
            await client.get("https://expired.badssl.com/", timeout=20.0)
        print("  control  expired.badssl.com                         -> NO ERROR (probe cannot see failures!)")
    except Exception as error:
        print(f"  control  expired.badssl.com                         -> {type(error).__name__} (probe can see failures)")


asyncio.run(main())
