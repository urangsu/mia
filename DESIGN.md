# MIA Report Design

## Scope and approved direction

2026-10-28 사용자 승인: 기본 밝게, 최상단 다크 전환 버튼. HTML 보고서는
금속 중심의 숫자·표 문서다. 앱의 기존 다크 UI와 원자료는 변경하지 않는다.
참고: 사용자 제공 Toss Securities DESIGN.md의 숫자 정렬, 절제된 색, 무그림자
표현을 따른다. 아래 밝은 테마는 사용자 요구에 맞춘 프로젝트 고유 변형이다.
브랜드 자산/전용 글꼴/로고는 복제하지 않는다.

## Color

| Role | Light | Dark |
|---|---|---|
| base | #ffffff | #101013 |
| panel | #f6f7f9 | #17171c |
| line | #e3e6eb | #35353e |
| text | #191f28 | #f3eeee |
| muted | #596575 | #aaaab2 |
| up | #bc2942 | #ff7588 |
| down | #1763b6 | #79b2ff |
| link | #245a96 | #9cc5ff |
| focus | #1763b6 | #9cc5ff |
| hover | #f1f4f8 | #202025 |

적/청은 한국 금융의 상승/하락 의미로만 사용한다. 부호를 함께 표기한다.
채도 높은 장식 요소는 사용하지 않는다. 그림자/사진/외부 이미지 없음.

## Typography

로컬 시스템 글꼴: -apple-system, BlinkMacSystemFont, Apple SD Gothic Neo,
Malgun Gothic, system-ui, sans-serif. 외부 폰트 요청 없음.
H1 32/700 (mobile 28), H2 22/700 (mobile 20), 본문/표 16/400,
메타·표 머리·mobile 표 14/400~500, 품목 링크 500.
숫자는 tabular-nums, 우측 정렬. 모바일 최소 14px, 인쇄 표 12px.
H1 한 개. 내부 원자료 제목은 별도 하단 영역에 둔다.

## Spacing and Radius

간격: 0, 4, 8, 12, 16, 24, 32, 40, 48px.
선: 1px, 주요 문서 구분선·focus 2px. Radius: 0, 8px.
본문 최대1120px, desktop 좌우40px, mobile 좌우16px.
페이지는 세로 스크롤, 표의 비교열은 축소하지 않고 표 내부 스크롤로 보존.
의도적인 지역 표 스크롤 외 페이지 가로 넘침은 허용하지 않는다.

## Component states

버튼/링크/summary: default, hover, active, focus-visible.
버튼 최소44px 높이, disabled 스타일 명시. anchor는 비활성 상태를 만들지
않고 주소 미확인 시 plain text로 렌더한다. 이름은 안전한 HTTP(S) 원문 링크,
외부 링크는 target=_blank 및 rel=noopener noreferrer.

## Report hierarchy and meaning

금속 → 환율 → 시장지표 → 시총 → 주가. 종합은 별도 접힘.
자료 상태와 모든 원자료는 맨 마지막 details, 기본 닫힘. 인쇄도 기본 닫힘.
각 표의 실제 날짜/비교일을 제목/머리에서만 표시한다. 혼합일은 별도 표.
서로 다른 금속 단위/JPY100 기준은 품목 부제에 보존. 주가 원/시총 억원은
표 위에서 표시한다. %는 한 자리, 원자료 정밀도는 유지. 금리 변화는 bp.
누락은 —. 수집시총을 확정종가 시총으로 표시하지 않는다.

## Voice

voice_preset: mia-numeric-brief. 짧은 명사형 표 제목과 단위/기준 표기.
임의 시장 해석, 홍보 문구, 장식용 슬로건 없음. 한국어 단일 locale.
