# Codex 종합 점검 지시서 — DOM Inspector Easy v3 / Fastmarkets Collector v3.7

작성: 2026-10-20 KST
상태: 점검 요청, 실환경 미검증
우선순위: P0 실행·보안·데이터보존 / P1 수집 정확도·연결 / P2 UX·성능

## 0. 범위와 절대 원칙

- 이 저장소 urangsu/mia의 실제 소스는 업무용 Fastmarkets Collector **v3.7**이다. Windows에서 실패한 **MIA_DOM_Inspector_Easy_v3**는 별도 독립 GUI 도구다. 두 코드를 같은 것으로 보거나 DOM Inspector를 Collector v3.7로 덮어쓰지 말 것.
- 확인 시점에 DOM Inspector Easy v3 소스는 저장소에서 발견되지 않았다. 로컬 Windows 위치는 %USERPROFILE%\Downloads\MIA_DOM_Inspector_Easy_v3 이다. Codex의 클라우드 체크아웃에서 이 Windows 로컬 파일을 읽을 수 있다고 가정하지 않는다. 실제 원본 ZIP/소스가 없으면 Inspector 내부 정적 감사·수정은 BLOCKED: SOURCE_NOT_AVAILABLE로 표기하고 Collector 감사는 진행한다.
- 먼저 AGENTS.md, README.md, README_V37.md, CHANGELOG_V37.md, VALIDATION_V37.md, HANDOFF_V37.md, docs/CODEX_WORK_ORDER.md를 통독한다. 기존 docs/CODEX_WORK_ORDER.md의 Collector 작업 계약과 보호 규칙이 우선이다.
- 재현 없는 문제는 확정 버그로 쓰지 않는다. 모든 항목을 OBSERVED(실제 오류)/HISTORICAL(과거 기록)/RISK(검토 필요)/BLOCKED(소스·현장 부족)/PASS(직접 테스트)로 분류한다.
- 업무용 MIA DB/Excel/ECM·SU OCR·Chrome 9222·관리자 Edge 9337은 검사 도구 패치로 건드리지 않는다. Collector Chrome 9444는 실제 소유 PID/프로필/CDP를 검증하고 Collector가 동작 중일 때 Inspector가 접근하지 않게 한다.
- 인증/DRM/SSO/회사 브라우저 정책 우회, 쿠키/프로필 복제, 관리자 권한 상승, 강제 브라우저 종료, 유료 Fastmarkets API 도입은 금지한다.
- 공개 GitHub 저장소에 실제 회사 DOM/가격/DB/Excel/로그/비밀번호/토큰/쿠키/개인식별 경로를 커밋하지 않는다. 인수 시험은 승인된 사본과 비밀정보를 제거한 최소 fixture로 진행한다.

## 1. 이미 발생한 문제·기존 기록 및 조치 필요 사항

| ID | 분류 | 관찰된 증상·근거 | Codex가 확인할 사항 |
|---|---|---|---|
| D01 | **OBSERVED** | PowerShell에서 .\.venv-py314\Scripts\python.exe 실행 시 CommandNotFoundException. Python 프로세스 실행 전에 실패 | 가상환경 미생성·다른 이름·중첩 압축·경로·권한을 구분. **이 로그만으로 GUI Python 오류를 단정하지 않음** |
| D02 | **HISTORICAL** | v3 README상 INSTALL.cmd를 처음 1회 실행한 뒤 START.cmd를 실행해야 함 | 실제 설치/시작 두 단계가 사용자에게 불필요하게 어려운지 및 원클릭 실행 가능성 검토 |
| D03 | **UNVERIFIED** | 별도 실행 복구 패치 MIA_FIX_AND_RUN.cmd/.py가 전용 venv·playwright·bs4·Chromium 준비 및 GUI 실행을 시도하도록 제작됨 | 패치의 Python 구문 외 Windows/GUI 실행은 아직 미검증. 원본 INSTALL/START와 중복·충돌·실패로그·재설치 조건을 감사. 패치 ZIP은 현 저장소에 없음 |
| D04 | **HISTORICAL** | 이전 Python 3.14 독립 환경에서 Crawl4AI 설치 뒤 setup/import 실패 기록 | 정확한 traceback 최종 원인을 확인. Crawl4AI는 선택 기능이며 실패해도 Playwright 원본 JSON 보존 |
| D05 | **RISK** | 열린 CDP 브라우저와 일반 로그인 Chrome/Edge의 연결 방식이 다르고 브라우저 버튼 확장 설치가 필요할 수 있음 | CDP 소유권·포트·탭 선택과 확장 정책/권한/다운로드/실패 UX 점검 |
| D06 | **RISK** | 가상화 AG Grid의 화면 밖 행, 가로 숨은 열, pinned row가 DOM에 일부만 존재할 수 있음 | 화면에 없는 값은 성공/0으로 만들지 말 것. 날짜·위젯·단위 식별 및 범위 메타 포함 |
| D07 | **RISK** | 공개 조사 JSON은 Downloads/MIA_Web_Results, 브라우저 확장 버튼 JSON은 기본 Downloads에 저장됨 | 저장 위치/파일명 명확화, JSON 검증, 중복 파일명·원자적 쓰기·실패 시 안내 |
| C01 | **현장 BLOCKED** | Collector Chrome/Driver 9444 실환경 연결 및 재연결 미검증 | Chrome 버전/Driver 호환, 프로필·PID·탭·작업공간 소유 검증, 다른 브라우저 무영향 |
| C02 | **HISTORICAL/BLOCKED** | FMB BM Payable의 42행 날짜 미인식, pinned 날짜·가격 행 매칭 문제 | 실제 최소 DOM으로 row-index/그리드 범위/날짜 상속 정확성 검증 |
| C03 | **현장 BLOCKED** | FMB 코발트 $/lb와 Tonne 위젯 전환 여부 불명확 | 원문 단위/뷰/모드/가격/환산을 분리, 임의 환산 금지 |
| C04 | **HISTORICAL/BLOCKED** | NAVER 홈 DOM은 메뉴 중심이고 실제 지표·시총 순위 DOM 추가 필요 | KOSPI/KOSDAQ/S&P500/NASDAQ/미국10년/한국10년/GOLD/WTI 확정종가, KRX_ALL Top10+005490 검증 |
| C05 | **HISTORICAL/BLOCKED** | ECM에서 링크보다 오른쪽 더블클릭으로 파일 열기 실패, searchValueT 검색·입력/포커스 문제 | 정확한 링크 hit-test, 검색 read-back, Excel FullName+HWND 재검증, 서버 체크인 분리 |
| C06 | **현장 BLOCKED** | SQLite/Excel 누적, 사용자 시트·수식·열·보안 속성, no-op 저장의 Windows 인수 미완료 | 승인된 사본에서 같은 데이터 반복·정정·부분실패·복구·파일 잠금 테스트 |
| C07 | **현장 BLOCKED** | 08:30 KST 예약 실행의 Windows 실제 기동/절전/재시도 미검증 | 로그인 상태/휴장일/놓친 실행/중복 실행, ECM 자동 승인 쓰기 방지 |
| C08 | **RISK** | 기존 202개 전체·79개 v3.7 테스트 통과는 과거 macOS 합성 검증 | 해당 수치 재사용 금지. 재실행/Windows 사이트/COM/ECM 서버 증거 구분 |

## 2. P0: DOM Inspector Easy v3 런처·설치 복구

원본이 제공된 경우 다음 순서로 수행한다.

1. 실제 파일 트리·압축 중첩 확인: INSTALL.cmd, START.cmd, MIA_DOM_쉬운실행.py, browser_button 폴더, README_처음부터.md, 패키지 매니페스트. 이름·한글 인코딩·공백이 있는 경로 검증.
2. Python 3.14 설치와 전용 .venv-py314 존재를 따로 검사한다. 가상환경 없는 상태에서 직접 인터프리터 호출했기 때문에 실패했을 수 있다. Windows CMD, PowerShell, 탐색기 바로가기 세 경로 테스트.
3. Clean Windows 11/Python 3.14에서 신규 설치 → GUI 실행 → 종료 → 2회 실행. 재실행 때 불필요한 패키지 재설치·Chromium 다운로드 없어야 한다.
4. Python 설치 경로가 다른 경우, py launcher가 없는 경우, pip/ensurepip 실패, 백신 격리, 사내 프록시/네트워크 차단, 다운로드 폴더 쓰기 제한, 깨진 기존 venv를 구분한다. 기존 venv를 무조건 삭제하지 않는다.
5. 제공된 복구 ZIP에 든 MIA_FIX_AND_RUN.cmd/.py가 원본을 수정하지 않는지, 기본 Python 경로 이외의 환경에서도 실행되는지, 설치·실패 로그가 과도한 내부 데이터를 남기지 않는지 검토한다.
6. 프로그램 실행 실패/Playwright 설치 실패/Crawl4AI 가공 실패를 구분해서 사용자에게 한국어로 설명한다. Crawl4AI는 필수가 아니며 실패해도 Playwright 핵심 기능을 계속 사용할 수 있어야 한다.
7. 빌드 및 배포 전 requirements 잠금/라이선스/Windows Python 3.14 호환/ZIP 파일 누락/UTF-8 CMD·PY/UI 한글 검증. 회사 정책을 우회하지 않는다.

현장 진단 명령(문서 예시일 뿐 실제 실행했다는 뜻이 아님):

    Get-Location
    Get-ChildItem -Force -Name
    Test-Path ".\MIA_DOM_쉬운실행.py"
    Test-Path ".\.venv-py314\Scripts\python.exe"
    py -3.14 --version
    .\INSTALL.cmd
    .\START.cmd

P0 완료: 깨끗한 Windows/Python 3.14에서 동작하는 단일 실행 경로, 재실행 멱등성, 실패 시 수정 가능한 메시지 및 실제 종료코드·로그를 확보. Linux/macOS 테스트만으로 Windows PASS를 선언하지 말 것.

## 3. P1: Inspector 실제 DOM·확장·사용성 검증

- **공개 사이트 조사:** Westmetall Ni/Cu, 서울외국환중개 SMBS, NAVER, 사용자 URL의 Playwright 렌더·상태코드/리디렉션·캡처·JSON 출력.
- **기존 CDP 로그인 브라우저 조사:** 기존 9222/9337은 접근하지 않는다. FMB 9444는 Collector 비작동/소유 검증 조건에서만 읽기 전용 접근. 자동 새로고침·탭 이동·스크롤·클릭·프로필 복사 금지.
- **일반 Chrome/Edge:** 디버그 비활성 일반 브라우저에 CDP 자동 연결된다고 주장하지 않는다. 회사 정책상 허용된 browser_button 확장만 수동 사용. manifest/activeTab/다운로드 권한·서비스워커·CSP·차단 시 UX 검증. v2의 9555/9556 포트를 근거 없이 v3에 이식하지 않는다.
- **DOM 정합성:** 화면 표시 범위, AG Grid pinned row, 가상 리스트/가로 열, iframes/Shadow DOM, 위젯 식별자, FMB 날짜/종목/가격/단위/통화/뷰, 수집 시각·사이트 URL·오류 상태를 검증.
- **민감정보:** INPUT/TEXTAREA/contenteditable의 사용자 입력, password/쿠키/토큰/세션/숨은 API 응답을 캡처하지 않는지 테스트한다. 로그인된 일반 페이지의 **표시 본문에도 기밀이 있을 수 있으므로** 외부 공개 금지.
- **파일:** 파일명 규칙 fmb_visible_dom_타임스탬프.json, probe_westmetall-ni/cu, probe_smbs, probe_naver 등과 위치·충돌 방지·UTF-8·JSON schema·원자 저장·쓰기 실패 처리 검증.
- **GUI:** 빈 데이터/부분 데이터/성공, 긴 렌더링, 버튼 중복 클릭, 취소/창닫기, UI 메인 스레드 정지 및 즉시 사용자 피드백. 값 없이 '완료'로 표시하는 오류 제거.
- **Crawl4AI:** 선택적으로 로컬 Markdown 부가 출력. import/setup 오류가 생겨도 원본 DOM JSON은 유지.

출력은 검사 도구의 증거 자료이지 Collector DB에 자동 쓰기할 권한이 아니다. 업무용 수집 데이터 반영은 별도의 검증된 Collector 파이프라인에서 한다.

## 4. P0/P1: Collector v3.7 전체 회귀와 실제 연계 문제

상세 구현 위치/계약은 docs/CODEX_WORK_ORDER.md를 우선 적용한다.

- 최신 진입점 FastmarketsCollector_v3_7.py, Selenium 실제 코어 FastmarketsCollector_v3_4.py, pipeline_v37.py 등의 현재 함수·테스트를 먼저 읽는다.
- Chrome 9444 소유 PID/프로필/CDP, 불필요한 로그인/페이지 재로딩 제거, 작업공간 고정, 중간 세션 교체 감지, Chrome/Driver 호환성.
- FMB 전체 금속·탄산리튬·코발트·망간·Black Mass Payable inventory와 실제 화면/허용된 공식 CSV 비교. 원문 $/lb vs Tonne 및 환율 단위 충돌 시 가격 반영 보류.
- SQLite 원본 DB를 계속 누적하고 동일한 누적 Excel을 갱신. '일별시세' 시트가 없으면 생성: 1행 짧은 이름, 2행 FMB/SMBS 출처, A열 고시일, B열 이후 금속 및 USD/CNH/JPY(100)/EUR 각각 독립 열, 3행부터 날짜별 수치. 기존 사용자 시트/열/수식과 호환성 확인.
- 동일 시세 재실행은 불필요한 revision/COM Save 없음, DB 불변성/백업/마이그레이션, 가격 원문·Low/High/Mid 구분. 휴일에 고시가 없으면 없는 상태로 표시.
- NAVER 지표·KRX_ALL Top10+005490은 최근 두 거래일의 확정 종가·시장일·출처를 원문과 비교. 현재가·등락값으로 과거 종가 역산하지 않고 이력 부족은 missing_history.
- ECM 기존 일반 Edge의 searchValueT 포커스/read-back, 파일 링크 정확 클릭(hit-test), 같은 이름 로컬 사본 오선택 차단, Excel FullName+HWND, Excel Save와 ECM 서버 체크인의 차이를 사용자에게 명확하게 표시.
- 08:30 Windows 예약 실제 기동, 놓친 실행/중복/SSO 만료, 편집 가능한 PPTX·HTML/Excel 동일 스냅샷, 보고서 기간 필터가 누적 원본을 절대 축소하지 않도록 한다.
- 실제 Windows 워밍 실행 최소 10회: 총시간, 수집/DB/COM/ECM/보고서 단계별 평균·P95·최악·실패율 측정. 과거 Mac 합성 벤치마크를 실제 개선 수치로 주장하지 않는다.

기본 회귀는 저장소의 README/AGENTS 지침에 따라:

    bash scripts/codex_setup.sh
    bash scripts/codex_check.sh
    python -m unittest discover -s . -p "test*.py" -v

운영 데이터/원본 Excel/ECM에 시험 쓰기를 하지 않는다. 인수 시험은 회사 정책상 승인된 테스트 복사본에서 진행한다.

## 5. 검증 매트릭스

| 범위 | 합격 기준 | 증거 수준 |
|---|---|---|
| 정적/의존성 | PY/JS/CMD·manifest·파일 배포 누락 없음 | 소스·명령·exit code |
| Clean Windows Python 3.14 | 설치·첫 실행·재실행·차단·한글 경로 | 실제 Windows 스크린/로그 |
| 공개 사이트 | DOM/JSON 원문 정확도·누락 표시 | 현장 페이지와 비교 |
| 로그인 브라우저 | 정확한 탭·CDP 소유 검증·비침습 | 세션 변경 없음 |
| 확장 버튼 | 브라우저 정책·권한·다운로드 동작 | 허용된 현장 수동 테스트 |
| FMB 전체 종목 | 원본 시세/단위/날짜/누락 0 또는 누락 사유 | 검열된 실제 DOM |
| SQLite/Excel | 누적 정확성, 수식·타 시트 보존, no-op | 승인된 사본 diff |
| NAVER | 확정 두 종가, KRX_ALL 및 원문 날짜·단위 | 실제 페이지 근거 |
| ECM | 파일 바인딩 정확성, Save와 서버 체크인 별도 | 사내 실제 서버 확인 |
| 예약/성능 | Windows 08:30, 실패 복구, 10회 성능 | 실제 PC 결과 |

**합격 표시 구분:** 정적 PASS / 합성 fixture PASS / 공개 사이트 PASS / 회사 Windows PASS / ECM 서버 PASS. 하나를 나머지 증거로 대체하지 않는다.

## 6. Codex 산출물

1. AUDIT_FINDINGS.md: 이 문서 D01~D07, C01~C08의 재현 여부, 증거, 실제 파일·함수·라인, 원인, 심각도, 해결책, 테스트, 보류 이유.
2. 확인된 결함만 격리된 브랜치에서 작은 커밋으로 수정. 실패 테스트 작성 → 실패 확인 → 수정 → 타깃/전체 회귀. 기존 main·다른 작업 중 브랜치·운영 데이터를 덮어쓰지 않는다.
3. TEST_REPORT.md: OS, Python, 명령, exit code, 테스트 통과/실패, 성능 측정, 실환경/모의 근거 분리.
4. Inspector 원본 파일이 제공되면 설치/시작/복구 패치를 비교하여 일관된 최종 실행 경로와 Windows 배포 ZIP·README를 만든다. 원본이 없으면 허구의 소스·검증 결과를 만들지 않는다.
5. 기밀 없는 최소 샘플만 요청: Inspector 원본 ZIP, 설치 실패 로그(검열본), BM 최소 DOM, 승인된 Excel/ECM 테스트 절차.
6. 최종 보고는 **확인된 문제 → 수정한 파일과 이유 → 실제 실행한 검증 → 현장 미검증 → 다음 최소 조치** 순서. 상용 완료 판정은 실환경 증거가 있는 범위에서만 한다.

**즉시 실행 지시:** 상기 선행 문서와 현재 소스를 읽고 기준선을 직접 재실행한다. D01의 설치 경로 실패를 가장 먼저 재현 가능한 항목으로 분류하되, Inspector 원본 부재 시 BLOCKED로 남긴다. 다음으로 Collector의 실제 확인 가능한 P0를 진행하고, 필요한 최소 파일만 요청한다.
