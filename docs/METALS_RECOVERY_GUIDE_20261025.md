# 금속 중심 개선판 실행 / 수집 실패 확인

이 변경은 main 13c19a7의 10월23일 설계와 별도 FDR 개발 브랜치를 통합한 후속 구현이다. 회사 전체 수집 완성/배포 승인본이 아니다. **기존 설치·DB·누적 Excel은 보존하고 새 폴더에 소스를 받는다.**

## 1. 시작

```text
py -m pip install -r requirements-desktop.txt
py FastmarketsCollector_v3_7.py
```

`RUN_GUI.cmd`도 같은 진입점을 실행한다. 기존 `requirements.txt`만 설치한 PC는 Qt가 없을 수 있으므로 `requirements-desktop.txt`를 사용한다. Python 3.10+가 필요하다. 기존 Tk UI는 `--legacy-gui`로 보존하지만 새 금속 탐색/공개 전용 버튼은 Qt 화면 기능이다.

## 2. 화면

- 첫 탭은 **원료·금속 시황**. 리튬 → 니켈 → 코발트 → 망간 → 구리 → 블랙매스. 공식 description으로 품명을 분류하고 원본 조건·단위·Actual/Forecast·출처를 함께 표시한다. 설명 불충분은 '품목명 확인 필요'; 내부 MB코드는 상세/툴팁과 별도 코드 열에 있다.
- 그룹·시리즈 선택 → 1/3/6개월·1년·전체 또는 YYYY-MM 월 범위. 표와 차트는 같은 포인트를 사용한다. 커서를 올리면 날짜·값/결측·단위·구분·원천·뷰가 보인다. 한 번에 하나의 단위/뷰를 그려 비교 불가능한 수열을 합치지 않는다.
- 명시적인 결측/보류는 선을 끊고 0으로 채우지 않는다. 다른 뷰의 값으로 빈 뷰를 채우지 않는다. 기간 기본 끝은 선택 시리즈의 마지막 저장 관측일이며 '실시간'을 의미하지 않는다. 월별 요약/별도 period_label 행은 이 일별 차트에서 제외하며 원본 Excel/DB에는 남긴다.
- 작은 창에서는 차트·표가 겹치지 않도록 금속 영역을 스크롤한다. 긴 전체 이력의 좌표는 1회 캐시, hover는 이진 탐색한다. 실제 선형 그리기 비용은 남으므로 10년 이상 고빈도 자료는 별도 성능 측정이 필요하다.
- 환율/확정 종가/주가/시총은 보조 탭에 유지한다. **원천 수집 범위**에는 저장 관측과 미지원 LME/SMM/GFEX를 구별한다. captured는 전체 작업공간 누락 0/공식가격 검증 완료가 아니다.
- 자료·보고서의 '자료 기준'은 하단 기본 접힘이다. HTML도 하단 details이며 JS 없이 열고 닫는다. 중요 경고는 상단 요약과 각 행에 남는다. 인쇄 펼침 CSS는 최신 브라우저용이며 회사 브라우저 인쇄는 미검증이다.

## 3. 수집 실패를 나누어 확인

**공개 종가만 수집**: 이번 실행에 한해 FMB/FX/NAVER DOM을 끄고 FDR를 켠다. 저장된 출처 설정은 변경하지 않는다. 로그인·ChromeDriver가 없어도 공개 HTTP 경로를 시험할 수 있다. 이 버튼은 금속 구독가격/환율/시총 수집을 대체하지 않는다.

**시세 수집**: 저장 화면의 선택 출처를 실행한다. Fastmarkets는 Chrome 9444의 소유·포트·프로필·로그인을 검증한다. 9222/9337·일반/관리자 Edge에는 간섭하지 않는다. 회사 프록시/방화벽·인증·Driver 문제는 실제 진단이 필요하다.

실패/부분 완료 후 하단에 **출처·실패 단계·실제 오류/누락 사유**가 나온다. 상세는 실행 기록과 데이터 폴더의 `last_diagnostic.json`, `collector.log`를 확인한다. 외부 공유 전 계정·쿠키·토큰·회사 경로를 제거한다. HTML/Excel만 실패하면 재수집 대신 출력만 재시도한다. 전체 FDR 요청이 실패하면 이제 partial이 아닌 failed로 표시한다.

공개 전용의 정상 자료가 있어도 KR10Y 미지원/금속·환율·시총 자료 없음 때문에 전체는 부분 완료가 될 수 있다. 이를 'ChromeDriver 연결 실패'와 혼동하지 않는다. 금·WTI는 연속선물이며 금 현물/공식 정산가가 아니다. 실제 수집일마다 필요한 두 날짜가 있는지 다시 검사한다.

Windows에서 Fastmarkets 실패 원인을 좁힐 최소 명령:

```text
py diagnose_windows.py --driver-check
py collect_evidence_v37.py --output evidence_v37.json
```

현재 사용자가 알려준 증상은 '수집 실패'뿐이며 실제 오류 로그는 아직 받지 못했다. main에 FDR가 없던 문제와 실패 이유 축약은 확인했지만, 이것이 회사 Fastmarkets 실패의 단일 원인이라고 단정하지 않는다.

## 4. 단일 TXT / ZIP

새 형식은 `MIA_SOURCE_CURRENT.txt`와 `RESTORE_LATEST_SOURCE.py`다. 기존 PART/LZW ONEFILE과 섞지 않는다. 두 파일을 같은 폴더에 놓는다.

선택 사항으로 같은 폴더의 `RESTORE_LATEST_SOURCE.cmd`를 더블클릭하면 검증→복원을 순서대로 실행한다. 외부 의존성을 자동 설치하거나 회사 브라우저/DB를 변경하지 않는다.

```text
py RESTORE_LATEST_SOURCE.py --verify-only
py RESTORE_LATEST_SOURCE.py
```

새 `%LOCALAPPDATA%\MIA_Sources\MIA_<커밋12자리>`에 복원한다. 기존 폴더가 있으면 거부한다. TXT 안의 ZIP·manifest·모든 파일을 SHA-256으로 검증한다. 해시는 손상 검증이지 서명/발행자 인증이 아니므로 신뢰하는 저장소에서 받는다. 소스 ZIP도 제공하며 소스/테스트/설치 목록을 포함하고 실행 바이너리·계정·사용자 DB/Excel은 포함하지 않는다.

개발자는 커밋 후 `python scripts/build_source_bundle.py --revision HEAD --output-dir <새 출력폴더>`로 생성한다. 작업 폴더의 미커밋 파일/운영 데이터가 아니라 지정 Git 커밋만 포함한다. 번들은 자동 업데이트되지 않으므로 TXT 헤더의 source_commit을 확인한다.

## 5. 후속

[공식 니켈·리튬 보고서 링크 계획](METAL_REPORT_LINKS_PLAN_20261025.md)에는 실제 확인한 기관 경로, 최초 목록/새 발행/개정/오류 구분, 공식 금리·지수 후보를 정리했다. 보고서 본문·PDF·AI 요약·메일·새 자동감시는 이번에 추가하지 않았다. LME/SMM/GFEX 실제 어댑터, NAVER 새 DOM 전체 지원, FMB 전체 작업공간 inventory, Windows COM/예약/ECM 서버 인수는 남아 있다.
