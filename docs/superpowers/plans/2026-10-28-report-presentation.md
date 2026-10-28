# Report Presentation Implementation Plan

> **For agentic workers:** Inline execution using executing-plans; no delegation.

**Goal:** 승인한 밝은 기본/다크 전환의 간결한 금속 중심 HTML 보고서를 구현한다.

**Architecture:** 불변 ReportContext는 그대로 두고 report_presentation.py가
표시용 행·날짜 그룹·이름 링크만 만든다. 기존 HTML exporter만 이를 사용한다.

**Tech Stack:** Python, Jinja2, self-contained HTML/CSS/JavaScript, unittest.

### Task 1: 재현 테스트

- [ ] test_report_presentation.py에서 합성 ReportContext로 최신 시총만 표시,
  상태 접힘, 한 자리 %, 날짜 그룹, 링크 안전성, 원자료 불변을 검증한다.
- [ ] `python -m unittest test_report_presentation -v`를 실행해 현재 결함으로 실패 확인.

### Task 2: 순수 표시 projection

- [ ] report_presentation.py에 `presentation_tables(context)`를 구현한다.
  입력 행을 dict(zip(headers,row))로 읽고 날짜/단위별 새 표를 반환한다.
  시총 원본은 market_cap이 있는 최신 수집일의 종목당 최신 행만 선택한다.
  동일시각 충돌값은 하나를 고르지 않고 보류한다.
- [ ] 퍼센트 formatter는 Decimal quantize(0.1), 이미 %인 값에 100을 곱하지 않는다.
- [ ] 링크는 HTTP(S), hostname 필수, userinfo 금지, 나머지는 링크 없는 이름.

### Task 3: HTML 표시

- [ ] report_exports.export_html에서 projection을 사용하고 raw tables는 audit로 넘긴다.
- [ ] report_template.html에 밝은 토큰과 data-theme=dark 토큰, theme-toggle 버튼,
  localStorage 실패도 허용하는 전환 script를 추가한다.
- [ ] 모든 경고와 원자료는 마지막 source-basis details로 이동한다.
  print에서 닫힌 details를 강제로 펼치는 CSS를 제거한다.
- [ ] 이전 top-warning 테스트를 새 사용자 정책의 기대값으로 바꾼다.
  기존 script 금지 검사는 외부/주입 script 금지 검사로 구체화한다.

### Task 4: 검증과 인수

- [ ] targeted와 전체 `python -m unittest discover -p 'test*.py' -q` 실행.
- [ ] 합성 HTML을 localhost로 열고 밝게/다크, 접기/펼치기, 이름 링크,
  desktop/mobile을 Computer Use로 확인한다.
- [ ] oh-my-design의 DESIGN.md 대비 검토를 기록하고 미검증 범위를 명시한다.
- [ ] 소스와 검증 문서를 로컬 reviewable commits로 저장한다. 원격 push는 별도 요청 시.
