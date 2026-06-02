from __future__ import annotations

import json
from urllib.request import Request
from urllib.request import urlopen


def build_endpoint_payload(input_text: str) -> dict[str, str]:
    #TODO: Deferred extension point: replace with a project-specific payload mapping.
    return {"input": input_text}


def call_endpoint(endpoint: str, input_text: str, timeout: int) -> str:
    payload = build_endpoint_payload(input_text)
    request_body = json.dumps(payload).encode("utf-8")
    request = Request(
        endpoint,
        data=request_body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=timeout) as response:
        response_bytes = response.read()

    return response_bytes.decode("utf-8")
