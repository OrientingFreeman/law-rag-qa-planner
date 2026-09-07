# OCR 경고 검토 큐

v4.27.4는 public-safe 감사 보고서와 원문 일부가 필요한 private 검토 큐를 분리한다.
검토 큐는 Git 저장소 밖에만 저장할 수 있고 파일 권한은 `0600`이다.

```bash
python -m tools.audit_ocr_source PRIVATE_IMPORT.json \
  --page-decisions PRIVATE_PAGE_DECISIONS.json \
  --repair-printed-labels --infer-footnotes \
  --review-queue-output PRIVATE_REVIEW_QUEUE.json \
  --output PRIVATE_AUDIT.json
```

`missing_printed_page_label`은 다음 후보로 분류한다.

- `front_matter_candidate`: 최초 숫자 인쇄면수보다 앞선 페이지
- `approved_non_text`: 이미 승인된 비본문 페이지
- `unreviewed_non_text`: 아직 승인되지 않은 빈 페이지
- `printed_label_detection_gap`: 본문 구간에서 탐지되지 않은 페이지

검토 결정 파일은 다음 형식이다. warning ID는 검토 큐의 값을 그대로 사용해야 한다.

```json
{
  "schema_version": "0.1.0",
  "decisions": [
    {
      "warning_id": "warn.example",
      "action": "accepted_as_is",
      "reason": "원본 대조 완료",
      "review_status": "approved",
      "reviewer": "reviewer-id",
      "reviewed_at": "2026-08-22"
    }
  ]
}
```

재감사할 때 `--warning-decisions PRIVATE_WARNING_DECISIONS.json`을 추가한다. 승인된 경고는
삭제되지 않고 동일 warning ID의 `info` 항목으로 남는다. 원문이나 감사 규칙이 바뀌어 warning ID가
더 이상 일치하지 않으면 결정을 자동 적용하지 않고 오류로 중단한다.
