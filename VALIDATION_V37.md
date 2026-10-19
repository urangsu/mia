# v3.7 검증 보고서

검증일: 2026-10-19. 환경: macOS, Python 3.14. Windows 배포 후보이며 상용 인수 완료가 아닙니다.

## 실행 결과

| 구분 | 결과 | 증거 범위 |
|---|---|---|
| v3.6 기준선 | 123개 통과 | 기존 패키지의 테스트 새로 실행 |
| 최종 전체 회귀 | 202개 통과, 0.705초 | verification/regression.log |
| v3.7 테스트만 | 79개 통과, 0.409초 | ResourceWarning을 오류로 취급한 별도 실행 |
| Python 구문 검사 | 전체 PY 컴파일 통과 | verification/results.json 파일 수 |
| BM pinned DOM | DOM_PINNED_FIXTURE_OK | 실제 수집 SAMPLE_JS + linkedom + 합성 형제 pinned 컨테이너 |
| GUI | GUI_SMOKE_OK | 실제 Tk 창 구성·큐 처리·다크 배경·최신값 표 확인. 사이트/로그인/ECM 호출 안 함 |
| 숫자 출력 | 통과 | 불변 snapshot SHA 재계산, HTML escape, Excel 숫자 셀·수식 주입 방지, PPTX native 표 값 일치·분할 |
| PPTX 시각 점검 | 합성 샘플 렌더 점검 | LibreOffice PDF 변환 후 금속/시장 10열/시총 표의 한글·날짜·가격 가독성 확인. Microsoft PowerPoint 실검증 아님 |
| HTML 시각 점검 | 미완료 | HTML 구조/값/escape 테스트 통과. 브라우저의 로컬 파일 열기 정책으로 화면 렌더 검증은 수행하지 못함 |
| Windows 예약 | 미검증 | XML·시간 검증·least privilege·중복/누락/재시도 계약만 테스트 |
| 회사 실환경 | 미검증 | Fastmarkets 로그인·전체 종목/실제 BM 실패 DOM·NAVER 실DOM/과거 종가·보안 Excel COM·ECM 서버 체크인 |

전체 회귀 로그에 구버전 SQLite 테스트의 미닫힘 ResourceWarning이 남습니다. 기존 기준선에서도 확인된 경고이며 새 v3.7 전용 79개는 ResourceWarning 오류 모드에서 통과했습니다. CLI의 잘못된 필터 조합 거부 테스트가 출력한 argparse error 문구는 의도된 성공 사례이며 테스트 실패가 아닙니다.

## 성능

10회 합성 CPU 블록 계획 평균 0.001272초, P95/최악 0.001553초, 실패율 0. 숫자 쓰기 구조는 5,000개 셀 호출에서 사용자 열을 건너지 않는 2개 직사각형 호출로 묶였습니다. 이것은 실제 COM 실행·수식 검사·Save/DRM·브라우저·네트워크 시간이 아니며 전체 30% 단축을 입증하지 않습니다.

Windows 실제 warm 비교는 사본 폴더에서 아래처럼 실행합니다. 이 명령은 수집과 로컬 출력 10회를 실제 수행하지만 ECM은 열지 않습니다.

```text
py benchmark_windows_v37.py --data-dir C:\FM_Test_Copy --runs 10 --confirm-test-run
```

기존 운영 DB/Excel을 테스트 대상으로 지정하지 마세요. 허용된 사본으로 기준선과 수정본을 같은 조건에서 비교해야 합니다.

## 중요한 미완료 조건

- 공식 CSV와 실제 DOM의 속도·정확도 우열: 실제 동일 조건 자료 없음. 자동 다운로드를 추정 구현하지 않음.
- 회사 전체 종목의 누락 0: 실 inventory/CSV 없으므로 미확정. 합성 필수 종목 테스트로 대체 주장하지 않음.
- NAVER 전일/직전 종가: 종료 근거와 두 시장일 이력이 확인될 때만 비교. 최초 이력 부족은 명확한 부분 완료.
- 예약 등록/실제 자동 기동: 이 Mac에는 만들지 않음. 회사 Windows에서 등록하고 다음 실행/실행 결과/파일 생성까지 인수 확인 필요.
- 절전 깨우기는 장비 정책 의존. 완전 종료 상태의 전원 켜기는 지원하지 않음.
- ECM은 실제 문서 HWND/경로를 검증하더라도 Excel 인스턴스가 COM에 노출되지 않으면 중단함. 임의 우회하지 않음.
- Windows Excel Save/셀 재읽기와 ECM 서버 체크인은 별개. 서버 성공으로 표시하지 않음.

## 독립 검토에서 수정한 사항

aria-label 하락 부호, 다른 행 날짜 전파, 미검증 단위, 초기 hydration 조기 종료, 빈 헤더 밑 사용자 값 보호, Excel HWND 전달/재검증, NAVER 열 출처 오표시, 보고서 필터의 누적 원본 축소, 출력 메타데이터로 인한 no-op 무효화, FX 중복 출처 충돌, 과거 날짜=종가라는 잘못된 가정, 종가 미확정 자료의 일일 완료 게이트를 수정했습니다.

## 인수에 필요한 최소 절차

1. 회사 Windows에서 사본 DB/Excel로 최초 실행, 진단·누적 결과 비교.
2. 동일 자료 재실행해 revision/COM Save/no-op 및 사용자 수식·열 보존 확인.
3. 실제 Fastmarkets CSV/위젯과 탄산리튬·코발트·망간·Black Mass·Payable 전체 코드/날짜 대조.
4. NAVER 두 종료 시장일 종가를 원문과 대조. 날짜가 없는 값·당일 장중 값은 빈값/경고인지 확인.
5. ECM 잘못된 같은 파일명/다른 HWND 차단 확인 후 올바른 사본에 미리보기·승인·Save·서버 체크인을 각각 확인.
6. Windows 시계를 한국시간으로 맞추고 2~3분 후 예약으로 자동 기동을 시험한 다음 08:30 등록. 로그인·절전·네트워크 복구/중복 실행도 확인.

원본 입력 SHA-256: FastmarketsCollector_v3_6_ECM_Sync.zip = `74845fd6f0ac7cc11fd938a16e4b256141b5f8c928d59b8724d70378bc330935`.
