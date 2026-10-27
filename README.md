# mia · 금속 시황 수집기

금속·환율을 날짜별로 누적하고, 주가·지수·시총은 별도 Excel·HTML·편집 가능한
PPTX 보고서로 만드는 Windows 업무 도구입니다. 현재는 회사 실환경 인수 전 개발판입니다.

## 회사에서 가져갈 파일

[반입 폴더](bring_in/README.md)의 **MIA_SOURCE_CURRENT.txt + RESTORE_LATEST_SOURCE.py**가 필수입니다.
[한글 안내 TXT](bring_in/MIA_COMPANY_SETUP_GUIDE_KO.txt)에 파일 위치·복사할 PowerShell
명령·설치·실행·진단을 모았습니다. 파일을 `vsc\매크로`에 바로 두어도 됩니다.
복원 폴더는 날짜 없는 `MIA_Collector_Update`, 실행기는 **MIA_Collector.py / RUN_GUI.cmd**입니다.
기존 대상이 있으면 덮어쓰지 않습니다. 내부 소스·테스트·문서는 반입본의 `app/`에 있습니다.

## 기능과 경계

- FMB: 검증된 Chrome 9444의 기존 구독 화면. 9222/9337·관리자 Edge에는 간섭하지 않음.
- SMBS: 기존 환율 경로 유지.
- LME: 로그인 없는 공개 Official 표. 니켈·구리·코발트 Cash/3-month Bid·Ask를 분리.
  운영 금속표는 Cash Ask(Official Settlement)·3-month Ask 6열. 임의 Mid 계산 없음.
- NAVER: 로그인 없는 실제 일별 시세. 8개 지표와 KRX Top10+POSCO의 두 날짜 종가.
- 시총: 거래 기준일 없는 실시간 원자료와 수집일 간 스냅샷 비교. 첫날 이전 시총은 없음.
- FDR/Yahoo: 선택 사항, 새 설정의 기본 꺼짐. 기존 설정은 자동 덮어쓰지 않음.
- 운영 Excel/ECM: 금속·환율만. 주가·지수·시총은 자료·보고서에서만 표시.
- 화면 확인 내역은 기본 접힘. 출처·품질 근거는 내부/보고서에 보존.

SMM/GFEX, LME Closing/유료 과거 이력, 미국 개별 주식 전체 순위는 미구현입니다.
실제 공개 사이트 확인·DOM 재생 검증과 회사 Windows ChromeDriver/DRM Excel/ECM
서버 검증은 구분합니다. 예약 기본 시각은 08:30이며 로그인한 대화형 Windows 세션이 필요합니다.
ECM 승인 쓰기를 무인 예약하지 않습니다.

## 개발 소스에서 실행

```text
py -3 -m pip install -r requirements-desktop.txt
py -3 MIA_Collector.py
```

소스 저장소에서는 파일이 루트에 있으며 반입본에서는 `app/`에 모입니다.
실제 공통 코어는 `FastmarketsCollector_v3_4.py`, 내부 명령 처리기는
`FastmarketsCollector_v3_7.py`입니다. 구 실행기와 ONEFILE/PART는 archive로 보관했습니다.

## 이어 작업 / 검증

[AGENTS.md](AGENTS.md), [작업지시](docs/CODEX_WORK_ORDER.md),
[수정 범위와 실사이트 확인](docs/COLLECTION_INSTALL_REPAIR_20261027.md),
[사진 기준 누적표 구조](docs/METAL_WORKBOOK_LAYOUT.md), [인수 경계](HANDOFF_V37.md)를 읽습니다.
오프라인 설치/검증: `bash scripts/codex_setup.sh`, `bash scripts/codex_check.sh`.
과거 버전 기록은 [변경 내역](CHANGELOG_V37.md)에 보존합니다.

Git에는 소스·합성 fixture·문서만 올립니다. 계정·쿠키·프로필·회사 DB/Excel·실DOM·실가격 로그는 올리지 않습니다.
