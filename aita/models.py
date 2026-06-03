from __future__ import annotations

from dataclasses import field
from dataclasses import dataclass
from http.cookiejar import CookieJar
from typing import Any
from typing import Literal


@dataclass(frozen=True)
class AsserterConfig:
    url: str
    api_key: str
    invoke_options: dict[str, Any]


@dataclass(frozen=True)
class RoundExpected:
    response: str | None
    fail_on: str | None
    status_code: int | None
    status_kind: str | None
    has_session_id: bool | None
    metadata_has: tuple[str, ...]


@dataclass(frozen=True)
class AuthRequestSpec:
    path: str
    method: str
    headers: dict[str, str]
    body: dict[str, Any]


@dataclass(frozen=True)
class IdentityConfig:
    login_required: bool
    authentication: AuthRequestSpec | None


@dataclass(frozen=True)
class RoundSpec:
    input_text: str
    expected: RoundExpected | None


@dataclass(frozen=True)
class TestSpec:
    name: str
    endpoint: str
    asserter: AsserterConfig
    identity: IdentityConfig
    pre_test: tuple[str, ...]
    post_test: tuple[str, ...]
    rounds: tuple[RoundSpec, ...]
    source_file: str
    source_document_index: int


@dataclass(frozen=True)
class EndpointResponse:
    body: str
    status_code: int
    headers: dict[str, str]


@dataclass
class RuntimeContext:
    identity_mode: Literal["legacy", "anonymous", "logged-in"]
    cookie_jar: CookieJar = field(default_factory=CookieJar)
    opener: Any | None = None
    session_id: str | None = None


@dataclass(frozen=True)
class RoundResult:
    index: int
    endpoint_response: str
    assertion_skipped: bool
    assertion_passed: bool
    failure_reason: str | None


@dataclass(frozen=True)
class TestResult:
    test_name: str
    source_file: str
    source_document_index: int
    passed: bool
    errored: bool
    error_message: str | None
    rounds_run: int
    rounds: tuple[RoundResult, ...]


@dataclass(frozen=True)
class RunSummary:
    total: int
    passed: int
    failed: int
    errored: int
    skipped_assertions: int
    tests: tuple[TestResult, ...]
