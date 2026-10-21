# FDR · 캘린더 도입 검증 (2026-10-22)

기준 main `39392aa2947899932c09dc4e1dc42a1bf43956fe`, 개발 브랜치 `codex/fdr-market-calendars-20261022`. 회사 Windows/ECM 배포 승인서가 아니다. 실행 환경은 macOS arm64/Python 3.14.3이며 독립 가상환경을 사용했다.

## 의존성 및 범위

- finance-datareader 0.9.202 (MIT), exchange-calendars 4.13.2 (Apache-2.0)를 고정했다. 패키지 메타데이터/설치와 pandas·NumPy 의존성 해석을 확인했다. 시스템 Python에는 설치하지 않았다.
- 공개 HTTP 종가, 종료 세션 검증, 별도 원본/정정/보류 테이블, 누적 출력, 설정/CLI/Qt 화면 연결까지 구현했다. 기존 Selenium/ECM/COM 경로는 대체하지 않았다.
- KRX 일별 경로가 로그인 오류를 내는 것을 확인했다. 로그인 우회는 하지 않았으며 한국 지수/주가는 공개 NAVER 경로로 한정했다.

## 오프라인/모의 검증

아래 `python`은 같은 가상환경 실행 파일이다. 테스트용 외부 네트워크 경계만 주입하고 실제 pandas/exchange_calendars/openpyxl/python-pptx를 사용했다.

```bash
QT_QPA_PLATFORM=offscreen python -m unittest discover -s . -p 'test*.py' -q
python -W error::ResourceWarning -m unittest discover -s . -p 'test_v37*.py' -q
python -m pip check
python -c 'import pathlib,py_compile; files=list(pathlib.Path(".").glob("*.py")); [py_compile.compile(str(p),doraise=True) for p in files]; print(len(files))'
python benchmark_v37.py --runs 10
```

| 검사 | 결과 |
|---|---|
| 전체 회귀 (Qt offscreen 포함) | 292개 통과, 5.830초, exit 0 |
| 기존 v3.7 엄격 ResourceWarning 검사 | 92개 통과, 0.628초, exit 0 |
| 신규 FDR/거래일/보고서/통합 | 26개, 전체 회귀에 포함 |
| 의존성 / Python 컴파일 | 깨진 의존성 없음 / 78개 컴파일 성공 |
| 합성 CPU 계획 성능 10회 | 평균 1.332ms, P95/최악 1.694ms, 실패 0 |

전체 회귀에는 기존 일부 테스트의 SQLite 연결 ResourceWarning이 남는다. 이를 무경고 전체 통과라고 표현하지 않는다. 엄격 검사는 기존 v3.7 대상만 92개이며 전체292개에 경고를 에러로 승격한 결과가 아니다. 합성 성능은 sparse-block 계획만 측정한 것으로 실제 COM/네트워크 30% 단축 증거가 아니다.

새 검증은 휴일·DST·조기 종료·당일 제외·게시 유예, NaN/Adj Close 배제, 중복일 가격 충돌 보류, 일일 캐시/정정, 보류값 Excel 삭제와 복구, source별 키/필터, 25개 초과 누적 관심종목 이력, HTTP 자식 시간초과/취소 회수, 공개 전용 최초 DB/CSV, CLI 옵션, 설정 roundtrip, 편집 가능 PPTX와 공통 스냅샷을 포함한다. 독립 코드 리뷰에서 발견된 필터·기준 시각·충돌 철회·누적 종목 경계는 실패 테스트를 먼저 추가해 수정했다.

## 실제 공개 사이트 실행

회사 계정/브라우저/파일을 사용하지 않고 새 임시 폴더에 다음 명령을 실행했다.

```text
python FastmarketsCollector_v3_7.py --once --public-only --data-dir <임시폴더> --workbook <임시폴더>/public.xlsx --report-dir <임시폴더>/reports
```

2026-10-22 오전 KST 조회: FDR 6.224초, 전체 6.467초, 원본245행 저장. KOSPI/KOSDAQ/SP500/NASDAQ/US10Y/005490의 기대 두 날짜는 2026-10-21/2026-10-20이며 모두 확보했다. GOLD/WTI는 10-20 Close가 원천 NaN으로 기대 두 종가를 확보하지 못했다. KR10Y는 지원 경로 미확정이다. 따라서 정상적으로 **partial/exit 2**이며 8개 지표 완전 수집 성공이 아니다.

Excel 42,443 bytes, CSV 37,466 bytes, HTML 12,300 bytes, 편집 가능한 PPTX 42,109 bytes가 생성됐다. context snapshot `df856947f0a548c33355eb2bda52bad9d47ab10047443033aa898b28d9a34c43`을 기준으로 실제 저장 파일을 다시 열어 Excel 표 값/날짜, PPTX native-table 140셀, HTML 수치와 snapshot ID를 대조했다. 빈 문자열은 XLSX에서 빈 셀(None)로 직렬화되는 차이만 정규화했고 수치/날짜를 반올림하거나 누락을 성공으로 바꾸지 않았다. 회사 자료/실제 수집 로그와 출력 바이너리는 Git에 포함하지 않는다.

## 남은 인수

Windows COM·회사 보안 Excel·FMB 구독 전체 inventory/실DOM·ECM 탐색/서버 체크인·08:30 예약 실기동은 미검증이다. 이 통합은 기존 DOM inspector/금속 추출의 완전성 증거가 아니다. KR10Y·시총 전체 경로, 원천 게시 지연과 선물 달력 정합성은 별도 과제다. 외부 사이트 장애/형식 변경 가능성도 남는다. [Windows 최소 검증 절차](FDR_CALENDARS_GUIDE.md#windows-최소-인수-절차)에 따라 사본에서 확인한다.
