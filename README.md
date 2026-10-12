# 한국어 표준어 사전 MCP 서버

분할 XLS 원본을 배포 전 SQLite로 변환하고, 표준어 사전 근거를 MCP 도구로 제공한다.

## 개발

```bash
uv sync --all-groups --extra build
uv run --extra build build-korean-dictionary --version 2026.10
uv run pytest
```

빌드 산출물 `data/releases/<version>/korean_standard_dictionary.sqlite3`만 운영 컨테이너의 `/app/data/korean_standard_dictionary.sqlite3`에 읽기 전용으로 마운트한다. Gateway claim 서명 비밀은 `KODICT_GATEWAY_CLAIM_SECRET`으로 설정한다.
