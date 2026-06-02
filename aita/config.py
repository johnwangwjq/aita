from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from aita.models import AuthRequestSpec
from aita.models import AsserterConfig
from aita.models import IdentityConfig
from aita.models import RoundExpected
from aita.models import RoundSpec
from aita.models import TestSpec

_ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
_DOTENV_LINE_PATTERN = re.compile(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$")
_SHARED_KEYS = ("endpoint", "asserter", "identity", "pre-test", "post-test")


def load_dotenv(cwd: Path) -> None:
    dotenv_path = cwd / ".env"
    if not dotenv_path.exists():
        return

    lines = dotenv_path.read_text(encoding="utf-8").splitlines()
    for index, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        match = _DOTENV_LINE_PATTERN.match(line)
        if match is None:
            raise ValueError(f"Invalid .env line {index} in {dotenv_path}")

        key = match.group(1)
        value = _normalize_dotenv_value(match.group(2).strip())
        os.environ.setdefault(key, value)


def _normalize_dotenv_value(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def require_global_config(cwd: Path) -> dict[str, Any]:
    global_path = cwd / "aita.yaml"
    if not global_path.exists():
        raise ValueError(f"Missing required global config: {global_path}")
    return _read_yaml_single(global_path)


def load_suite_config(path: Path) -> dict[str, Any]:
    if path.is_file():
        suite_config_path = path.parent / "aita.yaml"
    else:
        suite_config_path = path / "aita.yaml"

    if not suite_config_path.exists():
        return {}
    return _read_yaml_single(suite_config_path)


def load_test_documents(test_file: Path) -> list[dict[str, Any]]:
    raw_docs = list(yaml.safe_load_all(test_file.read_text(encoding="utf-8")))
    docs = [doc for doc in raw_docs if doc is not None]
    if not docs:
        raise ValueError(f"No YAML test documents in {test_file}")
    for doc in docs:
        if not isinstance(doc, dict):
            raise ValueError(f"Each YAML document must be an object in {test_file}")
    return docs


def build_test_specs(
    test_file: Path,
    test_documents: list[dict[str, Any]],
    global_config: dict[str, Any],
    suite_config: dict[str, Any],
) -> list[TestSpec]:
    specs: list[TestSpec] = []
    for index, doc in enumerate(test_documents, start=1):
        merged = merge_configs(global_config, suite_config, doc)
        expanded = _expand_env_vars(merged)
        specs.append(_to_test_spec(expanded, test_file, index))
    return specs


def merge_configs(
    global_config: dict[str, Any],
    suite_config: dict[str, Any],
    test_document: dict[str, Any],
) -> dict[str, Any]:
    merged = dict(test_document)

    merged_asserter = _merge_asserter_configs(
        global_config.get("asserter"),
        suite_config.get("asserter"),
        test_document.get("asserter"),
    )
    if merged_asserter is not None:
        merged["asserter"] = merged_asserter

    for key in _SHARED_KEYS:
        if key == "asserter":
            continue
        if key in test_document:
            continue
        if key in suite_config:
            merged[key] = suite_config[key]
            continue
        if key in global_config:
            merged[key] = global_config[key]
    return merged


def _merge_asserter_configs(
    global_asserter: Any,
    suite_asserter: Any,
    test_asserter: Any,
) -> dict[str, Any] | None:
    merged: dict[str, Any] = {}
    has_any = False

    for source in (global_asserter, suite_asserter, test_asserter):
        if source is None:
            continue
        if not isinstance(source, dict):
            raise ValueError("Asserter config must be a YAML object")

        has_any = True
        for key, value in source.items():
            if key == "invoke-options":
                if value is None:
                    continue
                if not isinstance(value, dict):
                    raise ValueError("Asserter invoke-options must be a YAML object")

                current = merged.get("invoke-options", {})
                if not isinstance(current, dict):
                    current = {}
                merged["invoke-options"] = {**current, **value}
                continue

            merged[key] = value

    if not has_any:
        return None
    return merged


def _to_test_spec(data: dict[str, Any], source_file: Path, doc_index: int) -> TestSpec:
    if "name" not in data:
        raise ValueError(_key_error(source_file, doc_index, "name"))
    if "rounds" not in data:
        raise ValueError(_key_error(source_file, doc_index, "rounds"))

    rounds_obj = data["rounds"]
    if not isinstance(rounds_obj, list) or not rounds_obj:
        raise ValueError(_key_error(source_file, doc_index, "rounds must be a non-empty list"))

    endpoint = data.get("endpoint")
    if not isinstance(endpoint, str) or not endpoint:
        raise ValueError(_key_error(source_file, doc_index, "endpoint"))
    parsed_endpoint = urlparse(endpoint)
    if not parsed_endpoint.scheme or not parsed_endpoint.netloc:
        raise ValueError(_key_error(source_file, doc_index, "endpoint must be an absolute URL"))

    asserter_obj = data.get("asserter")
    if not isinstance(asserter_obj, dict):
        raise ValueError(_key_error(source_file, doc_index, "asserter"))

    asserter_url = asserter_obj.get("url")
    asserter_api_key = asserter_obj.get("api-key")
    asserter_invoke_options = asserter_obj.get("invoke-options", {})
    if not isinstance(asserter_url, str) or not asserter_url:
        raise ValueError(_key_error(source_file, doc_index, "asserter.url"))
    if not isinstance(asserter_api_key, str) or not asserter_api_key:
        raise ValueError(_key_error(source_file, doc_index, "asserter.api-key"))
    if asserter_invoke_options is None:
        asserter_invoke_options = {}
    if not isinstance(asserter_invoke_options, dict):
        raise ValueError(_key_error(source_file, doc_index, "asserter.invoke-options"))

    pre_test = _to_string_tuple(data.get("pre-test", []), source_file, doc_index, "pre-test")
    post_test = _to_string_tuple(data.get("post-test", []), source_file, doc_index, "post-test")
    identity = _parse_identity(data.get("identity", {}), source_file, doc_index)

    rounds: list[RoundSpec] = []
    for round_index, round_obj in enumerate(rounds_obj, start=1):
        if not isinstance(round_obj, dict):
            raise ValueError(_key_error(source_file, doc_index, f"rounds[{round_index}]"))

        input_text = round_obj.get("input")
        if not isinstance(input_text, str) or not input_text:
            raise ValueError(_key_error(source_file, doc_index, f"rounds[{round_index}].input"))

        expected_obj = round_obj.get("expected")
        if expected_obj is None:
            expected = None
        else:
            if not isinstance(expected_obj, dict):
                raise ValueError(_key_error(source_file, doc_index, f"rounds[{round_index}].expected"))
            response = expected_obj.get("response")
            fail_on = expected_obj.get("fail-on")
            status_code = expected_obj.get("status-code")
            status_kind = expected_obj.get("status-kind")
            has_session_id = expected_obj.get("has-session-id")
            metadata_has = expected_obj.get("metadata-has", [])
            if response is not None and not isinstance(response, str):
                raise ValueError(_key_error(source_file, doc_index, f"rounds[{round_index}].expected.response"))
            if fail_on is not None and not isinstance(fail_on, str):
                raise ValueError(_key_error(source_file, doc_index, f"rounds[{round_index}].expected.fail-on"))
            if status_code is not None and not isinstance(status_code, int):
                raise ValueError(_key_error(source_file, doc_index, f"rounds[{round_index}].expected.status-code"))
            if status_kind is not None and not isinstance(status_kind, str):
                raise ValueError(_key_error(source_file, doc_index, f"rounds[{round_index}].expected.status-kind"))
            if has_session_id is not None and not isinstance(has_session_id, bool):
                raise ValueError(_key_error(source_file, doc_index, f"rounds[{round_index}].expected.has-session-id"))
            metadata_has_tuple = _to_string_tuple(
                metadata_has,
                source_file,
                doc_index,
                f"rounds[{round_index}].expected.metadata-has",
            )
            expected = RoundExpected(
                response=response,
                fail_on=fail_on,
                status_code=status_code,
                status_kind=status_kind,
                has_session_id=has_session_id,
                metadata_has=metadata_has_tuple,
            )

        rounds.append(RoundSpec(input_text=input_text, expected=expected))

    return TestSpec(
        name=str(data["name"]),
        endpoint=endpoint,
        asserter=AsserterConfig(
            url=asserter_url,
            api_key=asserter_api_key,
            invoke_options=asserter_invoke_options,
        ),
        identity=identity,
        pre_test=pre_test,
        post_test=post_test,
        rounds=tuple(rounds),
        source_file=str(source_file),
        source_document_index=doc_index,
    )


def _to_string_tuple(
    value: Any,
    source_file: Path,
    doc_index: int,
    key: str,
) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError(_key_error(source_file, doc_index, key))
    if not all(isinstance(item, str) and item for item in value):
        raise ValueError(_key_error(source_file, doc_index, key))
    return tuple(value)


def _parse_identity(value: Any, source_file: Path, doc_index: int) -> IdentityConfig:
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise ValueError(_key_error(source_file, doc_index, "identity"))

    mode_obj = value.get("mode", "legacy")
    if mode_obj not in {"legacy", "anonymous", "logged-in"}:
        raise ValueError(_key_error(source_file, doc_index, "identity.mode"))
    mode = str(mode_obj)

    auth_request = _parse_auth_request(
        value.get("auth-request"),
        source_file,
        doc_index,
        "identity.auth-request",
    )
    if mode == "logged-in" and auth_request is None:
        raise ValueError(_key_error(source_file, doc_index, "identity.auth-request"))

    return IdentityConfig(mode=mode, auth_request=auth_request)


def _parse_auth_request(
    value: Any,
    source_file: Path,
    doc_index: int,
    key: str,
) -> AuthRequestSpec | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError(_key_error(source_file, doc_index, key))

    endpoint = value.get("endpoint")
    if not isinstance(endpoint, str) or not endpoint:
        raise ValueError(_key_error(source_file, doc_index, f"{key}.endpoint"))
    parsed_endpoint = urlparse(endpoint)
    if not parsed_endpoint.scheme or not parsed_endpoint.netloc:
        raise ValueError(_key_error(source_file, doc_index, f"{key}.endpoint must be an absolute URL"))

    method_obj = value.get("method", "POST")
    if not isinstance(method_obj, str) or not method_obj:
        raise ValueError(_key_error(source_file, doc_index, f"{key}.method"))
    method = method_obj.upper()

    headers = _to_string_map(value.get("headers", {}), source_file, doc_index, f"{key}.headers")

    body = value.get("body")
    if body is None:
        body = {}
    if not isinstance(body, dict):
        raise ValueError(_key_error(source_file, doc_index, f"{key}.body"))

    return AuthRequestSpec(
        endpoint=endpoint,
        method=method,
        headers=headers,
        body=body,
    )


def _to_string_map(value: Any, source_file: Path, doc_index: int, key: str) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(_key_error(source_file, doc_index, key))

    normalized: dict[str, str] = {}
    for raw_key, raw_value in value.items():
        if not isinstance(raw_key, str) or not raw_key:
            raise ValueError(_key_error(source_file, doc_index, key))
        if not isinstance(raw_value, str):
            raise ValueError(_key_error(source_file, doc_index, key))
        normalized[raw_key] = raw_value
    return normalized


def _expand_env_vars(value: Any) -> Any:
    if isinstance(value, str):
        return _expand_string(value)
    if isinstance(value, list):
        return [_expand_env_vars(item) for item in value]
    if isinstance(value, dict):
        return {key: _expand_env_vars(item) for key, item in value.items()}
    return value


def _expand_string(value: str) -> str:
    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in os.environ:
            raise ValueError(f"Missing required environment variable: {key}")
        return os.environ[key]

    return _ENV_PATTERN.sub(replace, value)


def _read_yaml_single(file_path: Path) -> dict[str, Any]:
    data = yaml.safe_load(file_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Config must be a YAML object: {file_path}")
    return data


def _key_error(source_file: Path, doc_index: int, key: str) -> str:
    return f"Missing or invalid key '{key}' in {source_file} (document {doc_index})"
