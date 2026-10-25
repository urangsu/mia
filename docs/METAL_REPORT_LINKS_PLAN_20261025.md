# 니켈·리튬 공식 보고서 링크 / 추가 자료 실행 계획

작성·웹 확인: 2026-10-25 KST. **링크·메타데이터만 관리하는 후속 설계**다. PDF/본문 수집·AI 요약·메일 전송·로그인/유료 우회는 구현하지 않는다. 아래 링크 확인은 가격 수집 성공이나 신규 보고서 자동 감시 구현을 의미하지 않는다.

## 1. 우선 연결할 공식 목록

| 우선 | 발행처 / 검증한 공식 경로 | 자료 / 금속 | 링크 접근 / 운영 결정 |
|---|---|---|---|
| 1 | [IEA Global Critical Minerals Outlook 2026](https://www.iea.org/reports/global-critical-minerals-outlook-2026) | 핵심광물 수급·투자·중장기 전망; 니켈·리튬 등 | 공개 소개 페이지; 본문/다운로드 권한은 별도. 페이지의 발행일 2026-07-16 확인. 연간 보고서이지 일일 가격 아님 |
| 1 | [USGS Lithium Statistics and Information](https://www.usgs.gov/centers/national-minerals-information-center/lithium-statistics-and-information), [Nickel](https://www.usgs.gov/centers/national-minerals-information-center/nickel-statistics-and-information), [MCS 목록](https://www.usgs.gov/centers/national-minerals-information-center/mineral-commodity-summaries/) | MCS/Yearbook 생산·매장량·통계 | 공개 목록의 연도·제목·공식 문서 링크만. 리튬 페이지는 통계 이관/일부 게시 중지 안내가 있어, 신규 없음과 확인 실패를 구분 |
| 1 | [INSG Press Releases](https://insg.org/index.php/imprensa/), [Publications List](https://insg.org/index.php/publications/) | 니켈 수급 전망·회의 발표·World Nickel Statistics | 공개 보도자료와 유료 통계 상품을 구분. 목록에 October 2026 Meetings 항목 확인; 페이지 수정일을 보고서 발행일로 대체하지 않음 |
| 2 | [Fastmarkets BRM Monthly Update 2026](https://www.fastmarkets.com/metals-and-mining/battery-raw-materials/brm-monthly-market-update-2026/) | 리튬·니켈·코발트·블랙매스 등 월간 시장 자료 | 공개 소개/신청·구독 조건 구분. FMB 9444 로그인 세션과 무관한 링크 목록만 |
| 2 | [Benchmark 공식 사이트](https://www.benchmarkminerals.com/), [공개 Source](https://source.benchmarkminerals.com/) | 배터리 원료 전문 분석·리튬·니켈 | 유료/등록 자료를 무료 보고서라고 표시하지 않음. 자동 목록 어댑터는 실제 목록 구조를 별도 검증한 뒤 활성화 |
| 3 | [LME Reports and data](https://www.lme.com/market-data/reports-and-data) | 공식 금속 가격·재고·계약 정보 | 공식 링크 카탈로그. 일 지연/15분 지연 등 제공 조건을 보존; 자동 가격 수집 권한/계약/표 구조는 아직 미확정 |

2026-10-25에 실제 본문을 확인한 경로: IEA 2026 페이지, USGS 리튬 페이지, INSG Press Releases, LME Reports and data. Fastmarkets BRM·Benchmark 공식 경로는 검색 결과/공식 소개 기준 후보이며 전용 자동 파서 실검증은 아니다. USGS Nickel·INSG Publications·Benchmark Source는 후속 어댑터 확인 대상이다. 확정하지 않은 발행일을 만들지 않는다.

## 2. 구현 파일·데이터 계약

1. `research_links.py`: stdlib dataclass `ResearchLink(publisher,title,url,published_on,published_precision,metals,access,document_kind,first_seen_at,last_seen_at,verification_state)`. `published_precision`은 day/month/year/unknown; `access`는 public/registration/subscription/unknown. URL은 https 공식 allowlist만 허용한다. 제목과 HTML을 그대로 실행하지 않는다.
2. `research_link_sources.py`: 기관별 **목록 HTML/RSS 메타데이터만** 파싱. 검증된 IEA/USGS/INSG부터 시작한다. 요청 제한 10초, 페이지 크기 제한 2MB, 기관별 독립 실패. 다운로드/PDF MIME 및 로그인 화면은 읽지 않고 링크·권한 상태만 남긴다. robots/공개 접근 정책을 먼저 확인한다.
3. SQLite 별도 `research_links` / `research_link_events` / `research_link_checks`. 수치 테이블에 보고서 링크를 끼워 넣지 않는다. PK는 기관+정규화 공식 URL; utm만 제거하고 문서 식별 query는 보존. 같은 문서에 여러 금속 태그 허용.
4. `desktop_research.py`: 자료·보고서 안의 별도 '공식 리서치 링크' 목록. 금속·기관·발행일·접근 조건 필터, 공식 사이트 열기, 확인 시각/오류 표시. 가격표 위에 기사 피드를 넣지 않는다. HTML은 링크 목록 부록만, PPTX는 필요한 공식 링크 텍스트만.
5. `pipeline_v37.py`: 기존 08:30 업무의 선택적 `research_links` 단계. 저장된 설정이 활성화되어 있을 때 1일 1회 목록 확인. 가격·Excel·ECM 성공 여부와 독립; 보고서 확인 실패로 금속 원본을 롤백하지 않는다. 새 Codex 자동화/메일 예약은 만들지 않는다.

## 3. 새 발행물·개정·장애 규칙

- 최초 목록 등록은 기준선이다. 오래된 전 자료를 '오늘 새 보고서'로 알리지 않는다. 발행일 미상 자료는 '신규 발견 · 발행일 미확인'으로 구별한다.
- URL 신규+발행일 확인이 '새 발행물', 같은 URL의 제목/발행 메타 변경은 '개정 감지'다. 단순 페이지 수정시각·가격 갱신은 새 보고서가 아니다. PDF 내용 변경을 해시 검증했다고 주장하지 않는다.
- 기관별 정상 확인 이후의 새 항목만 배지로 표시한다. 발행일은 source date, first_seen은 KST 관측시각이다. 둘을 합치지 않는다.
- 파서/네트워크/권한 실패는 마지막 정상 링크를 보존하고 stale/check_failed/auth_required로 표시한다. 목록이 비었다고 과거 링크를 삭제하지 않는다. 재시도는 해당 기관만 1회; 무한 polling 금지.
- 기관 이동/리다이렉트는 공식 allowlist 내에서만 승인한다. 임의 URL/로그인 토큰·사내 ECM 경로를 링크 저장소에 넣지 않는다.

## 4. 가격·지수의 더 나은 출처 도입 순서

금속 주업무를 지수 대시보드로 바꾸지 않는다. 먼저 리튬/니켈/FMB 품목 coverage와 계약을 완성한 뒤, 필요한 보조지표만 다음 순서로 평가한다.

| 자료 | 우선 후보 | 이번 결정 / 검증 계약 |
|---|---|---|
| 국내 KOSPI/KOSDAQ·지수 | [금융위원회 개방 목록](https://www.fsc.go.kr/in060301), 공공데이터포털 지수시세정보 | 키/승인·기준일·갱신시각·수정 정책 확인 후 별도 어댑터. 과거 대화에 '승인' 문구가 있어도 이 환경에서 키 준비를 확인하지 못했으므로 연결했다고 하지 않음. 현재는 FDR NAVER 유지 |
| 미국10년 | [미 재무부 Daily Treasury Rates](https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?type=daily_treasury_yield_curve), [FRED DGS10](https://fred.stlouisfed.org/series/DGS10) | Yahoo ^TNX보다 '미 재무부 10년 par yield'라는 보고 정의에 직접 맞는 후보. 둘은 기존 ^TNX와 다른 series_key로 추가; %/관측일/게시 지연/휴일 검증 후 명시 선택. 자동 fallback으로 수열을 섞지 않음 |
| 한국10년·공식 금리/환율 | [한국은행 ECOS](https://ecos.bok.or.kr/) | 통계표/항목/일별 주기/시장금리 vs 기준금리/환율 정의와 키 필요 여부 확인. SMBS 매매기준율을 중앙은행 금리와 혼동하지 않음 |
| LME 니켈·구리·코발트 | [LME 공식 자료](https://www.lme.com/market-data/reports-and-data) | Cash/3M, bid/offer/settlement, USD/t, 공식일·지연·권한을 먼저 확정. 미확정은 unsupported; NAVER/FMB/ETF를 LME라고 표기하지 않음 |
| 리튬 현물·선물 | 기존 구독 FMB / 허용 SMM / GFEX | 전지급 탄산/수산화, CIF지역·VAT포함/제외·계약월 별도. 공통 '리튬가격' 열로 덮어쓰지 않음. 근거 없는 22.3%/20.9% 계산 도입 안 함 |
| Dow/SOX/NASDAQ100·달러·에너지 | 현재 FDR/Yahoo 별도 검증 후 선택적 확장 | 금속업무 보조 목적일 때만. 원천 심볼·거래소 캘린더·두 기대 종가·출처/단위 fixture와 실제 조회를 모두 통과한 뒤 활성화. 이번 변경에는 임의 추가하지 않음 |

## 5. 후속 합격 기준

각 기관 1개 이상의 공개 목록 fixture로 링크·발행일 정밀도·금속 태그·구독 조건 검증. 최초 baseline 배지 없음, 신규/개정/중복URL/페이지실패/빈목록/리다이렉트/미래일자/스크립트 제목을 테스트한다. 동일 결과 재실행은 event 중복 0. 가격 원본·Chrome 9222/9337/9444·Edge 세션 변경 0. 실제 목록 조회 결과와 오프라인 fixture 테스트를 별도 기록한다. 수집되지 않은 보고서를 '최신 자동 확보'로 표시하면 불합격이다.
