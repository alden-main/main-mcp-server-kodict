"""Streamable HTTP MCP 도구와 비민감 healthcheck를 제공하는 진입점이다."""

from __future__ import annotations

import logging
from typing import Annotated

from mcp.server.fastmcp import Context, FastMCP
from starlette.responses import PlainTextResponse
from starlette.routing import Route

from .config import Settings
from .dictionary import DictionaryRepository
from .morphology import MorphologyAnalyzer
from .review import TextReviewer
from .recommendations import RecommendationCatalog
from .security import ClaimVerifier, error, require_scope

SERVICE_ID = "korean-standard-dictionary"
logger = logging.getLogger(__name__)


def create_server(settings: Settings | None = None) -> FastMCP:
    """의존성을 조립하고 `/mcp` 도구와 `/healthz`를 갖춘 MCP 서버를 만든다.

    Args:
        settings: 테스트 또는 배포 환경별 런타임 설정이다.

    Returns:
        Streamable HTTP 전송으로 실행할 준비가 된 FastMCP 인스턴스다.
    """
    settings = settings or Settings()
    repository = DictionaryRepository(settings.database_path)
    verifier = ClaimVerifier(settings.claim_secret)
    try:
        catalog = RecommendationCatalog.from_path(settings.recommendation_data_path)
        reviewer = TextReviewer(repository, MorphologyAnalyzer(), settings.max_candidates, catalog)
    except Exception:
        reviewer = None
    mcp = FastMCP(SERVICE_ID, host=settings.host, port=settings.port, streamable_http_path="/mcp", stateless_http=True, max_request_body_size=settings.max_text_length * 4)

    def caller(context: Context) -> object:
        request = context.request_context.request
        headers = getattr(request, "headers", {})
        return verifier.verify(headers.get("x-gateway-claim"), headers.get("x-gateway-claim-signature"))

    def audit(tool_name: str, result_code: str, context: Context) -> None:
        verified_caller = caller(context)
        request_id = verified_caller.request_id if verified_caller else "unverified"
        logger.info("audit service_id=%s service_version=%s tool=%s request_id=%s result=%s", SERVICE_ID, settings.service_version, tool_name, request_id, result_code)

    @mcp.tool()
    def lookup_standard_dictionary(query: Annotated[str, "조회할 표제어 또는 이형태"], context: Context) -> dict[str, object]:
        """표제어 또는 검색용 이형태를 색인에서 정확 조회한다."""
        denied = require_scope(caller(context), f"{SERVICE_ID}:read")
        if denied:
            audit("lookup_standard_dictionary", denied["error"]["code"], context)
            return denied
        if not isinstance(query, str) or not query.strip():
            return error("invalid_input", "query는 비어 있지 않은 문자열이어야 합니다.", False)
        if len(query) > settings.max_text_length:
            return error("request_too_large", "query가 허용 길이를 초과했습니다.", False)
        try:
            entries = repository.lookup(query, settings.max_results)
        except Exception:
            return error("upstream_unavailable", "사전 DB를 현재 조회할 수 없습니다.", True)
        audit("lookup_standard_dictionary", "ok" if entries else "not_found", context)
        return {"entries": [entry.as_dict() for entry in entries]} if entries else error("not_found", "일치하는 사전 항목이 없습니다.", False)

    @mcp.tool()
    def review_standard_korean_text(text: Annotated[str, "검토할 한국어 문서 텍스트"], context: Context) -> dict[str, object]:
        """형태소 단위를 사전 근거와 함께 검토하되 자동 교정을 확정하지 않는다."""
        denied = require_scope(caller(context), f"{SERVICE_ID}:analyze")
        if denied:
            audit("review_standard_korean_text", denied["error"]["code"], context)
            return denied
        if not isinstance(text, str) or not text.strip():
            return error("invalid_input", "text는 비어 있지 않은 문자열이어야 합니다.", False)
        if len(text) > settings.max_text_length:
            return error("request_too_large", "text가 허용 길이를 초과했습니다.", False)
        if reviewer is None or not repository.is_ready():
            return error("upstream_unavailable", "분석기 또는 사전 DB를 사용할 수 없습니다.", True)
        result = reviewer.review(text)
        audit("review_standard_korean_text", "ok", context)
        return result

    async def healthz(request: object) -> PlainTextResponse:
        """민감한 내부 상태를 노출하지 않고 DB·분석기 준비 상태만 HTTP 상태로 반환한다."""
        return PlainTextResponse("ok" if reviewer is not None and repository.is_ready() else "unavailable", status_code=200 if reviewer is not None and repository.is_ready() else 503)

    mcp._custom_starlette_routes = [Route("/healthz", healthz)]
    return mcp


def main() -> None:
    """운영 전송인 Streamable HTTP 모드로 MCP 서버를 시작한다."""
    create_server().run(transport="streamable-http")
