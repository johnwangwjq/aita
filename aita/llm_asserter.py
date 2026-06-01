from __future__ import annotations

import json
from typing import Any
from urllib.request import Request
from urllib.request import urlopen

from aita.models import AsserterConfig


SYSTEM_PROMPT = (
    "You are a strict test asserter. Return JSON only with keys: "
    "result (passed|failed), reason (string)."
)


def assert_round(
    asserter: AsserterConfig,
    input_text: str,
    endpoint_response: str,
    expected_response: str | None,
    fail_on: str | None,
    timeout: int,
) -> tuple[bool, str]:
    user_prompt = _build_user_prompt(
        input_text=input_text,
        endpoint_response=endpoint_response,
        expected_response=expected_response,
        fail_on=fail_on,
    )

    request_payload = _build_request_payload(user_prompt, asserter.invoke_options)

    request = Request(
        asserter.url,
        data=json.dumps(request_payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {asserter.api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    with urlopen(request, timeout=timeout) as response:
        response_data = json.loads(response.read().decode("utf-8"))

    content = response_data["choices"][0]["message"]["content"]
    parsed = json.loads(content)
    result = parsed["result"]
    reason = parsed.get("reason", "")

    if result not in {"passed", "failed"}:
        raise ValueError("Asserter returned invalid result. Expected passed|failed.")

    return (result == "passed", reason)


def _build_user_prompt(
    input_text: str,
    endpoint_response: str,
    expected_response: str | None,
    fail_on: str | None,
) -> str:
    return (
        "Evaluate one API round and decide if it should fail.\\n"
        f"Input: {input_text}\\n"
        f"Actual response: {endpoint_response}\\n"
        f"Expected response hint: {expected_response}\\n"
        f"Fail-on criteria: {fail_on}\\n"
        "If actual response meets fail-on criteria, result must be failed."
    )


def _build_request_payload(user_prompt: str, invoke_options: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": "openai/gpt-oss-20b",
        "temperature": 0,
    }
    payload.update(invoke_options)

    # Never allow config to override assertion prompt structure.
    payload["messages"] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    return payload
