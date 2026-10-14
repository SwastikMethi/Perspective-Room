"""Serve the built React app from the API origin. /api paths never fall back to HTML.

The SPA fallback is a 404 handler rather than a catch-all route, so it can never shadow a route.
"""

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.errors import error_response


def mount_spa(app: FastAPI, static_dir: Path) -> None:
    index = static_dir / "index.html"
    assets = (static_dir / "assets").resolve()

    @app.get("/assets/{path:path}", include_in_schema=False)
    async def asset(path: str) -> FileResponse:
        file = (assets / path).resolve()
        if not file.is_relative_to(assets) or not file.is_file():
            raise HTTPException(404, "Not found")
        # Vite hashes asset names, so they can be cached forever.
        return FileResponse(file, headers={"Cache-Control": "public, max-age=31536000, immutable"})

    async def not_found(request: Request, exc: Exception) -> Response:
        path = request.url.path
        spa_path = not (path == "/api" or path.startswith(("/api/", "/assets/")))
        if request.method == "GET" and spa_path and index.is_file():
            return FileResponse(index, headers={"Cache-Control": "no-cache"})
        detail = exc.detail if isinstance(exc, StarletteHTTPException) else "Not found"
        return error_response(request, 404, "not_found", str(detail))

    app.add_exception_handler(404, not_found)
