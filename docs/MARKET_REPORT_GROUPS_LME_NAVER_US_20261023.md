# MIA 금속·시장 보고서 묶음 / NAVER US / LME 인수기준 (2026-10-23)

## 확정 요구 (사용자 제공 금속 표 기준)
- 전체 보고서의 `자료 기준·출처·검증 상태`는 **맨 아래**, 기본 **닫힘**, 클릭하여 **펼치기**.
- 첫 열은 `품목명` (예: "전지급 탄산리튬 · Fastmarkets CIF"); 금속시세코드는 별도 열에서 보조 식별자.
- 동일 금속의 복수 원천은 **하나의 품목 묶음 아래** 연속 표시. 같은 축에 단위나 환산기준이 다른 가격을 혼합하지 않음.
- 순서: 탄산리튬 → 수산화리튬 → 니켈 → 황산니켈 → 코발트 → 황산코발트 → 망간 → 구리 → BM NCM/NCA → BM LCO Co payable → BM NCM Ni/Co payable → 환율 → 국내 증시 → 미국·글로벌 증시.
- 1·3·6·12개월/전체 및 직접 시작·종료 월 조절. 마우스 오버 날짜, 값, 단위, 출처 노출. 가격이 없으면 비어 있음으로 표시.
- 국내 시가총액은 국내 증시 안에서, 미국 주식·ETF/NYSE·NASDAQ·AMEX는 미국 증시 안에서 연속 확인.

## 목표 원천/세부항목 (관리 기준, 수집완료 표시가 아님)
- 탄산리튬: Fastmarkets Spot Price CIF, GFEX 선물, SMM 함세가, SMM 세전가
- 수산화리튬: Fastmarkets Spot Price CIF, SMM 함세가, SMM 세전가
- 니켈: LME. 황산니켈 환산 지표(LME × 22.3% 등)는 원문 정의와 환산 기준이 입증될 때만 별도 시리즈로 표현; SMM 함세/세전 독립 기록.
- 코발트: LME, Fastmarkets. 황산코발트 환산(LME × 20.9%, FMB × 20.9% 등)은 원문 기준을 확인한 별도 계산 시리즈로 취급; SMM 함세/세전 독립 기록.
- 망간: SMM 함세/세전, Fastmarkets (LME × 20.9%는 망간 항목으로 오배치하지 않음).
- 구리: LME, SMM
- BM NCM/NCA CIF, BM LCO Co payable %, BM NCM Nickel/Cobalt payable % (서로 다른 단위)
- USD, CNH, JPY(100), EUR 등 SMBS 환율 + 중국은행 환율 원천은 별도
- 국내 KOSPI/KOSDAQ/KRX 전체 시가총액 및 미국 주요 지수·개별주·ETF 차트

## 이번 PR 코드 범위
- market_catalog.py: 수집된 종목 코드와 품목명·출처·그룹의 검증 가능한 매핑. 불확실한 품목은 "확인 필요"로 남김.
- market_report_ui.py: 불변 ReportContext의 검증된 일별시세만 그룹별 chart series로 변환; 누락 자료 0 채우지 않음.
- report_template.html + market_report.js: 로컬 HTML/JS 네이버 증권 참고형 묶음 및 기간별 단독 차트, 하단 접힘 기준, 국내 순위와 미국 종목 영역.
- report_model.py: 금속 보고용 테이블에 품목명을 선두로, 금속시세코드는 분리. DB 스키마 및 운영 수집 로직은 그대로.
- report_exports.py: 오프라인 static JS를 HTML과 같은 보고서 폴더에 원자적 저장. 네트워크 없음.
- test_market_report.py, test_v37_reports.py: 합성 회귀/출력 계약 보완.

## 미구현 — 출처가 없는데 수집 성공으로 표시하지 말 것
1. **LME 독립 수집**: 현재 pipeline_v37.py stage는 FMB/SMBS/NAVER, LME 전용 stage가 없음. NAVER `marketindex/metals/CMNI0/price` DOM의 `stx-holder` 차트는 값 자체를 포함하지 않는 캔버스 구성이며 공식 LME 정산값 증빙이 아님. 현물/선물, 일일 정산/지연 시세, 계약월, 단위(USD/t 등), 날짜, 제공 권한 확인 후 별도 LME 테이블과 별도 단계를 설계.
2. **SMM/GFEX/중국은행**: 원천 접근·단위·증치세 포함/제외·고시일·정산 여부 검증 전 가짜 데이터 생성 금지. LME × 22.3%, LME × 20.9%, FMB × 20.9% 같은 파생 계산은 원재료 정의·고정계수·환산 대상·단위를 명확히 검증한 별도 calculated series로 구현.
3. **NAVER 신 UI 검증**: 한국 시총 DOM은 `Table_table-viewport` 안의 `table>tbody>tr`이고 `SingleLinePrice_price` 및 `SingleLinePrice_highlight`로 숫자가 분리되어 있음. 입력은 2026-10-23 선택 요소 JSON이며 적합성 검증 필요. `KRX 전체` 필터와 종목코드·시가총액 단위를 먼저 검증할 것. 장중 현재가를 전일 확정 종가로 취급하지 않음.
4. **NAVER 미국 증시**: https://stock.naver.com/market/stock/usa 는 주식/ETF, NYSE/NASDAQ/AMEX, 시총/상승/하락/거래량 필터. 현재 수집기에는 미국 개별 종목 등락/랭킹 이력 저장이 없음. 미국 장 휴장일·현지 거래일·확정 종가·통화/단위·미국 거래소 scope 검증을 갖춘 별도 source stage 필요. DOM 캡처 없이 selector 또는 종목 가격/이력을 지어내지 말 것.
5. **실환경**: 회사 Windows/Chrome 9444/SSO/FMB 가입 세션, NAVER 변경 DOM, ECM 및 Excel DRM 파일은 로컬 합성 테스트로 승인할 수 없음.

## QA 필수
- `python -m unittest test_market_report.py test_v37_reports.py -v`
- `python -m unittest discover -s . -p 'test_*.py'`
- `node --check market_report.js`
- HTML을 직접 열어 그룹 순서, 월 필터, 차트 hover, missing 표시, 하단 자료기준 접힘, 원본 표의 모든 기존 값 및 코드 분리 확인.
- 악성 문자열 HTML 이스케이프 확인. 시장 데이터는 네트워크/서드파티 차트 라이브러리로 전송 금지.
- 스냅샷 SHA256, 원본 Excel 시트/수식, 수정 이력, ECM 권한 동작 불변.
- 테스트/PR은 합성용만. 실제 회사/구독 가격 DOM 및 실거래 가격을 공개 저장소에 넣지 않음.
