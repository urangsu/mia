# MIA v3.8 개발 변경기록 — FMB 단위·LME·5일 시세 보고

**작성일:** 2026-10-20  
**대상:** `urangsu/mia`의 v3.7 `main`을 기반으로 한 별도 개발 브랜치  
**상태:** 소스 반영·오프라인 회귀 검증 중. 회사 Windows/보안 Excel/FMB/ECM 실사용 인수검증 미완료.

## 1. 왜 수정했는가

### 1-1. 코발트 가격의 단위가 맞지 않았음

Fastmarkets `MB-CO-0005`에는 같은 종목 코드와 같은 `$/lb` Description을 가진 두 위젯이 존재한다.

- 원본 위젯: 2026-10-19 **22.50 USD/lb**
- 오른쪽 `Tonne` 표시 변환 위젯: **49,604.01 USD/tonne**
- 둘의 `MB-CO-0005` 및 원문 Description은 동일함. Description만으로 환산 여부를 판단하면 중복·가격 충돌 또는 2,204배 오류가 발생할 수 있음.

**수정:** 원본 SQLite 가격과 RawData는 절대 변경하지 않는다. `smbs_rates.prepare_excel_series()`에서 보고용 값을 표준화한다.

1. 원본으로 검증한 `$/lb` 숫자에 `2,204.62262185`를 곱하고 보고용으로 소수점 두 자리까지 반올림한다.
2. 동일 고시일에 별도로 표시된 `Tonne` 위젯 숫자가 있다면 원본 기반 환산값과 **0.02 USD/tonne 이내**로 검산한다.
3. 값이 일치하면 하나의 시리즈로 집계한다. 불일치하면 해당 날짜의 가격을 **반영 보류**하고 경고를 남긴다.
4. 환산 위젯 값만 존재하여 원본 `$/lb`를 검증할 수 없으면 해당 날짜를 반영 보류한다. 이 선택은 수집 누락보다 **잘못된 금액의 자동 보고 방지**를 우선한다.
5. 보고표·가격열설정에는 **원본 단위와 보고용 단위**를 구분해 설명한다.

**동일 규칙:** Fastmarkets `MB-LI-0029`(LC), `MB-LI-0033`(LiOH)의 원본 `$/kg`는 보고용 `USD/tonne`으로 **×1,000** 변환한다. 원본 DB·RawData의 단위/금액은 보존한다.

> 예: Co 2026-10-19 22.50 USD/lb → 49,604.01 USD/tonne. Co 2026-10-16 22.93 USD/lb → 50,552.00 USD/tonne.
> BM Payable의 %는 금액/tonne로 변환하지 않는다. MB-BMS-0012의 금액은 원본 `$/tonne` 그대로 사용한다.

### 1-2. LME Ni/Cu와 재고가 누적 원본에 없었음

**수정:** `westmetall_lme.py`를 추가했다.

- **출처:** Westmetall의 공개 HTML 표. 별도 유료 Fastmarkets API를 사용하지 않는다.
- **조회:** `LME_Ni_cash`, `LME_Cu_cash` 표에서 날짜가 명시된 행만 수집한다.
- **수집항목:** `Cash-Settlement USD/tonne`, `3-month USD/tonne`, `LME stock tonne` (Ni/Cu 각각).
- **DB:** `lme_quotes`에 `(source,metal,price_date)` 고유 키로 누적한다. 동일값 재실행은 무변경, 공식 수정 숫자는 `lme_revision_history`에 변경 전/후 값을 기록한다.
- **검증:** 지표·열 제목, 원문 고시일, 숫자 형식, 양수, 당일 이후 미래 날짜 여부를 검증한다. 불명확한 표·중복 충돌은 추정 저장하지 않는다.
- **장애 격리:** 기존 FMB·SMBS·NAVER 작업을 롤백하지 않는 별도 수집 단계다. 회사 네트워크에서 Westmetall 접근 제한 시 경고와 실패 상태를 남긴다.
- **새 Excel 출력:** `LME_원본`에 원자료; `일별시세`/`일별요약`/`월별시세`/`월별건수` 오른쪽에 `LME Ni`, `LME Cu`, `LME Ni(3M)`, `LME Cu(3M)`, `LME Ni재고`, `LME Cu재고`를 추가한다. 두 번째 행 출처는 `WESTMETALL`.
- 기존 사용자 열은 날짜/시리즈 키를 통한 Excel COM 증분 갱신 방식을 유지한다. FMB·SMBS 열 위치는 고정하지 않는다.

### 1-3. 보고서에 최근 5일·월평균 및 자동 문구가 없었음

**수정:** `lme_reporting.py` 및 `report_model.py`를 변경했다.

- 새 보고 시트 `보고용_최근5일`: 검증된 시세가 존재하는 최신 5고시일, 직전 **실제 고시일**과의 차이·증감률.
- 새 보고 시트 `보고용_3개월평균`: 최근 월별 실제 관측값의 산술평균. 휴장일은 0으로 채우지 않는다.
- 새 보고 시트 `보고용_문구`: FMB LC/LiOH/Co, LME Ni/Cu, 원료 MB-BMS-0012, SMBS USD에 대해 기준일과 전일대비를 이용한 **자동 한 줄 문구**.
- 기존 HTML 및 편집 가능한 PPTX는 `ReportContext`의 동일 불변 스냅샷에서 이 신규 표를 함께 출력한다.
- 원본에 없는 SMM LC/LH/Ni/Co는 **임의의 값·열을 만들지 않는다**. 검증 가능한 별도 수집기가 연결된 이후 확장한다.
- 가격과 재고를 혼동하지 않으며 LME 재고는 **tonne**, Cash/3개월물은 **USD/tonne**로 분리한다.
- 보고서의 `FMB Co` 단위도 `USD/tonne`으로 표시한다.

### 1-4. 첫 SSO 로그인에 8초만 기다려 실패할 수 있었음

**수정:** `FastmarketsCollector_v3_4.py`의 수집 시작 로직에서 `open_workspace(...,wait_seconds=8)` 고정을 제거했다. 로그인된 **Chrome 9444 세션이 있으면 그대로 즉시 재사용**하고, 신규 로그인만 기본 30초(설정값 8~90초 제한)를 기다린다. **로그인·DRM·구독 제한 우회가 아니다.**

### 1-5. GUI 수집 항목 선택이 부족했음

**수정:** `gui_v37.py` 고급 설정에 **Westmetall LME 수집** 체크박스를 추가해 `lme_enabled` 값을 저장한다. 완료 화면에 LME 수집 건수를 표시한다. 기존 FMB·환율·ECM 버튼 및 환경설정은 삭제하지 않는다.

## 2. 실제 변경된 소스

| 파일 | 변경 | 이유 |
|---|---|---|
| `smbs_rates.py` | FMB Co/Li 환산, 변환 위젯 검산 및 격리, LME 출처 인식 | 중복·단위 오류 방지 |
| `series_mapping.py` | 가격열설정에 원본/보고 단위 | 숫자 추적성 보장 |
| `westmetall_lme.py` (신규) | 공개 HTML 날짜별 수집, DB/정정이력 | LME 가격·재고 누적 |
| `pipeline_v37.py` | 독립 `lme` stage | 실패 격리·같은 실행에서 수집 |
| `lme_reporting.py` (신규) | LME 열 추가·5고시일·3개월평균·문구 | 표 보고 자동화 |
| `report_model.py` | DB/원본/집계/HTML·PPTX 공통 모델 확장 | 한 출처의 일관된 수치 |
| `excel_secure.py` | 신규 프로그램 소유 시트 허용 | DRM 환경에서 COM 출력 |
| `ecm_excel_sync.py` | `LME|` 시리즈 출처 표시 | ECM 열 추적 시 잘못된 FMB 분류 방지 |
| `gui_v37.py` | LME 설정 복원 | 사용자 선택·진단 |
| `FastmarketsCollector_v3_4.py` | SSO 대기시간 개선 | 로딩 지연 오류 감소 |
| `test_v38_lme_report.py` (신규) | 변환/파서/DB 중복·정정/보고표 테스트 | 회귀 방지 |
| `.github/workflows/market-regression.yml` (신규) | PR 단위 회귀 테스트 | 실제 GitHub에서 코드 검사 |

## 3. 사용 절차

1. 기존 회사 DB와 `fastmarkets_prices.xlsx`를 복사해 안전한 위치에 백업.
2. 개발 브랜치의 v3.7 진입점 `FastmarketsCollector_v3_7.py` 사용; 사내 Excel에는 Excel COM과 현재 회사 보안정책 그대로 적용.
3. GUI 고급 설정에서 **Westmetall LME** 선택 후 FMB·SMBS와 함께 실행.
4. `일별요약` 1행 간략 품목, 2행 FMB/SMBS/WESTMETALL 출처, 3행부터 날짜별 숫자 확인.
5. 새 `보고용_최근5일`, `보고용_3개월평균`, `보고용_문구` 검토. 숫자 없는 날짜를 임의로 채우지 않는다.
6. ECM에 이미 올린 파일에 반영할 때는 **변경 대상 셀 미리보기 후 명시적 승인**. 서버 체크인 여부는 별도 확인.

```powershell
py -u .\FastmarketsCollector_v3_7.py --export-only
py -u .\FastmarketsCollector_v3_7.py --once
py -m unittest discover -s . -p "test_v38_*.py" -v
py -m unittest discover -s . -p "test_v37_*.py" -v
```

## 4. 검증·한계

- **원본 자료:** 기존 Fastmarkets 제공 화면에 Co 22.50($/lb) ↔ 49,604.01($/tonne)이 같이 표시되는 실제 사례, Westmetall 가격·재고 표.
- **코드 검증:** 전용 정적/오프라인 회귀 테스트 추가. 결과는 GitHub Actions의 실행 상태로 확인할 것.
- **미검증:** 실제 회사 Chrome 9444/SSO/FMB 가상 AG Grid, 네트워크가 Westmetall HTML 수집을 허용하는지, Windows COM/DRM 저장, ECM 저장/체크인.
- **외부 이용조건:** Westmetall 공개 웹페이지 이용조건·접속 제한을 준수하고 과도한 요청·보호회피를 하지 않는다.
- **기능 보류:** SMM 시세 자동 수집과 매일 Excel 입력 없는 완전 자동 ECM 서버 체크인은 미구현. 기업 보안정책 우회 기능·Fastmarkets 유료 API 호출은 없음.
- **운영 전 필수:** 2026-10-16, 2026-10-19 코발트 환산/원본 일치, LME Cash·3M·Stock의 실제 고시일 일치, 수동 삽입 열/수식 보존 확인.

## 5. 운영 데이터 보존 정책

`fastmarkets_prices_v3.sqlite3`는 원본 DB로 유지한다. 수집 단위($/lb, $/kg, % Payable, USD/tonne 등)를 임의 변경하거나 이전 이력을 일괄 덮어쓰지 않는다. 보고서는 파생값이며, 정정은 별도 기록한다. 보안 엑셀은 `endp.py`에서 사용한 정상 Excel COM 경로로 처리하고 보안 래핑을 해제하지 않는다.

