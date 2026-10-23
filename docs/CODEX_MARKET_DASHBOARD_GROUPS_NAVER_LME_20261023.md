# MIA 시장 데이터 화면·수집 파이프라인 개편 작업지시서 — 2026-10-23

상태: **설계 및 수집 계약 정리 완료 / 코드 구현 및 회사 Windows 실환경 검증 미완료.** 이 문서를 '기능 구현 완료'로 보고하지 말 것.
기준 저장소: urangsu/mia main, PySide6 기본 Qt / SQLite 원본 / Excel 지속 누적.
참조: 사용자가 직접 전달한 2026-10-23 Npay 증권 3종 페이지 DOM (marketindex/metals/CMNI0, KR capitalization, stock/usa), 화면 캡처, 보고 대상 금속 항목 표. 사내 민감 DOM/시세 값은 공개 저장소에 첨부하지 않음.

## 0. 제품 목표 / 사용자 피드백
- 보고서 화면 하단의 **'자료 기준'** 영역은 기본 접힘 상태로 맨 아래에 배치하고, 명시적 '펼치기' 동작 전에는 긴 출처/진단 상세를 보이지 말 것.
- UI에서 `MB-...` 같은 내부 식별코드를 품목명으로 대신 표시하지 말 것. **정확한 정식명칭(등급/화학/지역/시장/조건) → 출처/조건 → 최신 값·단위·고시일**이 우선; 코드/기술 메타데이터는 상세 정보에서 보인다. 설명이 불충분한 코드는 '품목명 확인 필요'로 표시하고 수치를 타 품목에 몰래 매핑하지 말 것.
- 가격과 기간 선택, 커서 위치에 따른 날짜·값 툴팁, 여러 항목의 그룹형 시세표와 차트; Npay 증권의 **정보 밀도, 그룹 분류, 카드 + 표 + 차트** 경험을 참고하되 독자적인 Qt/HTML 구성 사용.
- 대시보드 기본은 '원료·금속 시황' → '환율·금리' → '국내 주식시장' → '미국·글로벌 주식시장' → '보고서 출력' 흐름. 그 안에서 비슷한 자료는 줄줄이 연결되게 묶어 표시. NAVER 실시간 호가와 확정 종가/고시 시세를 혼합하지 않음.

## 1. 메인 품목 그룹과 별도 시리즈키

절대로 '니켈' 1종으로 LME 금속/황산니켈 환산/SMM 과세·비과세/FMB를 합치지 말 것.
모든 열은 series_key (source, product, contract, measure, grade, market, geography, tax, unit, mode, field)로 구별; 누적 DB 기존 symbol·unit·view_key 유지 및 마이그레이션은 백업/검증 아래 후속 작업.

| 순서 | 1차 분류 | 2차 하위 제품/벤치마크 | 필수 시리즈/구별 |
|---|---|---|---|
| 1 | 리튬 | 전지급 탄산리튬 | Fastmarkets Spot CIF; SMM VAT 포함/제외 |
| 2 | 리튬 | GFEX 탄산리튬 선물 | 거래소 고가·저가·종가·평균가, 선물 계약월 구별 |
| 3 | 리튬 | 전지급 수산화리튬 | Fastmarkets CIF; SMM VAT 포함/제외 |
| 4 | 니켈 | 금속 니켈(Ni) | **LME 정식 가격** (계약/현금·3M/일·통화/단위 명시) |
| 5 | 니켈 | 황산니켈(Nickel Sulfate) | SMM 증치세 포함/제외와 환산 방법 분리 |
| 6 | 코발트 | 금속 코발트(Co) | LME; FMB; 환산 시 LME ×22.3% 공식·기준 따로 |
| 7 | 코발트 | 황산코발트(Cobalt Sulfate) | SMM 증치세 포함/제외 |
| 8 | 망간 | 금속/망간 제품 | LME ×20.9% / FMB ×20.9% / SMM 포함·제외; 사용자가 제시한 열의 연결 관계는 원본 다단 헤더로 재확인 전 추정 금지 |
| 9 | 구리 | 구리(Cu) | FMB/LME 별도 |
| 10 | 환율 | USD/CNH/JPY(100)/EUR 등 | 중국은행/SMBS 구별; 기준/고시일/환산 단위 필수 |
| 11 | 블랙매스 | NCM/NCA | FMB 가격, 지역·품질·단위 |
| 12 | 블랙매스 | LCO Co Payable | FMB %, KR/EU 등 지역 구별 |
| 13 | 블랙매스 | NCM Ni/Co Payable | Ni와 Co 별도 % 및 Forecast/Actual 분리 |
| 14+ | 추가 품목 | 사용자 확장 | 동일 제품 사전에서 관리 |

주의: 사용자 표는 Markdown 변환으로 다단 헤더 열 경계가 흔들릴 수 있음. 30개 하위 열을 검증된 원본 Excel 헤더 기준 매핑. 곱하기 22.3%/20.9%는 **원본 제공 표기**이며 모든 제품에 무조건 적용하지 말고 식·원천·단위·수율 의미를 검증한 후 계산. LME 소스가 빈 경우 FMB/SMM을 LME라고 표시하지 말 것.

## 2. NAVER UI 그룹
참고 URL:
- 시장지표 홈 https://stock.naver.com/market/marketindex
- 금속 개별화면 https://stock.naver.com/marketindex/metals/CMNI0/price
- 국내 시총 순위 https://stock.naver.com/market/stock/kr/stocklist/capitalization
- 미국·글로벌 홈 https://stock.naver.com/market/stock/usa

사용자 첨부 미국 페이지 DOM 선택 항목 40건의 검증된 구조:
- S&P 500, NASDAQ Composite, Dow Jones: 지수 섹션에 제목, `장마감`, 시세, 비교/당일 차트와 '전일·고가·저가·52주 기준' 메타가 분리됨.
- 필라델피아 반도체, NASDAQ 100 등 보조 지수: 그룹 카드 안에 지수별 값·변화율 등이 들어 있음.
- DOM 내 첫 13개 요소는 **국내 시총 랭킹 화면**의 삼성전자/SK하이닉스/포스코홀딩스 `tr` 행도 포함되어 있음. URL 이름만 믿고 전체 DOM을 모두 미국 지수라고 분류하지 말 것. DOM/SPA 캐시/선택 맥락을 함께 검사.
- 지수 차트 `path` 등 SVG 화면 좌표는 **가격·시간 원본 시계열이 아님**. 이를 역사적 종가로 역산하지 말 것. DOM에 일봉 이력이 없으면 이력 미확보로 표시.
- 국내 랭킹 `SingleLinePrice_price__...`와 `highlight__...` 숫자가 분리되어 캡처 결과에 `20 8,00 0` 같은 공백이 포함됨. 전용 파서와 원문 대비 검증 없이는 가격 저장 금지.
- NAVER의 CSS Modules 해시 클래스는 변동 가능. semantic anchor (label, href, heading, table headers) 우선, 구조 변경 시 missing/error.

화면 그룹:
A. 금속/원료: 리튬(탄산·수산화) → 니켈(금속/황산니켈) → 코발트(금속/황산코발트) → 망간 → 구리 → 블랙매스(가격/Payable).
B. 환율/채권·금리: USD/KRW · CNH/KRW · JPY(100)/KRW · EUR/KRW / 미국 10년물 / 한국 10년물 / 중앙은행 기준금리 (시장 가격 vs 공식 금리 출처 따로).
C. 에너지/보조지표: WTI, 브렌트유, 금, 달러인덱스. 이들은 선택적 확장 그룹이며 core FMB/FX 수집 실패를 가리지 않음.
D. 국내 주식시장: KOSPI / KOSDAQ / 시총 상위 10 / POSCO홀딩스 별도 관심 항목; 날짜·범위 KRX 전체 확인.
E. 미국·글로벌: S&P500 / NASDAQ 종합 / Dow Jones → SOX(필라델피아 반도체) / NASDAQ100 / 다우운송 등 그룹, 시장별 시차·거래일 표시.
F. 자료·보고서: 내보내기, 수집 상태/누락, 보고 기준(기본 접힘, 맨 아래).

## 3. 시계열과 인터랙션
- 각 그룹 안에서 **비교 가능한 단위끼리** 동일 차트, 다른 단위는 분리/보조축 명시. 시계열 포인트는 SQLite 원천의 (series_key, date, value, source, quote_mode, status).
- 1개월 / 3개월 / 6개월 / 1년 / 전체 + 시작/종료 월 입력; 기준일 필터 바뀌면 차트와 표가 **동시에 바뀜**.
- 커서 hover/crosshair: 날짜·값·단위·원천·고시시각/상태·Forecast 여부; 복수 선이면 선택일의 각 시리즈 값.
- Actual/Forecast, VAT 포함/제외, LME/FMB/SMM을 색으로만 구별하지 말고 텍스트 라벨·범례로 표기. 결측값은 선을 끊고 0으로 보간하지 않음.
- Chart는 DB 또는 실제 검증된 값만 표시. UI 예시 더미 수치는 **DEMO**라고 크게 표시하고 운영화면에는 내보내지 말 것. HTML 보고서의 JS 인터랙션은 오프라인 동작으로, PPTX는 정적 도형/표 편집 유지.
- 사용자 요청: 보고서 하단 '자료 기준'은 접혀 있다가 펼칠 때 자세한 원천별 날짜/진단/수집 커버리지를 표시; 이 영역은 경고/수집 실패를 숨겨버리는 곳이 아님. 주요 실패는 헤더 상태에도 반드시 노출.

## 4. 수집 파이프라인 P0 진단
현행 `naver_markets.py` PAGES는 'https://stock.naver.com/market'와 KR capitalization + 구 finance.naver POSCO 페이지. 미국 `/market/stock/usa`와 새로운 `/market/marketindex`가 기본 수집 대상에 미포함. 추가만으로 끝나지 않음: SPA 네비게이션/DOM, 식별자, 종가 확정성, 개별 원천 URL, 일자·시장시간 검증의 새 어댑터 필요.
현행 NAVER INDICATORS=(KOSPI,KOSDAQ,SP500,NASDAQ,US10Y,KR10Y,GOLD,WTI); SOX/NASDAQ100/DJIA/WTI외 에너지/달러인덱스는 신규 등록 + 스키마 provenance 필요.
기존 `parse_capitalization`은 `data-stock-code` / 행 내 링크 `/stock/\d{6}`에 의존하므로 2026-10-23 선택 DOM (tr + 하위 이름/로고 URL)에서 코드를 찾지 못할 수 있음. 로고 URL의 코드 추출은 확정된 의미 검증 전에는 추정으로 사용하지 말 것.
현행 LME는 별도 공식 가격 시리즈 수집 근거가 확인되지 않음; **LME 가격을 읽어온 척 채우거나 FMB로 대체하지 말 것**. LME/BMF/SMM에서 사용자 요구 품목-출처별 coverage 매트릭스 작성 → 지원 여부/로그/분석용 DOM 판별. 정식 소스·계약·접근 경로 확인 후 별도 어댑터 추가.
회사의 허가된 브라우저만 사용. Chrome 9444(구독 FMB 전용) 유지; 9222/9337 간섭 금지, 보안 우회 금지. Excel 기존 시트/사용자 수식 보존, DB 원본 유지.
SMBS 환율은 은행 매매기준율; 중국은행 환율과 제공 시리즈를 혼동하지 않음. SMM/GFEX/LME 데이터 자동 수집은 권한/실제 경로 확인 전 '미지원/수집 불가' 명시.

## 5. 구현 단위 / 수용 기준
P0. A. `desktop_ui.py`: 자료·보고서 내 '자료 기준' 하단 QToolButton 접힘/펼치기(기본 false), 기존 보고 기능·필터 불변. `report_template.html`: `<details>` 하단 자료 기준 접힘(프린트 시 펼침/표시), 보고서 중요 경고는 상단 노출.
P0. B. `series_mapping.py`에 엄격한 품목 catalogue (공식 description→품명+시장+등급+지역+unit+source), `report_model.py` 보고용 금속 테이블 첫 열은 품목명, 코드 별도. 미해석→품명 확인 필요와 원래 코드 별도, 데이터 임의 병합 금지. 백업 및 회귀.
P0. C. LME + 기타 원천 coverage 진단. unsupported/missing/auth_failed/mismatch/captured/verified 상태를 구별.
P1. D. `desktop_tables.py` / 별도 Qt QWidget 그룹형 카드+시계열. DB에서 날짜별 리드 전용 정렬된 series record API + 그룹별 섹션 스크롤/툴팁, 기간 전환, 단위 충돌 검증.
P1. E. NAVER 신규 DOM adapter: marketindex / usa / KR capitalization. 시세가 보여도 미확정 종가이면 일별시세에 넣지 않음. NAVER 과거 확정일 2개 별도 근거 없으면 missing_history.
P2. F. HTML 보고서 그룹/차트, PPTX 동일 snapshot 정적 미러, 개별 보고서 필터/표 정합.
테스트: 제품별 이름·단위·원천 조합 불변; 날짜 1/3/6/12개월; hover label과 올바른 포인트; 빈 데이터; NAVER 가격 분할 DOM; 2개 확정 종가 부족; 미국 지수 장마감 vs 장중; 국내 시총 KRX 범위; 미지원 LME 빈 값; AG Grid pinned 날짜/virtual scroll; 변경 없는 Excel no-op.
배포: 모의/합성 테스트와 실 Windows/회사 웹/Excel/ECM 검증 완전히 구분. 수정 브랜치에 작은 범위별 커밋, 테스트 결과·성능·미검증 항목 기록 후 PR 리뷰. 실제 회사 스냅샷 Git commit 금지.

## 6. Codex 실행 프롬프트
"AGENTS.md를 먼저 읽어라. 위 작업지시서의 P0→P1 우선순위를 지켜 implementation+unit regression을 수행하고, 소스 없는 LME/새 NAVER 이력 값을 가짜로 채우지 마라. 사용자 회사 PC 데이터/브라우저를 건드리지 말고 코어 원본 데이터 계약부터 고쳐라. 차트는 누적 DB 실제 시세만 시각화하라. 추가된 제품/그룹은 실DB 미관측 상태가 정확히 노출되어야 한다. 먼저 실제 결함을 재현한 뒤 소스와 테스트를 별도 브랜치에 반영하고 PR로 제출하라."