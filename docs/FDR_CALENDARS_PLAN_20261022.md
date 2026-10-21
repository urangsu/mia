# FinanceDataReader · exchange_calendars 도입 계획

Goal: 공개 가격 이력을 실제 수집·SQLite·공통 보고서·GUI·CLI·예약에 연결하고 검증 후 개발 브랜치에 푸시한다. 기존 FMB/SMBS/ECM 및 DOM 수집은 보존한다.

Architecture: 브라우저 없는 FDR 단계와 출처별 별도 원본 테이블을 추가한다. exchange_calendars는 종료된 거래일과 기대 비교일 검증에 사용하며 가격·고시·정산 근거를 만들어내지 않는다. FDR의 HTTP 호출은 소유한 자식 프로세스로 한정하고 시간 초과/취소로 회수한다. 최신 기대 거래일 누락은 과거 값으로 대체하지 않는다.

기본 공개 대상: NAVER의 KOSPI/KOSDAQ/POSCO 005490, Yahoo의 S&P500/NASDAQ/미국10년 지수/GC=F 금 연속선물/CL=F WTI 연속선물. 실제 조회에서 Yahoo 한국 지수 최신 Close 누락을 확인해 NAVER 일별 이력을 선택했다. 실제 원천 URL·심볼·시장일·Close·단위·캘린더·검증 근거를 보존한다. 한국10년은 검증된 지원 경로가 없어 미지원으로 표시한다. 시총 순위는 FDR 종가로 조작하지 않는다. 금 선물과 현물, Yahoo Close와 공식 정산가는 동의어가 아니다.

## 순서와 합격 기준

- [ ] 실제 패키지 설치/지원 경로/라이선스/공개 읽기 조회를 조사하고 버전을 고정한다.
- [ ] `test_market_sessions.py`: 한국/미국 휴일·조기 종료·DST·08:30·당일 제외·기간 밖 실패 검증 후 `market_sessions.py` 구현.
- [ ] `test_fdr_provider.py`: 종목 매핑/실제 DataFrame 변환/NaN·중복일 충돌/시간초과·취소/재실행 no-op·정정 이력/부분 실패를 재현 후 `fdr_provider.py` 구현.
- [ ] `test_fdr_reporting.py`: 원본 DB→두 기대 거래일→금속과 분리된 공개 지표/주가→동일 스냅샷 Excel/HTML/PPTX 및 원본 시트 검증. 기존 NAVER 원본을 덮어쓰지 않는다.
- [ ] 파이프라인 독립 단계·일일 캐시·설정/CLI/Qt 입력을 연결한다. 공개 전용 실행은 브라우저 connect를 부르지 않아야 한다.
- [ ] 신규 설치 의존성과 오프라인 검사 계약을 정리한다. 실제 공개 조회는 명시적 진단 명령만 사용한다.
- [ ] 기존 전체 회귀/전용 엄격/Qt 테스트, 패키지 검사, 공개 종가 조회·임시 DB·세 출력 read-back을 수행한다. 회사 Windows·ECM·예약 실기동은 별도로 명시한다.
- [ ] 변경을 기능별 커밋하고 SSH push, 원격 HEAD/내용 확인. 요청에 없는 main 병합·운영 예약 등록은 하지 않는다.

기준: main 39392aa. 순수 함수 테스트는 실제 exchange_calendars와 pandas를 사용하고 외부 네트워크 경계만 주입한다. 사용자 DB/Excel·계정·브라우저·공개 Git의 회사 자료는 사용하지 않는다.

## 실행 결과

구현·설치·오프라인 회귀·공개 전용 실조회·세 출력 read-back을 수행했다. 체크리스트는 원래 계획을 보존하며 최종 증거와 남은 인수 경계는 [검증 보고서](FDR_CALENDARS_TEST_REPORT_20261022.md), 사용법은 [운영 안내](FDR_CALENDARS_GUIDE.md)를 따른다. 회사 Windows·보안 Excel·ECM·08:30 실기동은 이 환경에서 검증하지 않았다.
