# HTML 보고서 공개 브리핑

일반 GUI·예약·보고서 실행은 이 기능을 호출하지 않습니다.
아래 옵션을 명시할 때만 브라우저를 열지 않고 저장 DB에서 보고서를 만들며,
USGS의 공식 공개 목록에서 발행물 메타데이터만 조회합니다.

```powershell
py -3 .\MIA_Collector.py --reports-only --public-briefing
```

필요하면 `--data-dir`와 `--report-dir`로 저장 경로를 선택하세요.
USGS 발행물은 보고 종료일 기준 최근 180일, 리튬·니켈·코발트·핵심광물 제목
필터 및 중복 제거 후 최신 5개까지 표시합니다. 제목·발행일·공식 안내 링크만
사용하며, 본문·PDF·댓글은 수집하지 않습니다. 조회 결과가 없으면 목록도
표시하지 않습니다. API 키가 없어도 공개 목록은 동작합니다.

## 나중에 요약을 켤 때

위 옵션에 더해 승인된 Chat Completions 호환 모델의 설정을 실행 세션에
모두 제공해야 합니다. 현재 기본값이나 사전 연결은 없습니다.

| 환경 변수 | 값 |
|---|---|
| `MIA_BRIEFING_ENDPOINT` | 승인된 HTTPS 엔드포인트 전체 URL. 경로는 `/chat/completions`로 끝나야 함 |
| `MIA_BRIEFING_MODEL` | 해당 엔드포인트가 지원하는 모델 ID |
| `MIA_BRIEFING_API_KEY` | 회사 승인 방식으로 실행 세션에 주입한 키 |

이름이 정해진 공개 지수의 확인된 두 종가 기준일과 수치·등락, 공개 SMBS
환율, USGS 제목·발행일만 모델에 보냅니다. Fastmarkets 등 구독 시세, 회사
워크스페이스, 종목별 자료, DB 파일, ECM, 로그, 계정·쿠키는 전송하지 않습니다.
보고서 HTML 자체는 네트워크를 호출하지 않습니다. 설정 미완성, 인증 실패,
시간 초과, 유효하지 않은 응답이면 `오늘의 요약`을 아예 생략합니다.
요약이 생성되더라도 본문 수치에는 영향을 주지 않으며, AI 초안으로 표시합니다.

Horizon에서는 **수집 → 필터·중복 제거 → 선택적 요약 → 출력**만 참고했습니다.
Horizon 설치, GitHub Actions, 메일·웹훅, 뉴스 본문 수집은 넣지 않았습니다.
회사의 네트워크 정책상 공식 목록이나 모델 접속이 허용되지 않으면 우회하지
않고, 옵션 없이 기존 보고서를 사용하세요.

참고: [Horizon](https://github.com/Thysrael/Horizon),
[USGS Publications Warehouse API](https://pubs.usgs.gov/documentation/web_service_documentation).

## 검증 범위

- 2026-11-05, macOS/Python 3.14: 원격 main 기준 전체 오프라인 회귀 475개 통과
  (`QT_QPA_PLATFORM=offscreen python -m unittest discover -s . -p 'test*.py'`).
- 공개 USGS 카탈로그 실조회는 TLS 검증을 유지하고 개발기의 신뢰 CA를
  지정하여 4개 검색 성공, 공식 링크 5개 선택, 모델 설정 없이 요약 0개를 확인했습니다.
- 합성 HTML 브라우저 검증: 1280/320px, 흰 기본 배경, 다크 전환, 키보드
  차트 열기와 전체 페이지 가로 넘침 없음. Oh My Design CLI 2.0.6의
  `check contrast`는 데스크톱/모바일 기본 밝은 화면에서 통과했습니다.
- 모델 응답 형식·데이터 전송 경계는 모의 테스트만 했습니다. 실제 모델,
  회사 Windows/프록시·SSO·ECM은 이번 검증에 포함하지 않았습니다.
