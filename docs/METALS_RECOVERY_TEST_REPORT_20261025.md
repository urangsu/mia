# 금속 중심 복구 · 검증 보고서

2026-10-25 KST. 기준 main `13c19a7`; 작업 브랜치 `codex/metals-dashboard-recovery-20261025`. 사용자 증상은 '수집 실패'이며 실제 회사 오류 로그는 미제공이다. 이 문서는 전체 회사 수집 해결/Windows 배포 승인서가 아니다.

## 확인된 원인 / 변경

| 관측 근거 | 수정 / 남은 경계 |
|---|---|
| main에는 기존 FDR 통합이 없고, 10월23일 화면 문서는 설계뿐. 과거 TXT는 8b0fc147 고정본 | 최신 main에 FDR 브랜치 통합. 새 기능/설정이 과거 설치본에 자동 포함되지 않음을 명시. 새 버전 고정 TXT 빌더·검증 복원기 추가 |
| 수집 pipeline의 단계 상태에는 오류가 빠지고 generic 안내만 표시 | 단계별 error/warnings/missing 전달, GUI에 실제 출처·원인 표시. 공개 전용 버튼은 이번 실행만 출처 변경하며 저장 설정 불변 |
| FDR 전 출처 실패도 partial 반환; 자식 통신이 Windows 기본 인코딩에 의존 | all-failed를 failed로 반환. 소유 자식만 UTF-8 고정/시간 제한·취소 유지. Windows 실기동은 미검증 |
| 금속 보고 첫 열이 MB코드; 그룹·기간·차트 없음 | description 기반 품명/조건·코드 분리. 리튬/니켈/코발트/망간/구리/블랙매스, 단위·mode·view별 독립 차트. DB/일별 가격열 키 변경 없음 |
| 독립 리뷰에서 빈 뷰가 공통 일별값을 상속하는 문제 재현 | 검증된 공통값은 veto만 적용하고 해당 raw Mid와 일치할 때만 표시. 결측을 다른 뷰로 채우지 않음 |
| 전체 이력 좌표 계산 O(n²), 작은 창에서 chart/table 겹침 재현 | ordinal/bounds 캐시, hover bisect; 작은 창 내부 스크롤. 독립 재검증: 3,650 좌표 2.028초→0.0055초, hover 10,000회0.025초, 예열 전체 paint약0.039초 |
| 실제 주가 등락률의 16자리 float가 XLSX에서 끝자리 달라짐 | 기존 지수와 동일한 소수6자리 **보고 표시** 계약. 원본 Decimal 문자열/가격은 유지. 실제 파일 재대조 |
| 자료 기준/경고가 길고 금속 PPT 조건 열이 좁음 | Qt/HTML 자료 기준 하단 기본 접힘, 중요한 실패/충돌은 상단 유지. PPT 금속 페이지3행·넓은 조건 열/행 높이; 모든 셀 native/editable 유지 |

## 오프라인 / 모의 / UI

환경 macOS arm64, Python3.14.3, PySide6 offscreen. 네트워크/COM 경계만 필요한 곳에서 주입하고 실제 Qt·SQLite·pandas·exchange_calendars·openpyxl·python-pptx를 실행했다.

```text
QT_QPA_PLATFORM=offscreen python -m unittest discover -s . -p 'test*.py' -q
python -W error::ResourceWarning -m unittest discover -s . -p 'test_v37*.py' -q
python -m pip check
```

- 통합 기준선292개 → 현재 전체314개 통과, 11.718초, exit0.
- 기존 v3.7 ResourceWarning 엄격 검사92개 통과, 1.010초, exit0. 전체 회귀에는 과거 SQLite 테스트의 ResourceWarning이 남는다. 무경고 전체 검사라고 주장하지 않는다.
- 루트 Python 및 신규 빌더/복원기87개 컴파일 성공, 의존성 검사 성공, git diff --check 통과.
- 실제 Qt 위젯 생성·그룹/기간/표/차트·기본 접힘·공개 버튼·1060×760 겹침 방지·취소/종료 스레드 계약 검증. 합성 가격임을 표시한 1440×1040 스크린샷을 직접 확인했다. 이를 실제 회사 가격 화면이라고 표현하지 않는다.
- 독립 읽기 전용 코드 리뷰의 Important2건을 실패 테스트로 재현하고 해결/재확인. 복원 경로·해시·기존 폴더 보호·설정 불변·UTF-8 경계에서 추가 Critical/Important 없음. Windows 전체 승인과 다름.
- 실조회와 테스트를 동시에 수행했을 때 공용 브라우저 잠금 때문에 로그인 모의 테스트2개가 거부됐다. 실조회 종료 후 직렬 전체 회귀 통과. 잠금 보호를 제거하지 않았다.

## 실제 공개 수집 / 저장 파일

사용자 원본·브라우저 없이 새 임시 폴더에서 `--once --public-only` 실행. FDR10.649초, 전체11.009초, 249행 저장. KOSPI/KOSDAQ/SP500/NASDAQ/US10Y/GOLD/WTI/005490 모두 기대 2026-10-23/2026-10-22 두 날짜 확보. KR10Y는 미지원이므로 정상 **partial / exit2**. 금속/SMBS/시총은 이 명령의 수집 대상이 아니다.

같은 폴더 재실행은 8개 대상 모두 캐시, 저장0행, FDR2.408초/전체2.749초. 보고 표시 정밀도 변경으로 기존 Excel 업데이트가 필요해졌으나 비Windows 보존 계약에 따라 기존 파일 덮어쓰기를 거부했다. 새 경로의 출력본을 만들어 검증했다. 이 거부를 COM 갱신 성공이라고 쓰지 않는다.

공통 ReportContext에서 실제 새 Excel·HTML·PPTX를 생성하고 다시 열어143개 표 셀·두 날짜·소스·snapshot을 대조했다. snapshot `ee95f6348fc688214abc3e207f248ca308d572bacb650d751a0b4e6f70e1044d`. XLSX 빈 문자열→None만 정규화; 원본 가격을 테스트 통과 목적으로 바꾸지 않았다. 실제 관측/로그/출력 바이너리는 Git에 올리지 않는다.

## 전달 패키지 인수 게이트

새 단일 TXT/ZIP은 지정된 Git 커밋에서만 생성한다. TXT ZIP SHA-256, manifest SHA-256, 각 소스 SHA-256, 상대경로/중복/심볼릭링크/크기 제한, 기존 폴더 거부를 검사한다. 예전 LZW ONEFILE/PART와 섞으면 형식 오류로 거부한다. 최종 패키지는 코드 커밋 후 재복원·전체 테스트를 다시 실행하고 TXT 헤더 source_commit으로 정확한 범위를 식별한다. 해시는 무결성 검증이며 발행자 인증 서명이 아니다.

실제 복원 검증: 코드 커밋 c4bdc73df82efc46384858c05e3137cbbba8197e에서130개 소스를 패키징하고 새 임시 폴더로 SHA-256 검증 복원. 그 복원본에서 전체314개 테스트 재통과(11.981초, exit0). ZIP SHA-256은0d6e04e0cac60da39e2255bcb1ec6e75d759d8a41ebe7c485e2db990901ff289였다. 최종 전달본은 이 증거 기록과 편의 CMD를 포함해 다시 생성하므로 정확한 최종 커밋/해시는 TXT 헤더를 따른다. Windows CMD 실제 더블클릭은 이 Mac에서 실행하지 않았다.

## 미완료 / 회사 인수

- 실제 회사 '수집 실패' 원인: 마지막 오류/last_diagnostic.json과 diagnose_windows --driver-check가 필요. Chrome9444 로그인·전체 품목 inventory/BM 날짜·실제 NAVER 새 SPA DOM·공식 CSV 대조는 미검증이다.
- LME/SMM/GFEX는 허용 경로/계약/실제 시세 근거가 없어 unsupported. 새 금속 수치를 만들어 넣지 않았다. 품명 분류는 authoritative description의 표시용이며 서로 다른 가격을 공통 제품으로 병합하는 사전이 아니다.
- Windows COM 보안 Excel·ECM 대상/서버 체크인·08:30 실기동·회사 프록시/TLS·Microsoft PowerPoint 렌더·브라우저 인쇄는 미검증.
- HTML 차트/다중 단위 복수 선, 신규 NAVER DOM 전체 어댑터, 상세 파생 환산 계산은 이번 범위에서 구현하지 않았다. Qt 단일 시리즈 일별 탐색부터 제공한다.
- 공식 니켈/리튬 보고서는 링크 전용 구현 계획이다. 자동 새 발행 감시/본문/PDF/AI/메일은 추가하지 않았다. ECOS/공식 국내지수/미 재무부 어댑터도 키·정의·게시 시각 검증 후 별도 구현이 필요하다.

회사 PC에서는 [실행·복구 안내](METALS_RECOVERY_GUIDE_20261025.md)의 새 폴더 설치 → 공개 종가 → FMB 진단 → 원본 사본/사용자 수식 보존 → 예약/ECM 순으로 인수한다. 9222/9337·관리자 Edge·로그인 쿠키/프로필은 변경하지 않았다.
