# 기능 우선 개선 실행 계획

Goal: 기존 수집·누적·ECM 보호 계약을 유지하며 설정·결과·복구를 실제로 연결하고 새 데스크톱 UI를 검증한다. 배포/원격 게시를 완료 조건으로 삼지 않는다.

Architecture: 기존 코어와 hotfix1을 유지하고 설정 왕복 보존/작업별 검증을 분리한다. 새 Qt Widgets GUI는 Controller를 통해서만 작업을 수행한다. 모든 외부 작업은 단일 worker로 직렬화하고 Qt signal로 UI를 갱신한다. 자료 없음/부분 실패/실패/승인 대기를 구분한다. 회사 실환경은 별도 인수다.

Tech stack: 기존 Python/Selenium/SQLite/Excel COM/UIA + PySide6-Essentials(Qt Widgets). WebEngine/웹 서버/새 인증 프로필은 추가하지 않는다.

## 작업

- [ ] 1. hotfix1의 실패 회귀 13개를 현재 브랜치에서 실행해 기준 결함 확인. 검증된 13개 파일을 이식하고 215/92 회귀 확인.
- [ ] 2. 가격 부분 정정 시 새 범위와 이전 Mid 혼합을 재현. 원본 관측을 보존하고 일관성 없는 결합 값을 보고하지 않도록 방어. 기존 부분 필드 보존과 감사 이력 테스트 유지.
- [ ] 3. app_settings.py에서 확장 설정 보존, 비밀정보 저장 금지, 작업별 검증. core config wrapper와 CLI의 명시 인자 덮어쓰기 연결. 실제 임시 파일 왕복 회귀.
- [ ] 4. desktop_controller.py에서 저장/로그인/진단/수집/출력/보고서/ECM 승인/예약 조회·등록·해제/상태 모델 구현. 입력한 계정의 일회성 로그인 지원. source_enabled는 실제 파이프라인 단계와 연결. DB 출력은 ECM 설정·로그인과 독립.
- [ ] 5. desktop_ui.py + desktop_theme.py + desktop_tables.py: 대시보드·자료/보고서·ECM·실행 기록·설정. 구조적 빈 상태, 실제 기준일·단위·출처, 정렬·필터, 스크롤 설정, 경로 선택, 저장 상태, 취소·오류·재시도. 계층 배경/24px 제목/16px 본문/8px 컨트롤/숫자 정렬. 샘플 가격은 실자료처럼 넣지 않음.
- [ ] 6. 새 UI 기능 테스트, 합성 화면 렌더 점검, 전체 회귀. 새 진입점은 기능 검증 후에만 연결. 기존 Tk 진입 경로는 명시적인 legacy 옵션으로 보존.
- [ ] 7. 독립 사양 검토 후 코드 품질 검토. 발견 사항 수정 후 재검증. Windows/회사 로그인/실제 NAVER 과거 종가/DRM Excel/ECM 서버 미검증을 결과에 명시.

## 검증 기준

2026-10-20 실행 상태: 위 1–7의 로컬 구현·회귀·독립 검토는 수행했습니다. 전체 회귀 265개, 엄격 검사 92개, Qt 검사 24개가 통과했습니다(서로 중복되는 검사이므로 합산하지 않음). 체크리스트는 전체 업무 인수 전까지 닫지 않습니다. 실제 NAVER 과거 종가 어댑터와 회사 Windows/Fastmarkets/Excel/ECM/예약 기동은 미완료 또는 미검증이며, 상세 증거와 잔여 항목은 FUNCTION_FIRST_TEST_REPORT.md를 따릅니다.

각 변경은 실패 재현 → 최소 수정 → 회귀. Qt 테스트는 임시 설정·모의 외부 어댑터를 사용하며 실제 브라우저/예약/ECM을 실행하지 않는다. 기능 버튼은 실제 Controller 메서드와 연결하고, 미지원 현장 작업은 명확한 오류를 반환한다. GUI 색상 테스트만으로 완료하지 않는다. 사용자 DB/Excel을 자동 추정 수정하지 않는다.

## 파일 소유권

주 에이전트: 기존 코어/hotfix, app_settings.py, desktop_controller.py, CLI/pipeline, 데이터/설정/서비스 테스트, 통합·검증.
UI 구현 에이전트: desktop_ui.py, desktop_theme.py, desktop_tables.py, test_desktop_ui.py만. 공통 파일 변경은 주 에이전트에 요청. Git 인덱스/커밋은 주 에이전트가 관리.
