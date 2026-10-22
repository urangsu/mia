MIA TEXT BRING-IN / SUPT 방식 오프라인 소스 복원
작성 2026-10-23 KST

이 디렉터리의 TXT 파트는 단순한 설명서가 아니라 실제 소스 파일 데이터를 포함합니다.
GitHub ZIP(codeload.github.com) 및 git pull이 차단된 회사 PC용입니다.
안내 TXT를 Invoke-Expression으로 실행하지 마세요.

본 프로그램 Collector
  https://github.com/urangsu/mia/tree/main/bring_in
  MIA_COLLECTOR_PART_01.txt ~ MIA_COLLECTOR_PART_11.txt (11개 모두 필요)
  복원 기준 commit: 8b0fc14781f33b44e0c1e5a0b446dfe53000c0a3
  소스 파일 106개, GUI/테스트/문서/requirements 포함.
  이 번들은 2026-10-23 기준 해당 스냅샷이며 GitHub main의 이후 변경은 자동 반영되지 않습니다.
  코드가 바뀌면 TXT 번들도 새 버전으로 재생성해야 합니다.

DOM Inspector V4
  MIA_DOM_PART_01.txt, MIA_DOM_PART_02.txt (대화의 V4 ZIP에서 생성된 두 개)
  원본 ZIP SHA256: 66d97db7a663d514f31fbdbef5c6f62913d5c8b3feff1b4f48a0a9b1da525888
  DOM 번들 파일이 GitHub에 없으면 대화의 MIA_DOM_TEXT_BUNDLE_V4.zip을 내려받으세요.
  ZIP 안의 2개 TXT를 같은 폴더에 풀어 넣으세요.

복원 실행
  RESTORE_MIA_FROM_TXT.py, RESTORE_MIA_FROM_TXT.cmd,
  MIA_COLLECTOR_PART_01.txt ~ 11.txt 와 MIA_DOM_PART_01.txt ~ 02.txt
  파일들을 한 폴더에 배치합니다.
  RESTORE_MIA_FROM_TXT.cmd 더블클릭 (Python 3 설치 시)
  또는 PowerShell에서:
    py -3 .\RESTORE_MIA_FROM_TXT.py --verify-only
    py -3 .\RESTORE_MIA_FROM_TXT.py
  한 종류만 복원할 때:
    py -3 .\RESTORE_MIA_FROM_TXT.py --project collector
    py -3 .\RESTORE_MIA_FROM_TXT.py --project dom

복원 폴더 기본값
  %LOCALAPPDATA%\MIA_Text_Restored\MIA_Collector_<commit>
  %LOCALAPPDATA%\MIA_Text_Restored\MIA_DOM_V4_<bundleid>

실행 전 주의
  - TXT 전체를 다운로드하세요. GitHub 화면의 미리보기 복사/붙여넣기 불가.
  - 모든 파트는 동일 기준 버전이어야 합니다. 누락·손상 시 복원 거부.
  - 기존 Collector/DOM, SQLite/Excel/ECM/예약작업/Chrome 설정 무변경.
  - Collector Python 라이브러리와 사내 사이트 인수는 별도입니다.
  - DOM은 chrome://extensions에서 복원 폴더를 수동 로드합니다.
  - 기업 보안정책상 허용된 파일전달 및 확장 설치 방법만 사용하세요.
