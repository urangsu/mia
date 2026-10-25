# 금속 중심 대시보드 · 수집 복구 실행 계획

**Goal:** 10월23일 승인 설계의 P0와 금속 탐색을 구현하고, 수집 실패/미지원/빈 데이터가 구별되는 실행 결과를 제공한다.
**Architecture:** main 13c19a7에 기존 검증된 FDR 브랜치를 통합한다. DB 변경 없이 동일 ReportContext에서 검증된 금속 시계열을 읽는다. Qt는 메모리 필터/그리기만 수행하며 HTTP·COM은 기존 단일 worker를 유지한다.
**Tech Stack:** Python/PySide6 QPainter, SQLite, 기존 Jinja/PPTX/FDR. 신규 대형 의존성 없음.

사용자가 지정한 CODEX_MARKET_DASHBOARD_GROUPS_NAVER_LME_20261023.md 및 후속 실행 요청을 설계 승인으로 사용한다. 화려한 전면 재작성보다 기존 기능 보존·실패 재현·근거 없는 가격 차단을 우선한다. 회사 실패 로그는 아직 없음: main의 FDR 미포함은 확인했으나 사용자 수집 실패의 원인과 동일하다고 단정하지 않는다.

1. [x] 최신 main/이력/복원 TXT 메타 대조. FDR 미통합과 오래된 번들 확인. 통합 기준선 292개 재실행.
2. [ ] `test_metal_dashboard.py`를 먼저 작성: 품명 불명, 리튬/니켈/블랙매스, 단위·뷰 분리, 충돌/결측 유지. `series_mapping.py`·`metal_dashboard.py`·`report_model.py` 연결. DB 원본/가격열 키는 변경하지 않는다.
3. [ ] `test_metals_ui.py`: 그룹/기간/hover/빈값/자료 기준 기본 접힘. `desktop_metals.py`·`desktop_ui.py`·`desktop_controller.py` 연결. 주가·ECM 기존 화면 유지.
4. [ ] `test_public_recovery.py`: 공개 전용 GUI→pipeline에 FMB/FX/NAVER false 전달, 원본 설정 불변, 단계 오류 표시 검증. 미지원 KR10Y를 전체 수집 실패로 오해하지 않도록 개별 상태 노출.
5. [ ] HTML 하단 details 기본 접힘·인쇄 펼침·상단 중요 경고 유지. Excel/PPTX 숫자/품목/원본코드 동일 스냅샷 회귀.
6. [ ] 공식 IEA/USGS/INSG/LME/전문기관 링크 및 미국 재무부/ECOS/FRED/국내 지수 API 대안 조사. `docs/METAL_REPORT_LINKS_PLAN_20261025.md`에 링크 메타·새 발행물 판단·중복/개정/장애 정책·수용 기준 기록. PDF/본문/메일/유료 API 도입 없음.
7. [ ] 전체/엄격/Qt 테스트, 새 임시 폴더 공개 실조회, 실제 Qt screenshot과 출력 read-back. 회사 Windows/9444/ECM 미검증은 별도 보고.
8. [ ] 커밋된 HEAD에서 결정적 소스 ZIP과 단일 TXT+복원 실행기를 생성·재복원·회귀. 오래된 번들 사용을 명확히 막고 변경 브랜치 push/PR 제출. main 자동 병합 없음.

검증 명령: `QT_QPA_PLATFORM=offscreen python -m unittest discover -s . -p 'test*.py' -q`, `python -W error::ResourceWarning -m unittest discover -s . -p 'test_v37*.py' -q`, `python -m pip check`. 새 검증 보고서에 실제 출력/종료코드를 기록한다. 실제 가격·브라우저 DOM·로그는 공개 Git에 추가하지 않는다.
