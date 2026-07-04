# SkinHarmony MCP Server

> "화해가 아니라, 카톡에서 사기 직전에 물어보는 성분 친구."

화장품 전성분을 붙여넣으면 식약처 공공데이터 기반으로 성분별 안전 신호등(🟢🟡🔴)을 즉시 리포트하고,
제품 간 성분 궁합(레이어링 충돌)을 검사하며, 사용자의 회피/선호 성분을 기억하는 MCP 서버.

## 툴 구성 (4종)

| 툴 | 역할 | 비고 |
|---|---|---|
| `analyze_ingredients` | 전성분 → 신호등 안전 리포트 | `demo=true` 원클릭 시연 지원 |
| `check_compatibility` | 2개+ 제품 궁합·충돌 → Day/Night 루틴 | ★대표 히어로 기능 |
| `remember_ingredient` | 회피/선호 성분 개인 기억(닉네임 기반) | 멱등 upsert |
| `search_cosmetic_info` | 성분 표준 사전 조회(규제·한도) | 미확인 시 정직 안내 |

## 정확성 설계

- **정규화 4단계**: 정확 매칭(표준명·이명 사전) → 퍼지 매칭(difflib ≥0.87) → 부분 매칭(액티브 카테고리 한정) → **미확인은 추정 없이 분리 표기**
- **룰셋 커버리지**: 충돌 룰은 성분쌍이 아닌 **카테고리쌍**(RETINOID×AHA 등 15룰 + 시너지 4룰) — 사전에 성분 추가 시 커버리지 자동 확장
- **데이터 출처**: 식약처 사용제한 원료·규제정보·기능성화장품 고시 기반 자체 사전(민간 크롤링 없음), 룰마다 출처 표기
- **응답 규격**: TextContent 마크다운, 20k 제한(24k 정책 여유), 🟢 성분은 요약 처리

## 로컬 실행

```bash
pip install -r requirements.txt
python server.py            # http://localhost:8000/mcp (Streamable HTTP, stateless)
```

MCP Inspector 점검:
```bash
npx @modelcontextprotocol/inspector
# Transport: Streamable HTTP / URL: http://localhost:8000/mcp
```

## 배포 (PlayMCP in KC)

- Git 소스 빌드: 이 저장소 루트에 Dockerfile 포함 → 그대로 등록
- 이미지 등록: `docker build --platform linux/amd64 -t <registry>/skinharmony:latest .` (arm64 불가!)
- 환경변수: `PORT`(기본 8000), `SKINHARMONY_DB`(SQLite 경로, 기본 ./user_prefs.sqlite)

## 테스트

```bash
python test_core.py   # 정규화·판정·궁합 코어 로직 검증 (mcp 설치 불필요)
```
