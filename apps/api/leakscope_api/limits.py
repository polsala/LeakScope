"""Bound JSON requests before framework parsing, including chunked requests."""

from starlette.responses import JSONResponse


class BodyLimit:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if (
            scope["type"] != "http"
            or scope["method"] not in {"POST", "PATCH", "PUT"}
            or scope["path"] == "/api/v1/captures/import"
        ):
            await self.app(scope, receive, send)
            return
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > 1024 * 1024:
                await JSONResponse(
                    {
                        "error": {
                            "code": "payload_too_large",
                            "message": "JSON requests are limited to 1 MiB",
                        }
                    },
                    status_code=413,
                )(scope, receive, send)
                return
            if not message.get("more_body", False):
                break
        replayed = False

        async def replay():
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, replay, send)
