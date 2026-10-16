"""Firebase sign-in helpers served from the app's own domain (Firebase: "proxy auth requests").

The sign-in flow keeps state in the auth domain's storage. When that domain (<project>.firebaseapp.com)
is not the app's domain, Safari (ITP) and other browsers that partition third-party storage lose it:
"Unable to process request due to missing initial state" (seen on 2026-10-16 in Safari on iOS).
Serving /__/auth/* from the app's domain and setting it as authDomain keeps the flow first-party.

Only GET requests to the /__/auth/ paths are forwarded, to one fixed upstream: this is not an open proxy.
"""

from __future__ import annotations

import re

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

ALLOWED_PATH = r"[A-Za-z0-9_.-]{1,64}"  # handler, handler.js, iframe, iframe.js, experiments.js…
FORWARDED_HEADERS = ("content-type", "cache-control", "etag", "last-modified")


def auth_proxy(upstream_host: str, client: httpx.AsyncClient | None = None) -> APIRouter:
    router = APIRouter()
    http = client or httpx.AsyncClient(timeout=10, follow_redirects=False)

    @router.get("/__/auth/{path}", include_in_schema=False)
    async def forward(path: str, request: Request) -> Response:
        if not re.fullmatch(ALLOWED_PATH, path):
            raise HTTPException(status_code=404)
        try:
            upstream = await http.get(
                f"https://{upstream_host}/__/auth/{path}",
                params=list(request.query_params.multi_items()),
                headers={"Accept": request.headers.get("accept", "*/*")},
            )
        except httpx.HTTPError as e:
            raise HTTPException(status_code=502, detail="sign-in helper unavailable") from e
        headers = {k: v for k, v in upstream.headers.items() if k.lower() in FORWARDED_HEADERS}
        return Response(content=upstream.content, status_code=upstream.status_code, headers=headers)

    return router
