"""Bounded HTTP exchange through a relay or an explicitly registered direct host."""

from uuid import uuid4

import httpx
from shared.relay import (
    BODY_LIMIT,
    HOP_HEADERS,
    RelayRequest,
    RelayResponse,
    decode_body,
    encode_body,
)


async def application_http(
    ctx,
    worker_id,
    transport,
    address,
    host_port,
    deployment_id,
    container_id,
    internal_port,
    method,
    path,
    query="",
    headers=None,
    body=b"",
    timeout=25,
):
    message = RelayRequest(
        request_id=uuid4(),
        deployment_id=deployment_id,
        container_id=container_id,
        internal_port=internal_port,
        method=method,
        path=path,
        query=query,
        headers=headers or [],
        body=encode_body(body),
    )
    if transport == "relay":
        return await ctx.relay.request(worker_id, message, timeout=timeout)
    if transport != "direct":
        raise ConnectionError("Unsupported worker application transport")
    url = httpx.URL(
        scheme="http",
        host=address,
        port=host_port,
        path=path,
        query=query.encode() or None,
    )
    async with (
        httpx.AsyncClient(
            timeout=timeout, trust_env=False, follow_redirects=False
        ) as client,
        client.stream(
            method, url, headers=headers, content=decode_body(message.body)
        ) as response,
    ):
        data = bytearray()
        async for chunk in response.aiter_raw():
            data.extend(chunk)
            if len(data) > BODY_LIMIT:
                raise ValueError("Application response exceeds 4 MiB")
        return RelayResponse(
            request_id=message.request_id,
            status=response.status_code,
            headers=[
                (k, v)
                for k, v in response.headers.multi_items()
                if k.lower() not in HOP_HEADERS
            ],
            body=encode_body(bytes(data)),
        )
