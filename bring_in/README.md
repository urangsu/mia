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

구 복원 자료는 `archive/legacy/`에 보관했습니다. 신규 설치에는 필요하지 않습니다.
무결성 확인은 발행자 신뢰나 회사 Windows/ECM 실검증을 대신하지 않습니다.
