# mia · Fastmarkets Collector v3.7

금속·환율·시장 확정 종가를 SQLite와 누적 Excel에 보관하고 HTML·편집 가능한 PPTX 보고서를 만드는 Windows 업무 도구입니다. 기본 예약 시각은 **08:30 KST**입니다.

현재는 **실환경 인수 전 후보 빌드**입니다. 클라우드에서 통과한 모의 테스트가 회사 Windows·Fastmarkets 구독·NAVER 실DOM·ECM 서버 성공을 의미하지 않습니다.

## Codex에서 이어 작업

1. [AGENTS.md](AGENTS.md)를 읽습니다.
2. [후속 작업지시서](docs/CODEX_WORK_ORDER.md)와 [인수 경계](HANDOFF_V37.md)를 읽습니다.
3. 환경 설치는 `bash scripts/codex_setup.sh`, 검증은 `bash scripts/codex_check.sh`를 실행합니다.
4. 결함 재현 → 실패 테스트 → 수정 → 회귀 순으로 P0부터 진행합니다.

이 저장소에는 실제 소스가 루트에 있습니다. ZIP 재첨부가 필요하지 않습니다. 기존 버전명 진입점은 호환용이며 최신 진입점은 `FastmarketsCollector_v3_7.py`입니다. 실제 Selenium 코어는 이름을 유지한 `FastmarketsCollector_v3_4.py`입니다.

## Windows 사용

```text
py -m pip install -r requirements.txt
py FastmarketsCollector_v3_7.py
py FastmarketsCollector_v3_7.py --schedule 08:30
py FastmarketsCollector_v3_7.py --schedule-status
```

[사용법](README_V37.md) · [변경 내역](CHANGELOG_V37.md) · [기존 검증 기록](VALIDATION_V37.md) · [클라우드 환경 설정](docs/CLOUD_SETUP.md)

Chrome **9444**만 Fastmarkets에 사용합니다. **9222/9337에는 간섭하지 않습니다.** ECM은 이미 로그인된 일반 Edge를 사용하며 별도 프로필/쿠키 복사를 하지 않습니다. 예약 실행은 ECM 승인 쓰기를 자동 수행하지 않습니다.

## 데이터와 접근 정보

공개 저장소에는 소스·합성 fixture·문서만 보관합니다. 계정·쿠키·프로필·회사 DB/Excel·실제 수집 로그는 올리지 마세요. 네이버는 두 실제 거래일의 확인된 종가로 비교하며 이력 부족은 `missing_history`로 남깁니다. 뉴스·AI 해설·메일 발송·유료 시세 API는 이번 범위가 아닙니다.

원본 배포 ZIP의 중복 PY/TXT 미러·합성 출력 바이너리·기기별 검증 로그는 저장소에서 제외했습니다. 프로그램 소스와 모든 기존 테스트는 보존했습니다.
