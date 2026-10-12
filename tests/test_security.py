"""Gateway claim 검증과 공통 오류 형식 테스트다."""

import hashlib
import hmac

from main_mcp_server_kodict.security import ClaimVerifier, require_scope


def test_signed_claim_allows_required_scope() -> None:
    """검증된 claim의 scope만 도구 실행 권한으로 사용한다."""
    claim = '{"subject_id":"user-1","scopes":["korean-standard-dictionary:read"],"request_id":"req-1"}'
    signature = hmac.new(b"secret", claim.encode(), hashlib.sha256).hexdigest()
    caller = ClaimVerifier("secret").verify(claim, signature)
    assert require_scope(caller, "korean-standard-dictionary:read") is None
    assert require_scope(caller, "korean-standard-dictionary:analyze")["error"]["code"] == "forbidden"


def test_unsigned_claim_is_rejected() -> None:
    """임의 헤더 값은 서명이 없으면 인증 정보가 될 수 없다."""
    assert ClaimVerifier("secret").verify('{"scopes":[]}', None) is None
