async def app(scope, receive, send):
    """Minimal ASGI app used for CLI tests."""
    if scope["type"] == "lifespan":  # pragma: no cover - uvicorn manages lifespan
        return
    await send({"type": "http.response.start", "status": 204, "headers": []})
    await send({"type": "http.response.body", "body": b""})
