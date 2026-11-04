"""Bounded HTTP relay envelopes on a separate authenticated worker socket."""

import base64
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator

from shared.contracts import ContractModel, Port

BODY_LIMIT = 4 * 1024 * 1024
FRAME_LIMIT = 6 * 1024 * 1024
HOP_HEADERS = {
    "host",
    "connection",
    "keep-alive",
    "transfer-encoding",
    "upgrade",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
}


def encode_body(value: bytes) -> str:
    if len(value) > BODY_LIMIT:
        raise ValueError("HTTP relay body exceeds 4 MiB")
    return base64.b64encode(value).decode("ascii")


def decode_body(value: str) -> bytes:
    body = base64.b64decode(value, validate=True)
    if len(body) > BODY_LIMIT:
        raise ValueError("HTTP relay body exceeds 4 MiB")
    return body


class RelayEnvelope(ContractModel):
    request_id: UUID
    headers: list[tuple[str, str]] = Field(default_factory=list, max_length=128)
    body: str = Field(default="", max_length=4 * ((BODY_LIMIT + 2) // 3))

    @field_validator("headers")
    @classmethod
    def valid_headers(cls, pairs):
        import re

        if sum(len(k) + len(v) for k, v in pairs) > 65536:
            raise ValueError("Relay headers exceed size limit")
        for key, value in pairs:
            if not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", key):
                raise ValueError("Invalid HTTP header name")
            if any(c in value for c in "\r\n\x00") or len(value) > 16384:
                raise ValueError("Invalid HTTP header value")
        return pairs

    @field_validator("body")
    @classmethod
    def valid_body(cls, value):
        decode_body(value)
        return value


class RelayRequest(RelayEnvelope):
    type: Literal["app_http_request"] = "app_http_request"
    deployment_id: UUID
    container_id: str = Field(min_length=1, max_length=256)
    internal_port: Port
    method: Literal["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
    path: str = Field(max_length=8192)
    query: str = Field(default="", max_length=8192)

    @field_validator("path")
    @classmethod
    def valid_path(cls, value):
        if (
            not value.startswith("/")
            or value.startswith("//")
            or any(c in value for c in "\r\n\x00\\?#")
        ):
            raise ValueError("Relay path must be an origin-relative HTTP path")
        return value

    @field_validator("query")
    @classmethod
    def valid_query(cls, value):
        if any(c in value for c in "\r\n\x00#"):
            raise ValueError("Invalid relay query")
        return value


class RelayResponse(RelayEnvelope):
    type: Literal["app_http_response"] = "app_http_response"
    status: int = Field(ge=200, le=599)
