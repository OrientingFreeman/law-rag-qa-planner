# 인쇄면수 승인 결정

v4.27.6은 private OCR 검토 큐의 고신뢰도 제안값을 승인 결정 파일로 내보낸다. 명시적인
`--approve-high-confidence`와 검토자·검토일이 없으면 생성하지 않는다.

```bash
python -m tools.export_printed_page_decisions PRIVATE_REVIEW_QUEUE.json \
  --output PRIVATE_PRINTED_PAGE_DECISIONS.json \
  --reviewer reviewer-id --reviewed-at 2026-08-22 \
  --verified-label-absent 1,9 \
  --approve-high-confidence
```

결정 파일을 적용하려면 감사 명령에 다음을 추가한다.

```bash
--printed-page-decisions PRIVATE_PRINTED_PAGE_DECISIONS.json
```

결정은 원본 OCR content SHA-256과 결합된다. 원본이 바뀌거나 기존 탐지 표지와 충돌하면
적용을 거부한다. 적용 후 private 검토 큐의 `correction_audit`에 결정 해시와 전후 표지가 남는다.
