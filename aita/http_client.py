from __future__ import annotations

import json
from urllib.request import HTTPCookieProcessor
from urllib.request import build_opener
from urllib.request import Request

from aita.models import AuthRequestSpec
from aita.models import EndpointResponse
from aita.models import RuntimeContext


def create_runtime_context(identity_mode: str) -> RuntimeContext:
    context = RuntimeContext(identity_mode=identity_mode)
    cookie_processor = HTTPCookieProcessor(context.cookie_jar)
    context.opener = build_opener(cookie_processor)
    return context


def call_endpoint(
    endpoint: str,
    input_text: str,
    timeout: int,
    context: RuntimeContext,
) -> EndpointResponse:
    method = "POST"
    resolved_endpoint = endpoint
    headers = {"Content-Type": "application/json"}

    payload = _build_payload(
        input_text=input_text,
        identity_mode=context.identity_mode,
        session_id=context.session_id,
    )
    request_body = json.dumps(payload).encode("utf-8")

    request = Request(
        resolved_endpoint,
        data=request_body,
        headers=headers,
        method=method,
    )
    with context.opener.open(request, timeout=timeout) as response:
        response_bytes = response.read()
        body = response_bytes.decode("utf-8")
        response_data = EndpointResponse(
            body=body,
            status_code=response.getcode(),
            headers={key: value for key, value in response.headers.items()},
        )

    _update_runtime_context(context, response_data)
    return response_data


def _build_payload(
    input_text: str,
    identity_mode: str,
    session_id: str | None,
) -> dict[str, object]:
    payload: dict[str, object] = {"message": input_text}

    if identity_mode == "anonymous" and session_id is not None:
        payload.setdefault("session_id", session_id)

    return payload


def run_auth_request(
    auth_request: AuthRequestSpec,
    timeout: int,
    context: RuntimeContext,
) -> EndpointResponse:
    request = Request(
        auth_request.endpoint,
        data=json.dumps(auth_request.body).encode("utf-8"),
        headers={"Content-Type": "application/json", **auth_request.headers},
        method=auth_request.method,
    )
    with context.opener.open(request, timeout=timeout) as response:
        response_bytes = response.read()
        body = response_bytes.decode("utf-8")
        return EndpointResponse(
            body=body,
            status_code=response.getcode(),
            headers={key: value for key, value in response.headers.items()},
        )


def _update_runtime_context(context: RuntimeContext, response: EndpointResponse) -> None:
    if context.identity_mode != "anonymous":
        return

    try:
        payload = json.loads(response.body)
    except json.JSONDecodeError:
        return
    if not isinstance(payload, dict):
        return

    session_id = payload.get("session_id")
    if isinstance(session_id, str) and session_id:
        context.session_id = session_id
