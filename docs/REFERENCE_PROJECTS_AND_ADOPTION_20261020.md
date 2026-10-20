# MIA 실전 자동화 레퍼런스 조사 및 적용 기준 (2026-10-20)

## 목적 및 범위
MIA는 **정상 권한으로 열린 Fastmarkets Chrome 9444 화면**에서 동적 AG Grid 가격을 수집하고,
SMBS/Westmetall/NAVER 공시 데이터를 날짜·출처·단위로 검증하여 SQLite에 적재한다.
Windows Excel COM으로 DRM이 적용될 수 있는 회사 통합문서/ECM 문서를 편집하고,
동일 DB 스냅샷을 기준으로 Excel·HTML·PPTX 보고서를 만든다.

**Fastmarkets 유료 Physical Prices API, 인증/DRM 우회, 브라우저 Stealth/탐지우회, 외부 비공개 종목 수집 대행은 대안에서 제외한다.**

## 확인한 저장소 (직접 살펴볼 링크)

| 프로젝트 | 링크 | 유용한 핵심 원칙 | MIA 적용 방침 |
|---|---|---|---|
| SeleniumBase | https://github.com/seleniumbase/seleniumbase | 페이지 상태·요소 확인, 명시적 대기 및 로그 | 기존 Selenium 유지. 로딩 완료는 고정 sleep 대신 '위젯 표출+날짜 셀+필수 col-id' 만족을 확인. Stealth 모드는 사용하지 않음 |
| Robocorp RPA Framework | https://github.com/robocorp/rpaframework | Browser/Excel.Application/FileSystem 단위로 독립 작업 | 이미 존재하는 `pipeline_v37.stage`를 실패 격리/재시도 단위로 유지. 새 프레임워크 전체 도입은 보류 |
| Excel Automation with Python | https://github.com/trenton3983/Excel_Automation_with_Python | 실제 Windows Excel COM으로 기존 수식·서식 보존 | `excel_secure.py` 및 `ecm_excel_sync.py`의 검증한 부분 셀 변경을 유지; 전체 Clear, 보안 해제, 임의 SaveAs 불허 |
| pywinauto | https://github.com/pywinauto/pywinauto | UIA 계층에서 대상 HWND·정확한 컨트롤/이름 식별 | 일반 Edge ECM 링크 식별에만 UIA. 통합문서 셀 수정은 UIA/좌표가 아닌 Excel COM |
| VCR.py | https://github.com/kevin1024/vcrpy | 기록한 외부 HTTP 응답을 오프라인에서 재현 가능한 테스트로 사용 | 공개 Westmetall/SMBS에만 *비식별* 최소 HTML fixture 또는 요청 기록. Fastmarkets 로그인·쿠키·유료 콘텐츠의 HTTP 기록/외부 커밋 금지 |
| pytest-recording | https://github.com/kiwicom/pytest-recording | fixture 재생과 네트워크 차단 테스트 | 표 구조 변경을 빠르게 감지할 테스트 패턴만 도입 검토. 별도 설치는 필수가 아님 |
| python-pptx | https://github.com/scanny/python-pptx | 이미지가 아니라 수정 가능한 PowerPoint 표 | 기존 `report_exports.py`처럼 버전별 동일 `ReportContext` 데이터를 native PPTX table로 출력 |
| Pandera | https://github.com/unionai-oss/pandera | 컬럼/타입/고유성/결측 데이터 스키마 검증 | 별도 대형 의존성 없이 먼저 Python/SQLite 검증: 날짜, 고시 source, 단위, 수정 이력, 필수 series coverage 체크 |

관련 기술의 공식 기준:
- AG Grid DOM 가상화: https://www.ag-grid.com/javascript-data-grid/dom-virtualisation/ (화면 밖 행·열 DOM 삭제. 보이는 범위만 크롤링하고 '완전 수집'으로 오판 금지)
- Selenium explicit waits: https://www.selenium.dev/documentation/webdriver/waits/ (implicit + explicit 섞지 않기)

## 코드에 바로 적용/검증할 항목

### P0 — 수집 신뢰성
1. `FastmarketsCollector_v3_4.py`에서 **데이터 렌더링 readiness**는 화면 URL이나 로딩 스피너만으로 판단하지 않는다. 필수 col-id, 실제 날짜 셀, 숫자 Mid 셀의 동일 행 매핑을 확인한다.
2. AG Grid 수평/수직 이동 후 좌표만 비교하는 대신 **가시 셀 signature / 이전 col-id 집합 / row-index+date**를 비교한다. 값이 움직이지 않으면 불완전 수집 경고. 목표 이동 좌표(`x=...`)를 '횟수'로 해석하지 않는다.
3. **일일 증분 7~31일** 기본, `--days 0`은 수동 이력 수집. 수집 범위를 다 찾지 못하면 부분 완료; 모르는 종목/날짜를 0으로 입력하지 않는다.
4. FMB 코발트 원본 `$/lb`, LC/LiOH 원본 `$/kg`, LME cash `USD/tonne`, payable `%`, 금속 재고 `tonne`은 서로 다른 스키마이다. **원본 단위를 저장하고 파생 보고값에서만 환산**한다.
5. 가격 일부 정정에서 기존 Mid를 새 Low/High와 합치는 일이 없어야 한다. 원자적 관측값과 출처·날짜·보기(view) 식별자가 일치하지 않으면 보류하고 기존 보고 셀만 명시적 비우기.

### P0 — Excel/ECM
1. Excel 대상은 실제 `FullName`, `Application.Hwnd`, 관리 시트와 열 카탈로그로 식별한다. 동일 이름의 무관한 파일에는 쓰지 않는다.
2. 이미 있는 파일은 `A열 고시일`, `1행 항목명`, `2행 출처`와 내부 종목 ID 매핑을 매 실행 읽는다. **사용자 추가 열의 수식·서식·위치 보존**.
3. `Save()` 이후 재열기/재읽기로 변경 셀을 검증한다. **Excel Save ≠ ECM 서버 체크인 성공**.
4. DRM 보호 데이터는 회사 Excel COM과 권한 범위에서만 처리한다. 임시 파일의 일반 XLSX 변환 등 보안 변경을 자동 승인하지 않는다.

### P1 — 테스트와 관측성
1. **실패 화면을 비식별 fixture로 재현**: 텍스트/코드/날짜/숫자/col-id/row-index만 남긴 최소 JSON. 전체 HTML·계정·세션 쿠키·토큰은 수집하지 않는다.
2. 동일 단위, 단위 환산 일치, 환산 충돌, 고시일 없음, Mid 없음, 오래된 버전 DB의 range 불일치, 정정 이력, ECM 재시도·수식 보호를 독립 회귀 테스트로 만든다.
3. 로그에 단계별 소요 시간 및 `received/parsed/valid/persisted/quarantined/exported` 카운터와 식별된 작업공간 ID를 분리한다.
4. 결과가 실패해도 FMB·SMBS·LME·NAVER 각각 **DB 저장 상태**를 보존하고, 자동 ECM은 데이터 품질 조건 미충족 시 멈춘다.

### P2 — 재사용 가능한 업무 출력
1. `report_model.build_context`의 스냅샷 한 번으로 Excel/HTML/PPTX를 생성한다. 서로 다른 시각의 FMB, FX를 강제로 같은 날로 표시하지 않는다.
2. 최근 5일/3개월 평균은 **실제 고시일 관측치**만 사용. 전일 비의 비교대상은 해당 series의 직전 실제 고시일이며 휴일·미고시를 0으로 취급하지 않는다.
3. 수정 가능한 PPTX 표와 복사 가능한 HTML `table`, Excel 보고용 시트를 같은 계산 모듈에서 작성한다.

## 실제 도입 상태와 보류사항

- **이미 MIA에 존재:** Selenium, widget/col-id signature, Chrome 9444 세션 재사용, `pipeline_v37.stage`, SQLite UPSERT 및 감사, COM/ECM 셀 단위 변경, frozen report context, python-pptx, 회귀 테스트.
- **본 조사에서 추가한 테스트:** `test_v38_reference_contracts.py` — AG Grid 가시 날짜/다중 그리드 분리·누락 날짜 오인 금지. 기존 테스트와 중복되는 무조건적인 UI 리팩토링은 수행하지 않음.
- **실환경에서 검증 후 도입:** 명시적 DOM 준비 조건과 구조변경 이후 signature stability, 최소한의 비식별 fixture 채집, 단계별 소요시간 벤치마크.
- **도입하지 않음:** SeleniumBase/Robocorp 전체 프레임워크 마이그레이션, Pandera·Pandas 신규 핵심 의존성, Stealth/CDP 우회, 미인가 네트워크 호출, 유료 Fastmarkets API.

## 라이선스·법적 주의
레퍼런스를 보고 새로 구현하는 것과 다른 저장소의 소스/파일을 복사하는 것은 다르다.
위 표에 있는 코드 파일을 통째로 가져오거나 의존성으로 추가할 경우 **해당 커밋/버전의 라이선스와 회사 보안 정책을 먼저 확인**한다.
Westmetall 등 공개 웹페이지라도 이용약관·적정 호출 간격을 준수하고, 유료 Fastmarkets 콘텐츠나 회사 로그는 공개 리포지터리에 업로드하지 않는다.

## 회사 PC 인수 검증 기준
- 실제 BM `MB-BMS-0001/0002/0003/0010/0011/0012` 날짜·col-id·Mid 누락 여부를 작업공간 원문과 대조
- 2026-10-19 FMB Co 22.50 USD/lb → 49,604.01 USD/tonne 확인
- 이전/수정된 종목 가격이 월평균·ECM에서 같이 검증되는지 확인
- 원본 Excel DRM·추가 수기 열·수식·서식 보존 및 Excel Save/ECM 서버 반영 개별 점검
- 9222 Chrome/9337 Edge 및 일반 Edge의 기존 세션이 바뀌지 않는지 점검

**이 문서의 외부 패턴 권고는 구현/검증 여부와 구분한다. 회사 실사이트 수집 및 ECM 반영 성공을 주장하지 않는다.**
