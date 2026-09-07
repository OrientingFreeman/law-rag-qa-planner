# Searchable OCR PDF Import Adapter

v4.27.1은 텍스트 레이어가 있는 OCR PDF를 v4.27.0의 private OCR import
envelope로 변환한다. OCR을 새로 수행하거나 문서 내용을 법률지식으로 승인하지
않는다.

## 설치

```bash
pip install -e '.[pdf]'
```

## 사용

OCR PDF와 추출된 full text JSON은 Git 저장소 밖의 private storage에 둔다.
`--output`이 Git worktree 안이면 명령이 실패한다.

```bash
python -m tools.import_ocr_pdf \
  "/private/path/searchable-ocr.pdf" \
  --document-id private.requirements_facts \
  --title "비공개 OCR 자료" \
  --edition "판 정보" \
  --output "/private/path/requirements_facts_ocr_import.json" \
  --audit-output "/private/path/requirements_facts_audit.json"
```

`--output`은 OCR 전문을 포함하므로 private artifact다. `--audit-output`은
v4.27.0의 공개 안전 보고 형식으로 원문과 private PDF 경로를 제거한다.

## 보존 정보

- PDF의 1-based 물리 페이지 번호
- 페이지별 추출 텍스트
- 첫·마지막 줄에서 보수적으로 감지한 인쇄 페이지 표지
- 명시적인 `제N장`, `제N편`, `제N절` 표제 후보
- 텍스트 레이어 누락 페이지 목록
- 원본 PDF의 private source reference

PDF 물리 페이지 번호와 인쇄 페이지 표지는 별도 필드로 보존한다. 표지를 감지하지
못하더라도 물리 페이지를 바꾸거나 추정값을 확정하지 않는다.

## 실패와 제한

- 암호화 PDF는 먼저 복호화해야 한다.
- 텍스트 레이어가 비어 있는 페이지는 별도 OCR을 시도하지 않고 누락으로 기록한다.
- 장·절 경계는 짧고 명시적인 표제만 후보로 잡는다.
- 표·각주·다단 편집의 읽기 순서는 원본 PDF에 따라 추가 검수가 필요하다.
- 변환 결과는 전부 private input이며 후속 추출 결과도 `draft` 또는
  `review_required`에서 시작해야 한다.
