# 설치·공개 수집·화면 수정 기록

## 확인한 실패 원인

- 설치 안내가 파일 실제 위치가 아닌 날짜 하위 폴더를 전제함.
- NAVER 현재 시총 행은 링크가 아닌 role=button이며 공식 로고에 코드가 있음.
  가격은 중첩 span, 시총은 조+억 표시. 부분 hydration 행은 필수 셀이 없기도 함.
- 이전 수집기는 현재 화면 한 개만 읽어 첫날 두 종가 이력을 확보하지 못함.
- 시총 원자료 화면이 이미 종가 필터를 거친 데이터만 표시함.
- 시총 비교는 실제 비교 계산이 없었음. POSCO 종가의 빈 시총이 비교를 막기도 함.
- 오래된 FDR target과 캘린더 오류가 정상 NAVER까지 가리거나 전체 화면을 중단함.
- 보고 Excel 오류가 이미 만든 HTML/PPTX 경로까지 숨길 수 있었음.

## 수정

- 실제 TXT 옆 고정 `MIA_Collector_Update` 복원, 절대경로 명령, .venv 우선.
- 고정 `MIA_Collector.py`, `MIA_Collector.zip` 이름. 최상위 5파일+app 내부 소스 구조.
- 구 실행기·ONEFILE/PART는 archive로 보관. 사용 중 코어/테스트/사용자 데이터 삭제 없음.
- 로그인 없는 NAVER 날짜/종가 표를 8개 지표와 Top10+POSCO 주가에 연결.
  Chrome 9444 기존 검증 연결만 사용, 만든 탭만 닫고 원래 탭으로 복귀.
- 한 공개 페이지의 접속 실패와 부분 hydration이 다른 성공 자료를 폐기하지 않음.
- 시총 원자료와 수집시점 비교 분리, 조/억을 억원 단위로 정확 환산.
- NAVER 기본, FDR/Yahoo는 신규 설정에서 선택 사항. 공개 종가 버튼은 NAVER만 실행.
  예전 설정을 자동 덮어쓰지 않으므로 기존 사용자는 설정에서 FDR 선택을 확인.
- 금속 누적 Excel과 시장 보고서 분리. 각 보고 형식 실패 격리.
- 확인 내역 기본 접힘, 금속 출처 열 숨김, 시장 탭은 자료·보고서로 이동.
- LME 공개 Official 표의 니켈·구리·코발트 Cash/3-month Bid/Ask 12개를 전용 DB에 저장.
  Cash Ask(Official Settlement)·3-month Ask 6개를 운영 누적표와 별도 보고에 연결.
  Bid는 원본과 선택형 차트에 남기며 평균 Mid를 만들지 않음. 부분 갱신+기존 반대편
  가격을 합친 결과 Bid>Ask이면 전체 배치를 거부하고 이전 데이터/감사 이력을 보존.

## 직접 확인한 공개 경로

- `stock.naver.com/domestic/index/KOSPI/price`, KOSDAQ
- `stock.naver.com/worldstock/index/.INX/price`, .IXIC
- `stock.naver.com/marketindex/metals/GCcv1/price` (COMEX 최근월물, 현물 아님)
- `stock.naver.com/marketindex/energy/CLcv1/price` (NYMEX 최근월물)
- `stock.naver.com/marketindex/bond/US10YT=RR/price`, KR10YT=RR (국채수익률)
- `stock.naver.com/market/stock/kr/stocklist/capitalization` (KRX 전체 실시간 순위)
- `stock.naver.com/domestic/stock/005930/price` (개별 주식 일별 시세)

Computer Use로 로그인 없이 실제 화면을 확인하고 DOM을 임시 폴더에만 보관해
파서 재생 검증했습니다. 실가격/DOM/로그는 Git에 포함하지 않습니다.
8개 지표와 국내 주가 11개의 10/26·10/23 두 날짜, 시총 Top10+POSCO 11개를 인식했습니다.
LME 실제 DOM은 고시일 10/26, 갱신일 10/27을 구분해 12개 가격을 인식했습니다.
실제 DOM 재생→임시 SQLite→차트 12개 시리즈→운영 LME Ask 6열→4형식 보고서를 확인했습니다.
실제 Windows ChromeDriver 연결/회사 프록시·DRM Excel·ECM 서버는 별도 검증 대상입니다.

## 남은 검증

- 회사에서 새 복원본 `RUN_GUI.cmd`, 공개 종가 수집, 기존 FMB·SMBS 회귀.
- 금속 누적 Excel 사본에서 시장 열이 신규 추가되지 않는지 확인.
- 보고서 Excel·HTML·편집 가능한 PPTX 간 날짜·값·단위 비교.
- 실제 08:30 예약 실행 및 ECM 승인/저장/서버 체크인은 회사에서 확인.
- 사용자 사진의 정확한 고정 열 매핑, SMM/GFEX 수집은 아직 완성 아님.
- LME는 위 공개 Official Cash/3-month만 지원. Closing/현물 추정/유료 과거 이력 미지원.
- 미국 개별 주식 전체 시총 순위는 이번 범위가 아니며 미국 지수 두 개를 수집.
