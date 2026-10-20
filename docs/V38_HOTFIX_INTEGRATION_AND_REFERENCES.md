# MIA v3.8 통합 보완·공개 레퍼런스 검토 (2026-10-20)

## 상태 및 운영 주의

- 대상: `codex/lme-conversion-daily-report-20261020`. `main`, DELIVERY 브랜치는 변경하지 않았다.
- PDF/ZIP 채팅 전달이 차단된 회사 환경을 고려해 **GitHub 소스·Markdown을 배포 원본**으로 사용한다. 필요 시 승인된 별도 기기에서 GitHub 브랜치를 ZIP으로 내려받고 사내 승인 경로로 전달한다.
- Windows 기업 DRM/Excel COM/ECM 저장은 현장 검증 전이다. **GitHub CI 성공을 실제 회사 Windows 성공이라고 주장하지 않는다.**

## hotfix1과 미해결 오류 4건의 통합

| 위험 | 기존 문제 | 반영 방식 | 시험 근거 |
|---|---|---|---|
| P0 새 폴더 첫 실행 | v3.7 런 이력 DB만 있고 instruments가 없는 경우 첫 수집 전 조회 실패 | instruments 유무 확인 후 첫 수집 이어가기; 다른 스키마 이상은 예외 유지 | `test_v37_recovery.py` |
| P0 충돌 가격 잔존 | DB에서 보류되더라도 옛 Excel·ECM 가격이 남음 | `보류셀` 명시목록 / 가격열설정 키·열 위치 보존 / 수식 보호 / 월평균·건수 정합성 | `test_v37_recovery.py` |
| P0 GUI 대기·오류 | fx=None 및 예외 시 pump 재예약 중단 | 완료·실패·부분완료 표기 / try…finally의 `root.after` 보장 / LME 상태 포함 | `test_v37_recovery.py` |
| P1 가격 일부 정정 | 기존 Low/Mid/High와 새 일부 값의 잘못된 혼합 | 가격 범위를 원자적 관측 묶음으로 저장(새 부분 관측만 남기고 이전 측정값을 조용히 재사용하지 않음) / 변경 감사 `price_revisions` | `test_v38_partial_revision.py` |
| P1 미고시와 공식 철회 혼동 | Mid 없는 모든 신규 날짜를 이전 가격 철회로 오인 가능 | **기존 Mid → NULL 정정 이력이 명시된 날짜·키만** 로컬 Excel·ECM에서 비우고, 신규 미고시는 빈 날짜 생성 안 함 | `test_v38_partial_revision.py` |
| P1 레거시 잘못된 범위 | 저장된 과거 Low > Mid, 또는 Mid > High | 보고시 원본 범위 충돌 감지 및 셀 자동 반영 보류 | `test_v38_partial_revision.py` |
| P1 단위 차이 | Co 본래 `$/lb`, LC/LiOH `$/kg`, Tonne 변환 위젯 중복 | 원본 DB/Raw 불변, 보고용 `USD/tonne`, 코발트 변환 뷰와 원본 값 일치 검증 | `test_v38_lme_report.py` |
| P1 LME·보고 | LME Ni/Cu 시세와 재고 누적 및 5일·월별표 부재 | Westmetall 공개 HTML 날짜/항목 검증, SQLite idempotent UPSERT 및 정정 감사, 새 보고 시트 | `test_v38_lme_report.py` |

### 단위 변경의 정책

- `MB-CO-0005`의 실제 수집 숫자 **22.50 USD/lb**, 보고값 **49,604.01 USD/tonne**.
- `MB-LI-0029` / `MB-LI-0033`의 실제 수집 `USD/kg`는 보고에만 `×1,000`.
- 퍼센트 Payable, LME 재고(tonne), FX KRW/통화는 자동 금액 환산 대상 **아님**.
- 두 Co 위젯 모두 헤더 `MB-CO-0005`, `$/lb`가 같을 수 있다. 어느 것이 원본인지 가격 및 추적 정보를 교차 확인하고 값이 불일치하면 **임의 선택 금지**.
- **향후 개선:** 화면의 `Tonne` 전환 상태를 명시적인 `display_unit` 메타데이터로 수집해 가격 크기만을 근거로 한 판별을 교체해야 한다. 현재는 숫자 범위 검증이 안전장치이며 DOM 실환경 확인 전 완성으로 간주하지 않는다.

### 부분 정정 저장 정책

기존 `COALESCE(excluded.mid, prices.mid)` 방식은 새 Low=30 / High=40을 저장하면서 이전 Mid=15를 남기는 불가능한 상태를 만든다. 수정 후 `low,mid,high,change_pct`는 **같은 가격 관측 세트**로 취급한다.

- 정정 들어온 셀만 존재하고 일부 필드가 빠졌다면 이전 미관측 값을 인위적으로 섞지 않는다.
- 이전 Mid가 있던 고시일이 `Mid=NULL`로 정정되면 `price_revisions`의 `old_values/new_values`로 철회 사실 확인 후 **보류셀**을 생성한다.
- 아예 가격이 처음부터 없던 고시일은 이전 값을 비우는 명령이 아니다.
- 새로운 정상 Mid가 다시 수집되면 기존 키·열로 복구한다.
- **현장 필수 검증:** DOM 가로 스크롤 가상화로 숨겨진 값이 `None`으로 잘못 저장되는지 확인한다. `None`이 실제 미고시인지 단순 수집 미완료인지 불명확하면 정정 저장 전에 중단하는 제어가 추가로 필요하다.

## 비슷한 공개 GitHub 저장소와 반영 아이디어

소스/문서 참조로 한정한다. 임의 복제 또는 DRM/구독/인증 우회 없음. 신규 외부 의존성은 회사 승인 없이 강제 설치하지 않는다.

| 추천 저장소 | 참고할 지점 | MIA 적용/다음 검토 |
|---|---|---|
| [ag-grid/ag-grid](https://github.com/ag-grid/ag-grid) | Angular AG Grid의 행/열 가상화와 테스트 구조 | 표시 DOM의 `row-index`/`col-id` 기반 매핑, 스크롤 전후 가시행 검증. **컴포넌트 내부/비공개 API 접근 아님.** |
| [seleniumbase/seleniumbase](https://github.com/seleniumbase/seleniumbase) | Selenium 동작과 UI 회귀의 테스트 구조, 명확한 대기·진단 | 가상표 지연 로딩/스크롤/종목 매핑의 합성 DOM 테스트 보강; 봇탐지 우회·stealth 기능은 사용하지 않음 |
| [xlwings/xlwings](https://github.com/xlwings/xlwings) | 데스크톱 Excel용 워크북·Range 조작 및 배치 읽기/쓰기 패턴 | 직접 `pywin32` COM을 유지하고 블록 단위 업데이트·수식/서식 보존을 더 검증. xlwings PRO 유료 기능은 선택하지 않음 |
| [pywinauto/pywinauto](https://github.com/pywinauto/pywinauto) | UIA/Win32 컨트롤 ID, 텍스트 기반 윈도우 식별 | ECM 일반 Edge + 데스크톱 Excel의 실제 HWND/FullName 신원 검증을 강화. 좌표만 믿고 Ctrl+S 하지 않음 |
| [agronholm/apscheduler](https://github.com/agronholm/apscheduler) | 영속 작업, `max_instances`와 늦은 실행 시 정책 | 기존 Windows 작업스케줄러는 보존하며 동시 실행 차단·실패 재시도/실행 이력을 확인 |
| [hgrecco/pint](https://github.com/hgrecco/pint) | 물리 단위의 타입 검사 및 변환 | `USD/lb` → `USD/tonne`, `USD/kg`, `%` Payable 등을 분리한 테스트와 단위표; 설치 의존성 추가는 보류 |
| [trenton3983/Excel_Automation_with_Python](https://github.com/trenton3983/Excel_Automation_with_Python) | Microsoft Excel `win32com` 직접 제어 예제 | 기존 `endp.py` 방식과 비교해 계산·서식 처리 COM 호출 수 최소화 |

### 외부 저장소를 직접 가져와 복제하지 않은 이유

1. MIA는 회사 허가된 **Chrome 9444 / 구독 사이트 표시 DOM**, 승인된 Excel COM과 ECM UIA만 사용한다.
2. 확장 프레임워크 전체 설치는 패키지 크기·사내 승인·운영 표면을 넓힐 수 있다.
3. 라이선스를 확인하지 않고 타 저장소의 코드·수집 스크립트를 붙여넣지 않는다.
4. **도입할 것은 설계 원칙과 검증 패턴**이며, 새 구현은 MIA 기존 인터페이스에 맞춰 자체 작성한다.

## 사용 및 검증

```powershell
py -m unittest discover -s . -p "test*.py" -v
py -u .\FastmarketsCollector_v3_7.py --export-only
py -u .\FastmarketsCollector_v3_7.py
```

`--export-only`는 현재 DB만으로 일별요약/일별시세/월평균/보고서 재생성한다. 외부 사이트를 다시 수집할 필요가 없다. 회사 DB·Excel 원본의 사본을 지정하고 작업한다.

GitHub Actions (PR의 최신 작업): https://github.com/urangsu/mia/actions/workflows/market-regression.yml

## 미검증·후속 P0

1. 9444 작업공간의 BM 위젯 실제 DOM 수집 완전성, 가상 그리드 날짜 열 매핑.
2. 사이트 로딩/인증 지연, 새 로그인 30초 한계는 계정/네트워크 상황에 따라 달라짐.
3. Westmetall 실제 HTML과 회사 인터넷 프록시/robots/약관 호환.
4. 회사 DRM Excel의 `Workbook.Save` 및 ECM 체크인·서버 반영.
5. 성능 벤치마크는 동일 Windows 프로필에서 10회 warm 실행, 수집/DB/COM/ECM 단계별 비교.
6. 숫자 휴리스틱 기반 변환뷰 구분을 명시적인 **표시 단위·전환 버튼 상태** 추적으로 교체할 필요가 있음.

**GitHub CI 통과 ≠ 현장 운영 승인.** 업무 원본에는 검증·백업 전 적용하지 않는다.
