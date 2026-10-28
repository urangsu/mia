# 회사 반입 파일

현재 반입에는 아래 파일만 사용합니다. 예전 ONEFILE/PART 파일과 섞지 마세요.

- `MIA_SOURCE_CURRENT.txt` — 전체 소스 데이터, 실행하는 TXT가 아닙니다.
- `RESTORE_LATEST_SOURCE.py` — Python 기본 라이브러리만 쓰는 검증·복원기.
- `RESTORE_LATEST_SOURCE.cmd` — 선택 사항, 같은 폴더의 TXT를 복원합니다.
- `MIA_COMPANY_SETUP_GUIDE_KO.txt` — 파일 배치·복사할 명령·설치·실행 설명.

모두 `%APPDATA%\Microsoft\AddIns\vsc\매크로`에 바로 놓아도 됩니다.
복원은 같은 위치의 **MIA_Collector_Update** 새 폴더에 수행하며 날짜를 붙이지 않습니다.
이미 그 폴더가 있으면 중단합니다. 기존 운영 폴더·DB·Excel을 삭제하지 마세요.
실행 파일은 복원 폴더의 **MIA_Collector.py** 또는 **RUN_GUI.cmd**입니다.
내부 소스·테스트·문서는 `app/`에 모았습니다.

## 누적 자료는 프로그램 폴더 밖에

기본 데이터 폴더는 `%USERPROFILE%\Documents\FastmarketsCollector`이며,
`fastmarkets_prices_v3.sqlite3`가 누적 DB입니다. 회사 계정이라면
`C:\Users\POSCOHYCM\Documents\FastmarketsCollector`입니다.
기존 설정이 있으면 그 경로가 우선하므로 GUI 설정에서 반드시 확인하세요.
프로그램만 새로 복원해도 기존 DB가 반입 TXT에 포함되거나 자동 이동되지는 않습니다.
Excel/CSV는 DB에서 다시 출력할 수 있지만 수기 내용·수식·ECM 원본의 백업은 아닙니다.
교체 전 기존 데이터 폴더 전체를 보관하고, 프로그램 폴더도 삭제 대신 이름을 바꿔 두세요.
자세한 절차는 `MIA_COMPANY_SETUP_GUIDE_KO.txt` 0번과 `docs/DATA_RETENTION_KO.md`에 있습니다.

## DOM 확장은 아직 별도

이 반입 TXT에는 DOM Inspector V4 원본이 없습니다. 원본 확보 전까지 함께 복원된다고
안내하지 않습니다. 기존 확장 폴더는 보존하세요. 실제 `manifest.json`이 있는 폴더를
확보한 경우에만 `chrome://extensions` → 개발자 모드 → 압축해제된 확장 프로그램 로드로
등록합니다. `GET_LATEST_DOM_V4.txt`만으로는 등록할 수 없습니다.

구 복원 자료는 `archive/legacy/`에 보관했습니다. 신규 설치에는 필요하지 않습니다.
무결성 확인은 발행자 신뢰나 회사 Windows/ECM 실검증을 대신하지 않습니다.
