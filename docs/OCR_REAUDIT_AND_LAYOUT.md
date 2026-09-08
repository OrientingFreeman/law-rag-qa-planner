# OCR 재감사와 본문/각주 레이아웃 힌트

v4.27.2는 이미 생성한 private OCR import JSON을 다시 사용하므로 PDF를 재처리할 필요가 없습니다.
비본문 판단은 반드시 사람이 확인한 별도 JSON으로 입력합니다. 저장소에는 책별 페이지 번호나 원문을 커밋하지 않습니다.

```json
{
  "schema_version": "0.1.0",
  "decisions": [
    {
      "page_number": 2,
      "classification": "blank",
      "reason": "원본 이미지 육안 확인",
      "review_status": "approved",
      "reviewer": "reviewer-id",
      "reviewed_at": "2026-08-22"
    }
  ]
}
```

```bash
python -m tools.audit_ocr_source "$HOME/private-law-rag/requirements_facts_ocr_import.json" \
  --page-decisions "$HOME/private-law-rag/requirements_facts_page_decisions.json" \
  --repair-printed-labels \
  --infer-footnotes \
  --output "$HOME/private-law-rag/requirements_facts_audit_v4272.json"
```

각주 경계는 페이지 높이의 절반으로 고정하지 않습니다. 텍스트 후반의 각주 표지 군집을 보수적으로
찾아 `body_candidate`, `footnote_candidate`, `unknown`만 기록합니다. 이 값은 검색 제외나 법적
승인의 근거가 아니며, 원문 텍스트를 자르거나 변경하지 않습니다.
