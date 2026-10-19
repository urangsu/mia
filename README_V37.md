# Fastmarkets Collector v3.7

Windows 업무용 후보 빌드입니다. 실제 회사 Windows·Fastmarkets 구독 화면·ECM에서의 인수 검증은 아직 수행하지 않았습니다. 기존 v3.6 ZIP과 회사 원본은 덮어쓰지 않았습니다.

## 시작하기

1. ZIP을 Windows의 고정 폴더에 풉니다. 예약 등록 후 이 폴더와 Python을 옮기지 마세요.
2. 회사에서 허용한 Python 3.10 이상과 데스크톱 Excel을 준비합니다.
3. 터미널에서 `py -m pip install -r requirements.txt` 실행.
4. `RUN_GUI.cmd` 실행. 연결·저장·자동 실행 설정에서 기존 데이터 폴더와 누적 Excel 사본을 지정합니다. 기존 DB 파일명은 `fastmarkets_prices_v3.sqlite3` 그대로입니다.
5. Chrome 연결·로그인으로 Fastmarkets 9444를 확인합니다. 계정은 명시적으로 저장할 때 OS 자격 증명 저장소에만 기록합니다. MFA는 사람이 처리해야 합니다.
6. 처음에는 시세 수집·Excel 갱신만 실행합니다. 결과가 맞으면 ECM 미리보기를 열고 실제 문서 경로·변경 셀을 승인합니다.

Python 프로그램 기본 진입점은 `FastmarketsCollector_v3_7.py`입니다. `FastmarketsCollector_v3_4.py`는 이름만 유지한 기존 수집 코어입니다. 과거 버전 진입점과 문서는 호환·참고용이며 새 예약/GUI에는 사용하지 마세요.

### 2026-10-20 hotfix1

새 배포는 별도 폴더에 풀고 `RUN_GUI.cmd`로 실행하세요. 기존 데이터 폴더와 Excel은 사본으로 먼저 확인합니다. 자동 생성되는 **보류셀** 시트는 프로그램 관리 영역이며 직접 메모하지 마세요. 가격 충돌이 확인되면 일별 관리 셀과 검증 표본이 없는 월평균 셀의 기존 숫자를 비우고 사유를 이 시트에 남깁니다. 일반적인 이력 누락은 기존 숫자를 지우지 않습니다. 월별 건수는 검증된 표본만 세며 0이 될 수 있습니다.

ECM은 `충돌 수치 보류로 기존 값 비우기` 건수까지 미리보기에서 확인하고 승인해야 적용됩니다. 사용자 수식이 있는 대상은 비우지 않고 중단합니다. 열 등록은 충돌 중에도 유지하므로 충돌이 해소되면 동일한 열에 다시 반영됩니다. 이미 과거 버전에서 열 등록이 사라진 파일은 임의 추정으로 연결하지 않으므로 정상 사본/백업에서 매핑을 복구해야 할 수 있습니다. 자세한 결과와 남은 제한은 [수정·검증 안내](FIXES_V37_HOTFIX1.md)에 있습니다.

## 매일 오전 8시 30분 자동 실행

GUI 설정의 자동 실행 등록 또는 `REGISTER_DAILY_0830.cmd`를 사용합니다. 다른 시각은 아래 명령을 사용하세요.

```text
py FastmarketsCollector_v3_7.py --schedule 08:30
py FastmarketsCollector_v3_7.py --schedule-status
py FastmarketsCollector_v3_7.py --unschedule
```

이 명령은 실행한 회사 Windows PC에만 `FastmarketsCollectorDaily` 작업을 등록합니다. Mac에는 등록하지 않았습니다. 사용자 로그인 세션, 네트워크, 구독 권한이 필요합니다. 관리자 권한이나 Windows 암호를 저장하지 않습니다. 동시 실행은 무시하고, 실행을 놓쳤으면 가능해진 시점에 보강합니다. 오류 시 5분 간격으로 최대 2회 재시도합니다.

절전 깨우기는 Windows/장비 정책이 허용할 때만 작동합니다. 전원이 완전히 꺼진 PC는 켤 수 없습니다. 로그아웃 상태, SSO 만료, MFA, 사내망 단절에는 사용자 조치가 필요합니다. 예약 실행은 FMB·환율·NAVER·누적 Excel·보고서까지만 수행하며 ECM 승인 쓰기를 자동으로 하지 않습니다.

예약 등록 후 스케줄러에서 다음 실행 시각을 확인하고, 2~3분 뒤 시각으로 한 번 시험 등록해 실제 자동 기동과 DB/보고서 생성까지 확인한 뒤 08:30으로 되돌리세요.

## NAVER는 전일 종가 비교

한국시간 실행일보다 이전인 실제 시장일 중 최근 확정 종가와 그 직전 거래일 종가를 비교합니다. 월요일·휴일에는 달력상 어제/그제가 아니라 저장된 거래일을 사용합니다. 해외 시장은 원문 시장일을 보존합니다. 보고서에 두 날짜를 함께 표시하고, 저장된 두 종가로 대비·등락률을 계산합니다.

장중 값, 미래 날짜, 날짜 불명, 종료 근거 없는 오래된 수치는 종가로 사용하지 않습니다. 현재가와 제공업체의 등락값을 이용해 과거 종가를 역산하지 않습니다. 최초 실행에 확인된 두 거래일 이력이 없으면 `missing_history`로 표시합니다. 그날 수집값 하나만으로 비교표가 완성되지는 않습니다. 실제 NAVER 과거 종가 화면 샘플은 제공되지 않아 자동 과거 이력 탐색은 검증되지 않았습니다.

대상은 KOSPI, KOSDAQ, S&P500, NASDAQ, 미국10년, 한국10년, GOLD, WTI와 KRX_ALL 시총 Top10+005490입니다. 실제 화면이 합성 fixture와 다르면 실패·부분 수집으로 보고하며 숫자를 추정하지 않습니다. 시총 단위와 주가 단위를 혼용하지 않습니다.

## 재수집 없는 복구

```text
py FastmarketsCollector_v3_7.py --once
py FastmarketsCollector_v3_7.py --export-only
py FastmarketsCollector_v3_7.py --reports-only --start 2026-10-01 --end 2026-10-19
py FastmarketsCollector_v3_7.py --reports-only --series KOSPI,MB-LI-0029
py FastmarketsCollector_v3_7.py --once --naver-force
py diagnose_windows.py --driver-check
py collect_evidence_v37.py --output evidence_v37.json
```

기간·종목 필터는 보고서 전용입니다. 누적 원본 Excel을 필터로 축소하지 않습니다. NAVER 보고 종료일은 그 날짜 이전 확정 종가의 기준일로 사용합니다. 같은 불변 스냅샷으로 HTML·편집 가능한 PPTX·JSON과 누적 Excel을 만듭니다. `자료 기준 시각`은 파일 생성 시각이 아니라 저장된 관측의 기준 시각입니다.

Excel·ECM만 실패하면 재수집하지 말고 출력 재시도/ECM 재시도를 선택합니다. 가격 충돌은 원본을 보존하고 해당 수치만 반영 보류합니다. 기존 누적 Excel은 Windows Excel COM에서만 갱신합니다. 비Windows에서 기존 파일을 openpyxl로 덮어쓰지 않습니다.

## 브라우저·문서 보호

- FMB는 Chrome 9444·전용 프로필·소유 PID/CDP 확인을 유지합니다. 9222·9337에는 연결하거나 프로세스를 종료하지 않습니다.
- ECM은 기존 일반 Edge의 UI Automation만 사용합니다. 관리자 Edge를 새로 띄우거나 쿠키/토큰을 복사하지 않습니다.
- ECM 파일 열기 전후 관측한 FullName+Excel HWND로 바인딩합니다. 같은 이름의 기존 미확인 파일, 다른 Excel 인스턴스, 읽기 전용 문서는 차단합니다. 최초 바인딩 때 이미 열린 파일은 사용자가 닫은 뒤 ECM에서 다시 열어야 할 수 있습니다.
- 수식·사용자 열·빈 헤더 아래의 사용자 값은 보존합니다. 본 프로그램이 관리하는 RawData/보고용/감사 시트는 재생성 영역이므로 직접 메모하지 말고 별도 사용자 시트를 사용하세요.
- Excel Save+셀 재읽기는 ECM 서버 체크인 성공이 아닙니다. 결과는 서버 반영 미확인으로 남습니다.
- 새 DB 스키마 적용 전 기존 SQLite를 backups에 검증 백업합니다. 동일 관측 재실행은 가격 revision을 불필요하게 만들지 않습니다. 실행 이력·수집 메타데이터는 별도로 기록됩니다.

## 디자인

제공된 DESIGN.md의 어두운 계층형 배경, 간결한 표, 한국 금융권 상승 빨강/하락 파랑, 낮은 장식을 적용했습니다. 전용 Toss 폰트·로고·브랜드 문구는 배포하지 않습니다. 실시간 호가처럼 보이지 않도록 실제 기준일과 미확인 상태를 표시합니다.

## 검증과 미검증

`VALIDATION_V37.md`에 재실행 결과와 범위가 있습니다. 합성 화면/모의 COM 테스트를 회사 Windows 성공으로 해석하지 마세요. 실구독 전체 종목, BM 실패 DOM, 실제 NAVER 종료·과거 이력 DOM, 보안 Excel, ECM 서버 체크인은 실제 PC 검증이 남아 있습니다. 유료 API·뉴스·AI 해설·메일 발송은 추가하지 않았습니다.

개발 테스트: `py -m unittest discover -s . -p "test*.py" -v`.
합성 성능: `py benchmark_v37.py --runs 10`. 숫자 쓰기 호출 구조를 측정할 뿐 실사이트 속도나 30% 단축을 증명하지 않습니다.
