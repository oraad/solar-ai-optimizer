"""Static file serving with precompressed Brotli/gzip sidecar negotiation."""

from __future__ import annotations

import mimetypes
import os
from typing import Literal

from starlette.datastructures import Headers
from starlette.responses import FileResponse, Response
from starlette.staticfiles import NotModifiedResponse, StaticFiles
from starlette.types import Scope

Encoding = Literal["br", "gzip"]

_SIDECAR_EXT: dict[Encoding, str] = {"br": "br", "gzip": "gz"}


def _media_type_for(path: os.PathLike[str]) -> str | None:
    media_type, _encoding = mimetypes.guess_type(os.fspath(path), strict=False)
    return media_type


def _sidecar_path(full_path: os.PathLike[str], encoding: Encoding) -> str:
    return f"{os.fspath(full_path)}.{_SIDECAR_EXT[encoding]}"


def _accepts_encoding(request_headers: Headers, encoding: Encoding) -> bool:
    accept = request_headers.get("accept-encoding", "")
    return any(part.strip().split(";", 1)[0] == encoding for part in accept.split(","))


def _pick_encoding(request_headers: Headers, full_path: os.PathLike[str]) -> Encoding | None:
    path = os.fspath(full_path)
    if _accepts_encoding(request_headers, "br") and os.path.isfile(_sidecar_path(full_path, "br")):
        return "br"
    if _accepts_encoding(request_headers, "gzip") and os.path.isfile(_sidecar_path(full_path, "gzip")):
        return "gzip"
    return None


class CompressedStaticFiles(StaticFiles):
    """Serve `.br` / `.gz` sidecars when the client accepts them."""

    def file_response(
        self,
        full_path: os.PathLike[str],
        stat_result: os.stat_result,
        scope: Scope,
        status_code: int = 200,
    ) -> Response:
        request_headers = Headers(scope=scope)
        encoding = _pick_encoding(request_headers, full_path)
        if encoding is None:
            return super().file_response(full_path, stat_result, scope, status_code)

        sidecar = _sidecar_path(full_path, encoding)
        sidecar_stat = os.stat(sidecar)
        response = FileResponse(
            sidecar,
            status_code=status_code,
            stat_result=sidecar_stat,
            media_type=_media_type_for(full_path),
        )
        response.headers["Content-Encoding"] = encoding
        response.headers["Vary"] = "Accept-Encoding"
        if self.is_not_modified(response.headers, request_headers):
            return NotModifiedResponse(response.headers)
        return response
