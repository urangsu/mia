# 이어서 작업할 때

2026-10-22: FinanceDataReader 공개 종가와 exchange_calendars를 독립 단계로 연결했습니다. 먼저 [운영 안내](docs/FDR_CALENDARS_GUIDE.md)와 [신규 검증 보고서](docs/FDR_CALENDARS_TEST_REPORT_20261022.md)를 읽으세요. fdr_provider.py는 공개 읽기/원본·정정·보류 이력, market_sessions.py는 기대 거래일, fdr_reporting.py는 두 종가 선택을 담당합니다. 한국 지수·관심종목은 NAVER, 해외는 Yahoo로 구분합니다. NAVER DOM 수집 자체를 고쳤다는 뜻은 아닙니다. KR10Y 미지원과 금/WTI 기대일 누락으로 실제 실행은 partial이었습니다. 회사 Windows·ECM·예약 실기동은 미검증입니다.

현재 기능 우선 개발 브랜치는 FUNCTION_FIRST_README.md와 FUNCTION_FIRST_TEST_REPORT.md를 우선 확인하세요. 최신 UI는 desktop_ui.py, 작업은 desktop_controller.py, 설정은 app_settings.py입니다. 아래 hotfix1 설명은 당시 기록이며 이후 가격 범위가 바뀔 때 이전 Mid의 부적합 상속 방어가 추가됐습니다. NAVER 실DOM/과거 종가 자동 확보와 회사 인수는 여전히 남아 있습니다.

2026-10-20 hotfix1: 첫 FMB 초기 조회, 보류값의 누적 Excel/ECM 반영과 열 키 유지, GUI 오류 복구를 수정했습니다. `FIXES_V37_HOTFIX1.md`와 `test_v37_recovery.py`를 확인하세요. DB 부분 정정 시 이전 Mid/새 범위 혼합 문제는 여전히 별도 P1이며 운영 적용 전 해결해야 합니다. 새 보류셀 시트는 프로그램 관리 영역입니다. 실제 Windows/보안 Excel/ECM 인수는 여전히 필요합니다.

최신 실행 파일은 FastmarketsCollector_v3_7.py. 실제 Selenium 수집 로직은 FastmarketsCollector_v3_4.py에 있습니다. 수정 전 README_V37.md, CHANGELOG_V37.md, VALIDATION_V37.md, 테스트를 읽으세요. 구버전 문서의 통과 수치를 현재 결과로 재사용하지 마세요.

## 남은 실환경 자료

1. 회사 Windows에서 diagnose_windows.py --driver-check 결과. 이 도구는 9444만 확인합니다.
2. BM 실패 위젯 날짜·가격 행과 컨테이너 경계가 포함된 최소 DOM. 계정/쿠키/토큰 전체 페이지는 필요하지 않습니다.
3. DB/Excel 허용된 사본과 사용자 수식·열 배치 샘플. 누락 종목 목록은 실제 전체 작업공간 inventory와 대조해야 합니다.
4. NAVER 8개 지표·KRX_ALL 시총 Top10·005490의 날짜/종가/단위가 포함된 표시 DOM. 특히 전일과 직전 거래일 과거 종가 화면의 실제 구조가 필요합니다. 현재 synthetic DOM 테스트는 실사이트 호환성 보장이 아닙니다.
5. ECM 열기/체크아웃/Excel 저장/체크인의 사내 절차 및 실제 서버 확인 방법.
6. 같은 Windows PC에서 동일 자료 warm 실행 10회 단계별 시간. benchmark_v37의 CPU 시간은 대체 증거가 아닙니다.

## 합격 체크

- 예약 시각에 사용자 로그인 상태에서 실행되어 DB/보고서가 생성되는지 확인.
- 같은 자료 재실행 시 가격 revision 증가·불필요한 Excel Save가 없는지 확인.
- BM 날짜와 전체 필수 금속/Payable 코드의 누락 0을 실제 DOM/공식 CSV로 확인.
- NAVER 두 종가 날짜·값을 원문과 대조. 이력 부족을 성공으로 바꾸지 않음.
- 사용자 수식·열·다른 시트·보안 형식 보존, 같은 파일명의 로컬 사본 ECM 오선택 차단.
- ECM Excel Save와 서버 체크인 결과를 별도로 확인.
- 9222/9337·일반 로그인 Edge·관리자 Edge 프로세스와 탭이 변경되지 않음.

P0/P1 우선입니다. 실제 Windows 증거 전에는 상용 완성/배포 승인으로 표시하지 마세요.
