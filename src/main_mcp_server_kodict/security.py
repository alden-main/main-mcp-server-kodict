"""Gateway가 서명해 전달한 호출자 claim을 검증하는 모듈이다."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json


@dataclass(frozen=True)
class Caller:
    """검증을 통과한 Gateway 호출자 정보다."""

    subject_id: str
    scopes: frozenset[str]
    request_id: str


class ClaimVerifier:
    """공유 비밀 HMAC으로 보호된 내부 claim만 수락하는 검증기다."""

    def __init__(self, secret: str | None) -> None:
        self.secret = secret

    def verify(self, claim_json: str | None, signature: str | None) -> Caller | None:
        """서명과 필수 claim을 확인한다. 비밀이 없거나 검증 실패면 None을 반환한다."""
        if not self.secret or not claim_json or not signature:
            return None
        expected = hmac.new(self.secret.encode(), claim_json.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            return None
        try:
            payload = json.loads(claim_json)
            return Caller(str(payload["subject_id"]), frozenset(payload["scopes"]), str(payload["request_id"]))
        except (KeyError, TypeError, json.JSONDecodeError):
            return None


def require_scope(caller: Caller | None, scope: str) -> dict[str, object] | None:
    """도구에 필요한 scope를 확인하고 표준 오류 응답 또는 None을 반환한다."""
    if caller is None:
        return error("unauthenticated", "검증된 Gateway 호출자 정보가 필요합니다.", False)
    if scope not in caller.scopes:
        return error("forbidden", "이 도구에 필요한 권한이 없습니다.", False)
    return None


def error(code: str, message: str, retryable: bool) -> dict[str, object]:
    """내부 정보와 민감 원문을 포함하지 않는 공통 오류 계약을 만든다."""
    return {"error": {"code": code, "message": message, "retryable": retryable}}
