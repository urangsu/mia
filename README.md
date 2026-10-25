# mia · Fastmarkets Collector v3.7

2026-10-25 금속 중심 개선판: [실행·수집 실패·새 TXT 복원 안내](docs/METALS_RECOVERY_GUIDE_20261025.md), [수정/검증/미완료](docs/METALS_RECOVERY_TEST_REPORT_20261025.md), [공식 리서치 링크 계획](docs/METAL_REPORT_LINKS_PLAN_20261025.md). 설치는 `requirements-desktop.txt`를 사용합니다. 기존 main의 10월23일 문서는 설계였으며 이 변경이 일부 P0/P1을 구현합니다. 전체 회사 수집 완료를 뜻하지 않습니다.

현재 개발 브랜치의 기본 화면은 Qt입니다. **[기능 우선 개발판 실행·변경·남은 검증](FUNCTION_FIRST_README.md)**을 먼저 읽으세요. 설치: `py -m pip install -r requirements-desktop.txt`. 기존 Tk 화면은 `--legacy-gui`로 보존합니다. 회사 사이트 수집·보안 Excel·ECM 인수는 미완료이며 배포 승인본이 아닙니다.

금속·환율·시장 확정 종가를 SQLite와 누적 Excel에 보관하고 HTML·편집 가능한 PPTX 보고서를 만드는 Windows 업무 도구입니다. 기본 예약 시각은 **08:30 KST**입니다.

2026-10-22: [FinanceDataReader·거래일 캘린더 운영 안내](docs/FDR_CALENDARS_GUIDE.md)를 추가했습니다. 공개 종가 수집은 브라우저 없이 실행하며 기존 Fastmarkets/ECM 경로는 유지합니다. [신규 검증 결과와 미지원 범위](docs/FDR_CALENDARS_TEST_REPORT_20261022.md)를 확인하세요. 한국10년·시총 순위 자동 확보까지 완성된 것으로 해석하지 마세요.

현재는 **실환경 인수 전 후보 빌드**입니다. 클라우드에서 통과한 모의 테스트가 회사 Windows·Fastmarkets 구독·NAVER 실DOM·ECM 서버 성공을 의미하지 않습니다.

2026-10-20 hotfix1은 첫 수집의 DB 초기 조회, 충돌 보류값의 Excel 반영·열 매핑 유지, GUI 오류 후 상태 갱신을 수정했습니다. [당시 수정·검증 안내](FIXES_V37_HOTFIX1.md)는 역사 기록입니다. 이후 기능 우선 개발판에서 부분 가격 정정의 Mid 범위 일관성 방어를 추가했습니다. 기존 Excel 사본으로 먼저 확인하세요.

## Codex에서 이어 작업

1. [AGENTS.md](AGENTS.md)를 읽습니다.
2. [후속 작업지시서](docs/CODEX_WORK_ORDER.md)와 [인수 경계](HANDOFF_V37.md)를 읽습니다.
3. 환경 설치는 `bash scripts/codex_setup.sh`, 검증은 `bash scripts/codex_check.sh`를 실행합니다.
4. 결함 재현 → 실패 테스트 → 수정 → 회귀 순으로 P0부터 진행합니다.

이 저장소에는 실제 소스가 루트에 있습니다. ZIP 재첨부가 필요하지 않습니다. 기존 버전명 진입점은 호환용이며 최신 진입점은 `FastmarketsCollector_v3_7.py`입니다. 실제 Selenium 코어는 이름을 유지한 `FastmarketsCollector_v3_4.py`입니다.

## Windows 사용

```text
py -m pip install -r requirements.txt
py FastmarketsCollector_v3_7.py
py FastmarketsCollector_v3_7.py --schedule 08:30
py FastmarketsCollector_v3_7.py --schedule-status
```

[사용법](README_V37.md) · [변경 내역](CHANGELOG_V37.md) · [기존 검증 기록](VALIDATION_V37.md) · [클라우드 환경 설정](docs/CLOUD_SETUP.md)

Chrome **9444**만 Fastmarkets에 사용합니다. **9222/9337에는 간섭하지 않습니다.** ECM은 이미 로그인된 일반 Edge를 사용하며 별도 프로필/쿠키 복사를 하지 않습니다. 예약 실행은 ECM 승인 쓰기를 자동 수행하지 않습니다.

## 데이터와 접근 정보

공개 저장소에는 소스·합성 fixture·문서만 보관합니다. 계정·쿠키·프로필·회사 DB/Excel·실제 수집 로그는 올리지 마세요. 네이버는 두 실제 거래일의 확인된 종가로 비교하며 이력 부족은 `missing_history`로 남깁니다. 뉴스·AI 해설·메일 발송·유료 시세 API는 이번 범위가 아닙니다.

원본 배포 ZIP의 중복 PY/TXT 미러·합성 출력 바이너리·기기별 검증 로그는 저장소에서 제외했습니다. 프로그램 소스와 모든 기존 테스트는 보존했습니다.
