MIA / SUPT TEXT BRING-IN - 실제 소스 TXT 복원 (2026-10-23)

이 폴더의 TXT는 설명서가 아니라 Base64 인코딩된 실제 소스입니다. Python 3로 무결성 검증 후 오프라인 복원 가능합니다.
기존 git pull / GitHub ZIP(codeload) 경로를 쓸 수 없는 회사 PC에서 활용할 수 있습니다.

[본 프로그램 Collector]
MIA_COLLECTOR_PART_01.txt ~ MIA_COLLECTOR_PART_11.txt : 모두 필요, 소스 106개
기준 소스 커밋: 8b0fc14781f33b44e0c1e5a0b446dfe53000c0a3
해당 커밋의 파일 내용/원본 blob SHA1/크기를 확인하여 게시한 완전한 스냅샷입니다.
이후 main의 새 변경은 자동 포함되지 않습니다. 최신 변경을 반영하려면 TXT 재생성이 필요합니다.

[DOM Inspector V4]
이전 대화에서 만들어 제공한 MIA_TEXT_BRINGIN_DOM_V4_복원키트.zip에
MIA_DOM_PART_01.txt + MIA_DOM_PART_02.txt 와 실행기가 들어있습니다.
원본 MIA_DOM_Inspector_V4_미니패널.zip SHA256:
66d97db7a663d514f31fbdbef5c6f62913d5c8b3feff1b4f48a0a9b1da525888
현재 DOM V4 TXT 2개는 GitHub가 아니라 대화 다운로드 키트에서 제공됩니다.
GitHub에서 Collector 번들을 내려받을 때 함께 별도 폴더에 보관하고, 같은 폴더에서 복원하세요.

[필요한 파일을 한 폴더에 배치]
RESTORE_MIA_FROM_TXT.py
RESTORE_MIA_FROM_TXT.cmd
MIA_COLLECTOR_PART_01.txt ... MIA_COLLECTOR_PART_11.txt
MIA_DOM_PART_01.txt / MIA_DOM_PART_02.txt

[복원 및 확인 - 인터넷 연결 없음]
RESTORE_MIA_FROM_TXT.cmd 더블클릭 또는 PowerShell:
py -3 .\RESTORE_MIA_FROM_TXT.py --verify-only
py -3 .\RESTORE_MIA_FROM_TXT.py
단독:
py -3 .\RESTORE_MIA_FROM_TXT.py --project collector
py -3 .\RESTORE_MIA_FROM_TXT.py --project dom

복원된 파일은 %LOCALAPPDATA%\MIA_Text_Restored\ 아래 별도의 버전별 폴더에 생성됩니다.
기존 소스/설정/SQLite/Excel/ECM/예약/브라우저는 자동 수정하지 않습니다.
검증에 실패하면 저장하지 않으며, 기존 파일을 강제 삭제·덮어쓰기하지 않습니다.
회사 Windows/Python 의존성, Fastmarkets/ECM 연결, DOM 확장 실제 설치 허용 여부는 별도 확인이 필요합니다.

[다운로드 주의]
GitHub 화면의 미리보기 전체 복사가 아니라 파일을 Raw/Download로 완전히 저장하세요.
회사가 GitHub 사이트까지 막으면 다른 승인된 환경에서 다운로드하여 회사 승인된 반입 방식으로 전달해야 합니다.
회사 보안 정책 우회나 계정/회사 DOM 자료 업로드는 하지 않습니다.
