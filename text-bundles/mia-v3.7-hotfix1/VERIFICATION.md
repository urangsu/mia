# 텍스트 전달 검증

2026-10-20 KST. Linux / Python 3.12.14. 이 검증은 전달 형식 검증이며 회사 보안 반입 승인이나 Windows/ECM 인수 결과가 아닙니다.

- 원본 수정 ZIP의 파일 153개를 JSONL 텍스트 조각 5개로 생성.
- 제공 복원기로 새 폴더에 복원한 모든 파일이 원본 ZIP의 파일 내용과 바이트 단위로 일치.
- 반복 복원 시 동일 파일을 변경하지 않음.
- 마지막 조각 누락, 조각 변조, 체크섬 파일 누락, 조각 중복, 개별 파일 해시 불일치에서 비정상 종료하며 출력 폴더를 만들지 않음.
- UTF-8 BOM과 Windows CRLF로 텍스트 조각/체크섬 파일을 저장한 경우도 원본 파일 바이트로 복원.
- 기존 내용이 다른 출력 폴더를 덮어쓰지 않고 사용자 파일을 보존.
- `../`, 절대 경로, Windows 드라이브 경로, 중간 부모 디렉터리 탈출 경로를 기록에 넣어 외곽 체크섬을 다시 계산한 경우에도 파일 기록 단계 전에 차단.

실행:

```text
python3 text-bundles/mia-v3.7-hotfix1/restore_mia_text_bundle.py --out /workspace/mia-delivery/text-restored-check
```

종료코드 0, 153개 파일 복원/검증.

복원 폴더에 기존 설치 의존성의 `.venv`를 연결한 후 실행:

```text
LOCALAPPDATA=/tmp/mia-review-appdata bash scripts/codex_check.sh
```

종료코드 0. 전체 215개 테스트 통과, v3.7 전용 ResourceWarning 엄격 검사 92개 통과, Python 59개 파일 컴파일 통과, 합성 CPU 벤치마크 10회 완료. 테스트 두 묶음은 중복되므로 합산하지 않습니다. `.venv`는 텍스트 묶음에 포함되지 않습니다.

Fastmarkets 실제 DOM, 회사 Windows, 보안 Excel COM/DRM, ECM 서버 반영, 실제 예약 기동은 별도 인수가 필요합니다. 부분 가격 정정 시 이전 Mid/새 범위 혼합 문제는 이번 hotfix1에서 미수정입니다.
