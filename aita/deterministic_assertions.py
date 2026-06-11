from __future__ import annotations

import json

from aita.models import EndpointResponse
from aita.models import RoundExpected


def _resolve_metadata_path(metadata_obj: dict, path: str) -> tuple[bool, object]:
    """Traverse a dotted path in metadata. Returns (found, value)."""
    parts = path.split(".")
    current: object = metadata_obj
    for part in parts:
        if not isinstance(current, dict) or part not in current:
            return False, None
        current = current[part]
    return True, current


def assert_deterministic_expectations(
    expected: RoundExpected,
    endpoint_response: EndpointResponse,
) -> tuple[bool, str | None]:
    if expected.status_code is not None and endpoint_response.status_code != expected.status_code:
        return (
            False,
            f"Expected status code {expected.status_code}, got {endpoint_response.status_code}",
        )

    needs_json = (
        expected.status_kind is not None
        or expected.has_session_id is not None
        or len(expected.metadata_has) > 0
    )
    payload: dict[str, object] | None = None

    if needs_json:
        try:
            decoded = json.loads(endpoint_response.body)
        except json.JSONDecodeError:
            return False, "Expected JSON response for deterministic checks"
        if not isinstance(decoded, dict):
            return False, "Expected JSON object response for deterministic checks"
        payload = decoded

    if expected.status_kind is not None:
        status_obj = payload.get("status") if payload is not None else None
        if not isinstance(status_obj, dict):
            return False, "Missing status object in response"
        actual_kind = status_obj.get("kind")
        if actual_kind != expected.status_kind:
            return False, f"Expected status.kind={expected.status_kind}, got {actual_kind}"

    if expected.has_session_id is not None:
        has_session_id = isinstance((payload or {}).get("session_id"), str) and bool((payload or {}).get("session_id"))
        if has_session_id != expected.has_session_id:
            return False, f"Expected has session_id={expected.has_session_id}, got {has_session_id}"

    if expected.metadata_has:
        metadata_obj = payload.get("metadata") if payload is not None else None
        if not isinstance(metadata_obj, dict):
            return False, "Missing metadata object in response"
        for entry in expected.metadata_has:
            if "=" in entry:
                path, expected_val = entry.split("=", 1)
                found, actual = _resolve_metadata_path(metadata_obj, path)
                if not found:
                    return False, f"Expected metadata path not found: {path}"
                if actual != expected_val:
                    return False, f"Expected metadata.{path}={expected_val!r}, got {actual!r}"
            else:
                found, _ = _resolve_metadata_path(metadata_obj, entry)
                if not found:
                    return False, f"Expected metadata key not found: {entry}"

    return True, None


def should_run_llm_assertion(expected: RoundExpected) -> bool:
    return expected.like is not None or expected.fail_on is not None
