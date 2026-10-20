# mia v3.7 hotfix1 · 텍스트로 가져오기

첨부한 PGPT 예시와 같은 `pgpt_text_bringin_v1` 형식입니다. 수정 ZIP의 **153개 파일 전체**를 텍스트 조각 5개에 담았습니다. ZIP/Base64 암호화 파일이 아니라 파일 경로·원문·SHA-256이 기록된 JSON 텍스트입니다. 회사에서 허용된 소스 전달 절차 안에서 사용하세요.

기준 소스: `376314334e1c82d7d41af908f8a8e1de2e7cd6e7`.
전달 브랜치: `delivery/mia-v3.7-hotfix1-text` (`main`은 변경하지 않음).

## 가져올 파일: 총 7개

아래 파일을 **같은 폴더**에 저장하세요. GitHub의 Raw 화면에서 내용을 복사해 UTF-8 텍스트로 저장해도 됩니다. 웹페이지 전체/줄 번호는 포함하지 마세요. 파일 확장명이 `.txt.txt`나 `.py.txt`로 바뀌지 않았는지 확인하세요. BOM과 CRLF 변환은 허용합니다.

| 파일 | 용도 |
|---|---|
| [restore_mia_text_bundle.py](restore_mia_text_bundle.py) | 이번 수정본용 복원기 |
| [PGPT_TEXT_PARTS.sha256.txt](PGPT_TEXT_PARTS.sha256.txt) | 전체 조각 체크섬 |
| [PGPT_TEXT_PART_01.txt](PGPT_TEXT_PART_01.txt) | 소스 조각 1/5 |
| [PGPT_TEXT_PART_02.txt](PGPT_TEXT_PART_02.txt) | 소스 조각 2/5 |
| [PGPT_TEXT_PART_03.txt](PGPT_TEXT_PART_03.txt) | 소스 조각 3/5 |
| [PGPT_TEXT_PART_04.txt](PGPT_TEXT_PART_04.txt) | 소스 조각 4/5 |
| [PGPT_TEXT_PART_05.txt](PGPT_TEXT_PART_05.txt) | 소스 조각 5/5 |

과거 PGPT 프로젝트 조각과 섞지 마세요. 이번 묶음에는 **06번 파일이 없습니다.** 과거 PGPT 복원기 대신 위 `restore_mia_text_bundle.py`를 사용하세요. 기본 출력 폴더가 mia용이고 검증 실패 때 중단하도록 개선했습니다.

## 회사 Windows에서 복원

Python 3.10 이상이 있으면 됩니다. 복원 자체에는 인터넷, pip 설치, 관리자 권한이 필요하지 않습니다. 7개 파일을 저장한 폴더에서 명령 프롬프트를 열고 실행합니다.

```bat
py restore_mia_text_bundle.py
```

현재 작업 폴더 아래 `mia-v3.7-hotfix1`을 생성합니다. 경로를 지정하려면 **아직 없는 새 폴더**를 사용하세요.

```bat
py restore_mia_text_bundle.py --out C:\FM_Test\mia-v3.7-hotfix1
```

조각/묶음/파일의 SHA-256과 파일 수를 확인한 뒤 임시 폴더에 복원하고, 읽어 검증한 후 출력 폴더로 옮깁니다. 다른 내용의 기존 출력 폴더는 덮어쓰지 않습니다. 동일 내용으로 이미 복원된 경우는 변경 없이 확인만 합니다. 복원기는 프로그램을 실행하거나 의존성을 자동 설치하지 않습니다.

성공하면 `Verified and restored 153 files`가 표시됩니다. 이후 복원 폴더로 이동합니다.

```bat
cd mia-v3.7-hotfix1
py -m pip install -r requirements.txt
RUN_GUI.cmd
```

회사에서 pip 접근도 제한한다면 회사 승인 설치 경로 또는 별도 Windows 오프라인 패키지가 필요합니다. 이 묶음에는 Python/EXE/Windows 설치 패키지는 포함하지 않았습니다.

## 수정 범위와 남은 제한

- 수정: 첫 금속 수집의 DB 초기 조회, 충돌 보류값의 Excel/ECM 반영·열 매핑 유지, 오류 후 GUI 로그/상태 갱신.
- 기존 데이터·Excel은 사본으로 먼저 검증하세요. ECM 비우기도 사람의 미리보기 승인이 필요합니다.
- **부분 가격 정정 시 이전 Mid와 새 범위가 섞이는 별도 문제는 아직 미수정**입니다.
- 실제 회사 Windows·Fastmarkets 구독 DOM·보안 Excel·ECM 서버·예약 기동 인수는 별도입니다.
- 상세 내용은 복원 후 `FIXES_V37_HOTFIX1.md`, `START_HERE_KO.txt`, `delivery_evidence/RESULTS.txt`를 확인하세요.

전달 ZIP SHA-256: `a9294572f048f424f15cf3e7962633c139d3c511f173bed449ee46db5612c12e`.
복원 결과는 이 ZIP에 든 파일 내용과 바이트 단위로 일치합니다. ZIP 파일 자체를 재생성하는 방식은 아닙니다.
