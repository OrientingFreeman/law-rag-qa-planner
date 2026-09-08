# OCR 교정 오버레이와 인쇄면수 추론

v4.27.5의 교정 overlay는 원본 private import JSON을 수정하지 않는다. 승인된 교정만 감사 실행 중
메모리에서 적용하며, 원문 문자열이 해당 페이지에서 정확히 한 번 일치하지 않으면 중단한다.

```json
{
  "schema_version": "0.1.0",
  "corrections": [
    {
      "page_number": 1,
      "original_text": "직접 작성 오류 예시",
      "replacement_text": "직접 작성 교정 예시",
      "reason": "원본 대조 완료",
      "review_status": "approved",
      "reviewer": "reviewer-id",
      "reviewed_at": "2026-08-22"
    }
  ]
}
```

`--text-corrections PRIVATE_CORRECTIONS.json`으로 적용한다. private 검토 큐의 `correction_audit`에는
페이지별 전후 SHA-256과 결정 메타데이터가 기록된다.

인쇄면수 추론은 탐지된 숫자 표지 가운데 같은 `physical_page - printed_page` 오프셋이 최소 20개,
80% 이상일 때만 활성화된다. 누락 페이지에는 `suggested_printed_page_label`,
`inference_confidence`, `inference_evidence`가 기록되며 실제 페이지 표지로 자동 반영되지 않는다.
