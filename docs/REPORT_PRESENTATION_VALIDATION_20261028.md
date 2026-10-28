# HTML 보고서 표시 개선 / 2026-10-28

## 추가 수정: 수치 바로 옆 단위

후속 사용자 요청으로 단위 위치 정책을 변경했다. 아래 초기 검증의
품목 부제/제목 단위 설명보다 이 항목과 현재 DESIGN.md가 우선한다.
가격·종가·비교값·절대등락 각각에 단위를 붙인다: `13.7 $/kg`,
`838.3 원/100엔`, `+168.87 pt`, `+0.7 bp`, `14,133,379 억원`.
등락률은 `+3.1%`, 누락은 단위 없이 `—`. % payable의 의미도 보존한다.
단위 변환 계산은 하지 않으며 금리의 기존 bp 표시 계산만 유지한다.
원자료 정밀도와 DB/Excel/PPTX는 그대로다.

단위 누락 실패1/error1을 재현한 뒤 수정했다. 추가 단위 테스트3개를 포함해
전체427개(7.693초), report presentation15개 통과. localhost 실제 브라우저에서
금속/FX/지수/시총의 표시와 하단 접힘 상태를 확인했다. 회사 실환경 인수는 아니다.

## 변경 범위

HTML만 변경. 수집, DB, 누적 Excel/ECM, 기존 PPTX 출력과 JSON snapshot은
유지한다. 기존 HTML도 덮어쓰지 않고 새 프로그램에서 보고서를 다시 생성해야
새 표시가 적용된다. 원격 push/main 병합은 이번 작업에서 수행하지 않는다.

## 원인과 수정

- exporter가 context의 모든 내부 열을 그대로 렌더했다. 별도 순수 projection으로
  이름/수치/등락만 표시하고 출처는 이름 링크로 이동했다.
- 시총 raw 테이블에 과거 일별 주가 이력이 포함되어 반복되었다. HTML 시총은
  보고용 비교 표 한 개만 사용하거나 최신 수집일의 시총 있는 행만 사용한다.
  보고용 보류값을 raw cache로 채우지 않으며 같은 시각 충돌은 빈값으로 남긴다.
- 과거 정책이 상단 오류 표시 및 인쇄 시 모든 details 강제 펼침이었다.
  사용자의 새 정책에 따라 모든 경고는 하단 기본 접힘으로 이동했다.
- %는 표시만 한 자리, % 기호/부호/적청 의미를 통일했다. % 값에100배를
  재적용하지 않는다. 금리 변동은 단위 혼동을 막도록 bp로 표시한다.
- 밝게 기본, 맨 위 다크 전환, 선택 저장. localStorage가 막혀도 밝게 동작.
- 날짜가 다른 금속/비교일은 별도 표, 시총 수집시각은 표 위 한 번 표시.
  주가 원/시총 억원은 제목, JPY100 및 금속 USD 단위는 품목 부제로 보존.

## 재현·테스트

최초 신규 테스트 7개는 기존 구현에서 실패5/error2. 이후 링크 fallback과
보류값 보호 재현2개, 금리 bp 단위 재현1개의 실패를 확인한 뒤 수정했다.

실행 Python: 3.14.3 (macOS 전용 개발 venv).

```sh
python -m unittest test_report_presentation test_metals_report test_v37_reports -q
python -m unittest discover -s . -p 'test*.py' -q
python -W error::ResourceWarning -m unittest discover -s . -p 'test_v37*.py' -q
python -m py_compile report_presentation.py report_exports.py
python benchmark_v37.py --runs 10
```

이번 실행: focused27개, 전체424개(7.657초), strict92개(0.464초) 통과.
전체 suite의 argparse 오류 출력은 잘못된 CLI 인수 거부를 검증하는 정상 사례다.
변경 파일 구문 검사 및 git diff --check 통과.

합성 HTML 생성10회: 평균6.40ms, nearest-rank P95/최악15.61ms, 실패0.
기존 CPU 블록 benchmark10회: 평균1.160ms, P95/최악1.401ms, 실패0.
네트워크/실제 COM/회사 수집 성능 측정은 아니다. 30% 개선을 주장하지 않는다.

## Computer Use

localhost 합성 HTML을 실제 인앱 브라우저로 열어 다음을 확인했다.

- 밝게→다크→밝게, 버튼 상태/라벨, 새로고침 시 선택 유지.
- 자료 상태 기본 닫힘, 펼치면 전체 경고/원자료 표시, 다시 접으면 제거.
- 1280/390/320px에서 페이지 폭 넘침 없음. 좁은 비교표만 지역 스크롤 허용.
- 이름 링크의 실제 href, javascript URL 비활성화, 같은 이름 반복 이력 비노출.
- 일반 화면과 전체 페이지 스크린샷 시각 확인. 인쇄 CSS는 정적 검사이며
  회사 Edge 인쇄/PDF 실제 확인은 남아 있다.

## oh-my-design 적용 검토

공식 프로젝트 후보 중 kwakseongjae/oh-my-design의
omd-designer-review / omd-final-qa 두 스킬을 커밋
c71ca8d8a530fde51c7b03967fdaf45dceedb254에 고정해 등록했다.
프로젝트 전체 hooks/CLI는 설치하지 않았다. 다음 턴부터 자동 발견 가능하다.
원본 사용자 DESIGN.md와 승인된 밝은 파생 DESIGN.md를 읽고 수동 적용했다.

디자이너8축: typography/semantic color/radius/component states/반응형/
spacing/측정 대비/overlay를 검사했다. 전체 경고를 히어로에 두지 않고,
숫자 정렬·접힘·의미색을 사용하도록 보고서 스킬 원칙을 반영했다.

실제 렌더의 평면 배경 대비 측정(눈대중 아님):

| Theme | 본문 | 메타 | 상승 | 하락 | 링크/focus |
|---|---:|---:|---:|---:|---:|
| Light |16.56|5.93|5.94|6.01|7.05 /6.01|
| Dark |16.53|8.23|7.37|8.71|10.71 /10.71|

모든 본문 foreground/base 대비4.5:1 이상. hover/모든 OS 글꼴/원천 사이트의
접근성을 전역 인증했다는 의미는 아니다. 모바일 표의 지역 가로 스크롤은
데이터 열 보존을 위한 의도적 예외다.

2차 검토에서 base/panel/hover 전 조합을 추가 측정했다. 밝게 최소5.37:1,
다크 최소6.30:1. Keyboard Tab으로 테마 버튼에서 목차 링크 이동을 확인했다.
omd-final-qa의 미측정 배경 경고를 해소했다. 모든 OS/원천 사이트/회사 보안
환경까지 검증한 것으로 확대하지 않는다.

## 남은 검증과 사용법

반입 TXT는 회사 경로 vsc/매크로에 복원 PY와 같이 두어도 된다. 기존 업데이트
폴더가 있으면 덮어쓰지 않으므로 원본 보존 후 다른 빈 경로를 --output으로
지정한다. 복원한 새 버전에서 보고서 다시 만들기/출력만 재실행한다.
기존 데이터는 사본으로 연결하고 실제 종가/시총 두 날짜를 화면과 대조한다.

실제 회사 Windows/DRM Excel/ECM 서버 검증, 로그인 상태의 FMB 링크 도착,
외부 링크 전체 HTTP200 검증, PPTX/Excel의 동일 시각 디자인 변경은 수행하지
않았다. 실제 가격 오류를 이번 표시 개선으로 해결했다고 주장하지 않는다.
