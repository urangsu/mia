# MIA Report Design

## Scope and approved direction

2026-10-28 사용자 승인: 기본 밝게, 최상단 다크 전환 버튼. HTML 보고서는
금속 중심의 숫자·표 문서다. 앱의 기존 다크 UI와 원자료는 변경하지 않는다.
참고: 사용자 제공 Toss Securities DESIGN.md의 숫자 정렬, 절제된 색, 무그림자
표현을 따른다. 아래 밝은 테마는 사용자 요구에 맞춘 프로젝트 고유 변형이다.
브랜드 자산/전용 글꼴/로고는 복제하지 않는다.
2026-11-05 사용자 참고 화면: 네이버 시장지표의 지표 밀도와 나란히 비교하는 표,
토스 WTS의 흰 배경과 간결한 탭, Apple의 조용한 중립색과 명확한 키보드
포커스를 참고한다. 마케팅용 대형 버튼, 유리 효과, 전용 글꼴은 가져오지 않는다.

## Color

| Role | Light | Dark |
|---|---|---|
| canvas | #ffffff | #0b0c10 |
| base | #ffffff | #101013 |
| panel | #f7f7f8 | #17171c |
| line | #e7e8eb | #35353e |
| text | #1a1f29 | #f3eeee |
| muted | #4e5968 | #aaaab2 |
| up | #bc2942 | #ff7588 |
| down | #1763b6 | #79b2ff |
| link | #175aa8 | #9cc5ff |
| focus | #175aa8 | #9cc5ff |
| hover | rgba(13,25,74,.04) | #202025 |

적/청은 한국 금융의 상승/하락 의미로만 사용한다. 부호를 함께 표기한다.
국기와 자산 구분 아이콘만 색상을 쓴다. 인라인 SVG로 포함하며 보조기기에는
장식으로 처리한다. 그림자/사진/외부 이미지 요청 없음.

## Typography

로컬 시스템 글꼴: -apple-system, BlinkMacSystemFont, Apple SD Gothic Neo,
Malgun Gothic, system-ui, sans-serif. 외부 폰트 요청 없음.
H1 32/700 (mobile 28), H2 22/700 (mobile 20), 본문 16/400,
메타·표 머리·표 14/400~500, 금속 이름 14/600, 금속 액션 표시 13/500.
숫자는 tabular-nums, 우측 정렬. 인쇄 표 12px.
H1 한 개. 내부 원자료 제목은 별도 하단 영역에 둔다.

## Spacing and Radius

간격: 0, 4, 8, 12, 16, 24, 32, 40, 48px.
선: 1px, 주요 문서 구분선·focus 2px. Radius: 0, 8px.
본문 최대1220px, desktop 좌우32px, mobile 좌우16px.
데이터 표는 별도 카드 틀 없이 행 구분선으로 구획한다.
페이지는 세로 스크롤, 표의 비교열은 축소하지 않고 표 내부 스크롤로 보존.
의도적인 지역 표 스크롤 외 페이지 가로 넘침은 허용하지 않는다.

## Component states

버튼/링크/summary: default, hover, active, focus-visible.
버튼 최소44px 높이, disabled 스타일 명시. anchor는 비활성 상태를 만들지
않고 주소 미확인 시 plain text로 렌더한다. 이름은 안전한 HTTP(S) 원문 링크,
외부 링크는 target=_blank 및 rel=noopener noreferrer.
금속 카드는 전체 클릭 영역, 잔잔한 hover와 분명한 focus·선택 상태를
제공한다. 카드를 띄우는 모션 없이 `추이 ⌄`와 `원문 ↗`을 구별한다.
이력이 있으면 차트를 펼치며 화살표 키와 포인터로 조회한다.
가로 카드 목록은 좌우 버튼과 기본 스크롤을 지원한다. 축소 모션 설정을 따른다.

## Report hierarchy and meaning

금속 카드 → 환율·채권/금리 → 시장지표 → 주가·시가총액. 종합은 별도 접힘.
환율·금리는 넓은 화면에서 나란히, 좁은 화면에서는 순서대로 배치한다.
자료 상태와 모든 원자료는 맨 마지막 details, 기본 닫힘. 인쇄도 기본 닫힘.
각 표의 실제 날짜/비교일을 제목/머리에서만 표시한다. 혼합일은 별도 표.
단위는 가격·종가·비교값·절대등락 각각의 수치 바로 옆에 표시한다.
HTML 본문: 코발트 USD 질량 단가는 $/kg, 원화 시총은 조원, 주가는 원,
환율은 원/달러·원/100엔, 지수는 pt. %는 한 자리, 금리 변화는 bp.
코발트의 비USD 가격과 Payable 비율, 감사·PPTX·Excel 원자료는 원 단위다.
모델 호출이 명시적으로 설정되어 유효한 요약이 반환된 경우에만 상단에 AI 초안을 둔다.
누락은 —. 수집시총을 확정종가 시총으로 표시하지 않는다.

## Voice

voice_preset: mia-numeric-brief. 짧은 명사형 표 제목과 단위/기준 표기.
임의 시장 해석, 홍보 문구, 장식용 슬로건 없음. 한국어 단일 locale.
