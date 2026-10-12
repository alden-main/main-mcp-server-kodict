# 표준어 사전 MCP Gateway 연동 계약

이 문서는 Gateway가 `korean-standard-dictionary` 서비스를 등록하고, 도구를 발견·인가·호출·관찰하기 위해 필요한 현재 구현 계약을 정의한다. Gateway Bridge의 구현, 외부 인증, 인터넷 공개 경로는 이 서비스 범위 밖이다.

## 서비스 등록 정보

| 항목 | 값 |
|---|---|
| service_id | `korean-standard-dictionary` |
| service_version | `0.1.0` |
| tool_contract_version | `v1` |
| 내부 endpoint | `/mcp` |
| transport | `streamable-http` |
| data classification | `sensitive-text` |
| 상태 변경 | 없음. 모든 도구는 읽기 전용·무상태이다. |
| 내부 기본 주소 | `http://korean-standard-dictionary:8000/mcp` |

Gateway는 MCP Streamable HTTP의 초기화와 `tools/list`를 사용해 도구 schema를 발견할 수 있다. 이 서버는 현재 MCP resource나 prompt, REST 조회 API, DB 파일 다운로드 기능을 제공하지 않는다. 등록·라우팅 키는 `service_id`와 도구명 조합을 사용한다.

## 제공 기능

| 도구 | 목적 | 필요 scope | 입력 | 성공 출력 |
|---|---|---|---|---|
| `lookup_standard_dictionary` | 표제어·검색용 이형태를 정확 일치 조회한다. | `korean-standard-dictionary:read` | `query: string` | `entries` 배열과 항목별 사전 근거 |
| `review_standard_korean_text` | Kiwi 형태소 단위로 문서를 검토하고 사전 근거가 있는 상태·후보를 반환한다. 자동 교정을 확정하지 않는다. | `korean-standard-dictionary:analyze` | `text: string` | `findings`, `warnings` |

`lookup_standard_dictionary`의 `entries` 항목은 아래와 같다.

```json
{
  "entry_id": "1595068_30000.xls:2",
  "surface": "표면형",
  "evidence": {
    "headword": "원본 어휘",
    "pronunciation": "원본 발음",
    "part_of_speech": "원본 품사",
    "definition": "원본 뜻풀이",
    "source": {"file_name": "원본.xls", "row_number": 2, "source_hash": "sha256"}
  }
}
```

`review_standard_korean_text`의 응답 구조는 다음과 같다. `start`와 `end`는 유니코드 코드 포인트 오프셋이고 `end`는 배타적이다. `source_text`는 반드시 요청 원문의 해당 슬라이스이며, `analysis_form`은 Kiwi 분석형이므로 둘은 활용형에서 다를 수 있다. 후보는 승인된 버전의 규범 관계와 사전 정확 조회 근거가 모두 있을 때만 반환되며, `needs_review`는 자동 적용 지시가 아니다.

```json
{
  "findings": [{"start": 0, "end": 2, "source_text": "원문 구간", "analysis_form": "분석형", "status": "matched | not_found | needs_review", "candidates": [{"replacement": "권장 표기", "confidence": 0.98, "reason": "규칙 ID와 규범 데이터 버전", "surface": "표면형", "entry_id": "항목 ID", "evidence": {}}]}],
  "warnings": [{"code": "analysis_incomplete", "retryable": false}]
}
```

`not_found`는 비표준어라는 확정이 아니다. `needs_review` 또는 `analysis_incomplete`는 분석·문맥·후보 수 때문에 자동 판단할 수 없다는 뜻이며, Gateway나 호출 클라이언트가 이를 확정 교정으로 바꾸면 안 된다. 후보는 사전 항목 근거가 있을 때만 포함된다.

추천 관계는 이미지에 포함된 버전 관리 데이터 `standard_recommendations.v1.json`으로 제공하며, 운영 배포에서는 `KODICT_RECOMMENDATION_DATA_PATH`로 승인된 동일 형식의 읽기 전용 파일을 지정할 수 있다. 각 규칙은 규칙 ID, 규범 출처, 적용 품사, 데이터 버전과 confidence를 갖는다. 사전 미등재 대상, 고유명사(`NNP`), 인용문 내부는 후보를 생성하지 않는다.

매핑 데이터가 비어 있더라도 서버는 제한된 내장 활용·철자 규칙으로 후보를 생성할 수 있다. 현재 내장 규칙은 `되요 → 돼요`, `됬(다/어요/습니다/지만) → 됐(다/어요/습니다/지만)`뿐이다. 이는 후보 생성 단계일 뿐이며, 변환 결과가 활성 사전 DB에 정확히 등재된 경우에만 `needs_review` 후보로 반환한다. 일반적인 편집거리·유사도·LLM 생성 후보는 반환하지 않는다.

## 인증·인가 및 claim 전달

Gateway는 외부 인증과 정책 평가를 수행한 뒤에만 내부 MCP 서버로 요청을 전달한다. 이 서버는 방어적으로 scope를 재검증한다. 단순한 임의 헤더는 신뢰하지 않는다.

1. Gateway는 최소 `subject_id`, `scopes`, `request_id`가 있는 JSON claim을 만든다.
2. claim JSON의 **전송하는 UTF-8 바이트 그대로**를 `KODICT_GATEWAY_CLAIM_SECRET`으로 HMAC-SHA256 서명한다.
3. 원문 claim을 `X-Gateway-Claim`, 16진수 소문자 서명을 `X-Gateway-Claim-Signature`로 전달한다.
4. 이 컨테이너에는 동일한 비밀을 `KODICT_GATEWAY_CLAIM_SECRET` 환경 변수로 주입한다.

claim 예시는 다음과 같다. Gateway는 JSON을 다시 정렬·축약해 서명과 다른 바이트열로 만들면 안 된다.

```json
{"subject_id":"gateway-user-123","scopes":["korean-standard-dictionary:read"],"request_id":"req-01"}
```

claim·서명이 없거나 HMAC 검증에 실패하면 `unauthenticated`, scope가 부족하면 `forbidden`이 반환된다. `request_id`는 서버 감사 로그의 연결 키로 사용된다. 원래의 Authorization 토큰, claim 원문, 문서 원문은 서버 로그에 기록하지 않는다.

## 오류 및 한도

도구 수준의 예상 오류는 모두 다음 형식이다.

```json
{"error": {"code": "invalid_input", "message": "민감 정보가 없는 설명", "retryable": false}}
```

| 코드 | Gateway 처리 |
|---|---|
| `invalid_input` | 재시도하지 않고 호출자에게 입력 오류로 전달 |
| `unauthenticated`, `forbidden` | 재시도하지 않고 Gateway 인증·인가 결과로 처리 |
| `not_found` | 정상적인 조회 결과로 처리. 자동 교정하지 않음 |
| `request_too_large` | 재시도하지 않고 입력을 축소하도록 안내 |
| `upstream_unavailable` | 재시도 가능. DB 또는 분석기 준비 상태를 확인 |
| `internal_error` | 일시적 재시도 정책에 따라 처리 |

기본 상한은 텍스트 10,000 코드 포인트, 조회 결과 20개, 검토 후보 10개다. Gateway의 본문·도구 timeout·rate limit 상한은 이보다 보수적으로 구성해야 한다. 이 서버에는 호출자별 rate limiter가 없으므로 Gateway가 rate limiting의 주 책임을 가진다.

## 네트워크·배포·상태 확인

컨테이너는 `KODICT_HOST`(기본 `0.0.0.0`)와 `KODICT_PORT`(기본 `8000`)에서 리스닝한다. 제공하는 [compose.yaml](../compose.yaml)은 이 서비스를 외부 Docker 네트워크 `mcp-gateway-network`에만 연결한다. Gateway도 같은 네트워크에 연결해야 하며, MCP 서버는 AI 서비스용 네트워크에는 연결하지 않는다. `expose: 8000`만 사용하고 host `ports`는 열지 않는다. 각 MCP 컨테이너는 내부적으로 모두 `8000`을 사용해도 되며 Gateway는 Compose 서비스 이름으로 구분한다.

| 항목 | 값 |
|---|---|
| healthcheck | `GET /healthz` |
| 정상 | HTTP `200`, 본문 `ok` |
| 비정상 | HTTP `503`, 본문 `unavailable` |
| 활성 DB | `/app/data/korean_standard_dictionary.sqlite3` 읽기 전용 마운트 |

`/healthz`가 200일 때만 Gateway의 백엔드 풀에 넣는다. 이 검사는 SQLite DB의 읽기·무결성과 Kiwi 분석기 초기화를 확인하며 민감한 세부 정보를 반환하지 않는다. DB가 없거나 검증에 실패하면 도구는 `upstream_unavailable`을 반환한다.

런타임 이미지에는 XLS 원본과 DB 빌드 작업을 포함하지 않는다. `data/releases/<version>/korean_standard_dictionary.sqlite3`처럼 검증한 DB만 읽기 전용으로 마운트한다. Gateway는 사전 DB나 원본 XLS를 호출자에게 제공하거나 프록시하면 안 된다.

## Gateway 구현 확인 목록

- [ ] `korean-standard-dictionary`를 내부 Streamable HTTP MCP 서비스로 등록했다.
- [ ] 서비스별로 `read`와 `analyze` scope를 Gateway 단계에서 검사한다.
- [ ] 동일한 `KODICT_GATEWAY_CLAIM_SECRET`을 Gateway와 MCP 컨테이너에 안전하게 주입했다.
- [ ] claim 원문 바이트를 HMAC-SHA256으로 서명해 두 Gateway claim 헤더를 전달한다.
- [ ] Gateway와 MCP 컨테이너가 같은 비공개 네트워크에 있으며 MCP 포트는 외부에 publish하지 않는다.
- [ ] `/healthz`가 200일 때만 라우팅한다.
- [ ] Gateway 로그·추적 데이터에도 문서 원문, 사전 정의 전문, Authorization 토큰, claim 원문을 기록하지 않는다.
