# 수정 검증 보고서

## 판정

코드/오프라인/공개 DOM 재생은 통과했습니다. 회사 운영 승인본이라는 뜻은 아닙니다.
검토한 런타임 코드 기준 커밋은 `72c0a59ad239f76a807afafd755f78f2181beb1f`입니다.
이후 소스 패키지에 포함되는 검증 문서/TXT 변경은 런타임 코드 변경과 구분합니다.
실제 배포 소스 기준과 ZIP/파일별 SHA-256은 TXT 헤더와 SOURCE_MANIFEST.json에 있습니다.

## 실행한 검사

```text
QT_QPA_PLATFORM=offscreen <Python3.14.3> -W error::ResourceWarning -m unittest discover -s . -p 'test*.py' -q
412 tests / 7.987 seconds / OK / exit 0

복원된 app/에서 같은 엄격 검사
412 tests / 7.883 seconds / OK / exit 0

Python py_compile: root source 97개 / exit 0
MIA_Collector.py --help: checkout와 clean root/app 복원본 모두 exit 0
RESTORE_LATEST_SOURCE.py --verify-only 및 새 폴더 복원: exit 0
```

검사 중 보이는 argparse 오류/합성 설정 오류/ECM 미리보기 문구는 의도한 음성 테스트입니다.
마지막 unittest 결과와 종료코드로 판정합니다. 실제 Windows CMD/PowerShell 실행을 대신하지 않습니다.

검증 환경: macOS arm64, Python 3.14.3, PySide6-Essentials 6.12,
exchange-calendars 4.13.2. 한글/공백 임시 경로·다른 현재 폴더·같은 대상 재복원
거부·운영 폴더 보존·.venv 우선 진입점은 별도 subprocess 테스트로 확인했습니다.

## 실제 공개 사이트와 DOM 재생

Computer Use로 로그인 없이 NAVER 지표 8개, 국내 Top10+POSCO 주가 11개,
KRX 전체 시총 표, LME 공개 Official 가격 표를 직접 열었습니다.
LME는 `Data valid for 26 Oct 2026`과 갱신일 `27 Oct 2026`을 구분했습니다.
실DOM/실가격/임시 DB/보고서 파일은 로컬 임시 폴더에만 두고 Git에 올리지 않았습니다.

실제 DOM을 프로그램 수집 경로의 driver 재생 입력으로 사용한 결과:

- 네이버 지표 이력 158행, 주가 이력 209행, 미확정 시총 캡처 11개.
- 보고: 지표 8개와 주가 11개 모두 두 실제 날짜의 종가를 표시.
- 시총 원자료 11개. 첫날 비교는 missing_prior_capture이며 전일 시총을 추정하지 않음.
- LME 12개 가격(3금속×2계약×Bid/Ask), 고시일 10/26.
- LME 선택형 차트 12개 시리즈, 운영 Ask 6열, 별도 LME 보고 6행.
- HTML/JSON/Excel/편집 가능한 PPTX 생성. 합성 교차검사로 셀 값을 재읽어 동일성 확인.
- 재수집 시 검증 이력 행 수 불변, NAVER 가격 수정 이력 0, LME unchanged 12.
  원자료 감사 캡처는 재실행마다 추가 보존함.
- 재생 21페이지 처리+DB+출력 2.121초. 이는 네트워크/회사 COM 실행 시간이 아님.

NAVER 전체 상태는 시총의 거래 기준일 미확인 때문에 partial을 유지합니다.
국채 두 날짜는 읽었지만 주식시장 캘린더를 국채 휴일에 대신 쓰지 않아
calendar_unverified로 최신성 경고를 남깁니다. 나머지 여섯 지표의 기대 세션은 확인했습니다.

## 성능 및 코드 리뷰

`benchmark_v37.py --runs 10`: 합성 CPU 블록 계획 평균 0.001335초,
P95/최악 0.001654초, 실패율 0%, 예시 쓰기 호출 5000→2.
브라우저/네트워크/수식 검사/DRM/Save·reopen을 제외한 수치이며 전체 30% 단축 근거가 아닙니다.

독립 코드 리뷰에서 발견한 부분 DOM KeyError, FDR target의 NAVER 은폐,
빈 POSCO 시총의 비교 차단, 출력 실패 전파, LME PPTX 누락, 부분 갱신 Bid>Ask,
새 탭 생성 실패 시 원래 탭 닫힘을 각각 재현한 뒤 수정했습니다.
최종 타깃 리뷰는 병합 가능, 남은 확인된 P0/P1 없음으로 판정했습니다.

## 남은 인수 검사

- 현재 Mac의 9444 Listener는 없음. 회사 Windows ChromeDriver 연결·프록시·SSO는 미검증.
- 회사 DRM Excel 사본의 실제 COM 쓰기/수식/날짜 고정열 보존은 미검증.
- ECM 기존 일반 Edge 탐색·승인·Excel 저장과 서버 체크인은 회사에서 별도 확인.
- 08:30 로그인 사용자 예약의 실제 반복 실행은 회사에서 확인.
- SMM/GFEX, LME Closing·유료 과거 이력, 미국 개별 주식 전체 순위는 미구현.
- 사진의 흐린 헤더를 실제 종목 코드에 연결하는 고정 양식 매핑은 원본 확인 후 진행.

원본 회사 프로그램을 지우지 말고 MIA_Collector_Update에서 새 데이터 폴더·Excel 사본으로
공개 수집→기존 FMB/SMBS→누적표→보고서→ECM 순으로 확인하세요.
