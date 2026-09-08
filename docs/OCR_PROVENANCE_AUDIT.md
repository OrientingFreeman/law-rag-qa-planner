# OCR 원천 출처·품질 감사

v4.27.0은 private OCR 자료를 Legal Reasoning 지식으로 추출하기 전에 출처와
구조를 검증하는 로컬 import boundary다. OCR 내용을 지식으로 확정하거나 자동
승인하지 않는다.

## 입력 경계

입력 JSON은 `manifest`와 `pages`를 가진다. `manifest`에는 문서 ID, 판, 권리
상태, 예상 페이지 범위와 선택적인 private source reference를 기록한다. 각
페이지는 페이지 번호, 인쇄 페이지 표지, 장·절과 OCR 텍스트를 가진다.

실제 원본과 OCR 전문은 Git 외부 private storage에 보관한다. 공개 저장소에는
직접 작성한 최소 fixture만 둔다.

```bash
python -m tools.audit_ocr_source /private/path/ocr_import.json \
  --output /private/path/ocr_audit_report.json
```

## 출력과 개인정보·저작권 경계

감사 보고서에는 OCR 원문이나 private source reference를 기록하지 않는다.
문단별로 다음 정보만 보존한다.

- 안정적인 segment ID
- document·edition·page·paragraph
- 장·절·인쇄 페이지 표지
- 문자 시작·종료 위치
- 원문 확인용 SHA-256
- `draft` review status

manifest의 metadata도 `public_` 접두사가 있는 항목만 공개 보고서에 남는다.

## 품질 검사

- 누락·중복·범위 밖·역순 페이지
- 빈 페이지 또는 비정상적으로 짧은 페이지
- 인쇄 페이지 표지 누락
- 대체 문자와 제어 문자
- 호환 한자
- 조문 번호 OCR 의심 패턴
- 부정 표현 OCR 의심 패턴
- manifest에 선언한 장 식별자 누락

오류가 있으면 `blocked`, 경고만 있으면 `review_required`, 둘 다 없으면
`passed`다. `passed`는 OCR 내용의 법률적 정확성이나 승인 상태를 의미하지
않는다. 후속 structured extractor의 출력도 반드시 `draft` 또는
`review_required`로 시작하고 사람 검수 후에만 `approved`로 승격한다.
