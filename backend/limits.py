"""Bound request bodies before multipart/JSON parsing, including streamed uploads."""

from fastapi import HTTPException
from starlette.responses import JSONResponse


class RequestSizeLimit:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in ("POST", "PUT", "PATCH"):
            return await self.app(scope, receive, send)
        headers = dict(scope["headers"])
        multipart = scope["path"] == "/api/papers" and headers.get(
            b"content-type", b""
        ).startswith(b"multipart/form-data")
        limit = 52 * 1024 * 1024 if multipart else 64 * 1024
        detail = (
            "Upload request exceeds 52 MB. Upload one file of up to 50 MB at a time."
            if multipart
            else "Request body exceeds 64 KB."
        )
        try:
            length = int(headers.get(b"content-length", b"0"))
            if length < 0:
                raise ValueError
        except ValueError:
            return await JSONResponse(
                {"detail": "Invalid Content-Length."}, status_code=400
            )(scope, receive, send)
        if length > limit:
            return await JSONResponse({"detail": detail}, status_code=413)(
                scope, receive, send
            )
        size = 0

        async def bounded_receive():
            nonlocal size
            message = await receive()
            if message["type"] == "http.request":
                size += len(message.get("body", b""))
                if size > limit:
                    raise HTTPException(413, detail)
            return message

        await self.app(scope, bounded_receive, send)
