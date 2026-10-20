# MIA v3.7 hotfix1 · 텍스트로 가져오기

필요한 파일은 **2개**입니다. 소스 텍스트를 **한 파일로 통합**했고, 체크섬은 복원기에 내장했습니다. 프로젝트 파일명과 내부 형식 이름도 모두 MIA로 맞췄습니다.

| 저장할 파일 | 용도 |
|---|---|
| [MIA_TEXT_BUNDLE.txt](MIA_TEXT_BUNDLE.txt) | 수정본 전체를 담은 소스 텍스트 1개 (약 1.3MB) |
| [restore_mia_text_bundle.py](restore_mia_text_bundle.py) | 체크섬 검증 및 파일 복원 |

## 가져오는 방법

1. 위 두 파일을 같은 폴더에 저장합니다. 다운로드 대신 **Raw 화면의 내용 전체를 복사해 UTF-8로 저장**해도 됩니다. 파일이 커서 GitHub 미리보기가 생략되면 Raw 화면을 사용하세요. 웹페이지 전체나 줄 번호는 포함하지 않습니다.
2. 그 폴더에서 명령 프롬프트를 열어 실행합니다.

```bat
py restore_mia_text_bundle.py
```

현재 작업 폴더 아래 `mia-v3.7-hotfix1` 폴더가 생성됩니다. 다른 위치는 아직 없는 새 폴더로 지정합니다.

```bat
py restore_mia_text_bundle.py --out C:\FM_Test\mia-v3.7-hotfix1
```

성공하면 `Verified and restored 153 files`가 표시됩니다. 기존 분할 파일이나 별도 체크섬 파일은 필요하지 않습니다. 이번 단일 파일용 복원기를 함께 사용하세요.

## 복원 후 실행

```bat
cd mia-v3.7-hotfix1
py -m pip install -r requirements.txt
RUN_GUI.cmd
```

Python 3.10 이상이 필요합니다. 복원 자체에는 인터넷·추가 패키지·관리자 권한이 필요하지 않습니다. 실행용 의존성 설치는 별도이며 회사 승인 설치 경로를 사용하세요. 이 텍스트에는 Python/EXE/Windows 오프라인 설치 패키지가 포함되지 않습니다.

복원기는 내장된 SHA-256, 묶음 헤더, 개별 파일의 크기·해시와 파일 수를 모두 검사합니다. 검증된 파일을 임시 폴더에 기록하고 다시 읽어 확인한 뒤 출력 폴더로 옮깁니다. 내용이 다른 기존 출력 폴더는 덮어쓰지 않으며, 동일하게 복원된 폴더는 변경하지 않습니다. UTF-8 BOM과 CRLF 변환을 지원합니다. 복원 후 프로그램을 자동 실행하지 않습니다.

## 내용과 검증 범위

- 원본 수정 ZIP의 153개 파일을 빠짐없이 포함하며, 복원한 파일 내용은 ZIP과 바이트 단위로 일치합니다. ZIP 파일 자체를 재생성하는 방식은 아닙니다.
- 수정: 첫 금속 수집의 DB 초기 조회, 충돌 보류값의 Excel/ECM 반영·열 매핑 유지, 오류 후 GUI 로그/상태 갱신.
- 실제 회사 Windows·구독 DOM·보안 Excel·ECM 서버 인수는 별도입니다. 기존 데이터·Excel은 사본으로 먼저 검증하세요.
- **부분 가격 정정 시 이전 Mid와 새 범위가 섞이는 별도 문제는 아직 미수정**입니다.
- 복원 후 `START_HERE_KO.txt`, `FIXES_V37_HOTFIX1.md`, `delivery_evidence/RESULTS.txt`를 확인하세요.

기준 소스: `376314334e1c82d7d41af908f8a8e1de2e7cd6e7`.
전달 브랜치: `delivery/mia-v3.7-hotfix1-text`. `main`은 변경하지 않았습니다.
