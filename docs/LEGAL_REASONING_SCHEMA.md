# 법률 추론 스키마 v0

`law_rag.reasoning.legal_schema`는 검색용 `LegalOntology`와 별개의 지식
구조 계층입니다. `LegalOntology`가 용어 정규화와 retrieval 보강을 담당하는 반면,
이 스키마는 청구권·청구원인·요건·항변·재항변·주장/증명책임·필요 사실·증거
유형·후속 질문·법적 근거 사이의 명시적 관계를 저장합니다. 실제 요청에서 검색된
근거와 논증 경로는 기존 evidence/argument graph가 계속 담당합니다.

## 공개/비공개 경계

- 공개 저장소에는 직접 작성한 최소 구조와 공개 법령 참조만 둡니다.
- 저작권이 있는 OCR 원문과 private source path는 포함하지 않습니다.
- OCR 기반 추출 결과는 `draft` 또는 `review_required`로 시작하고 자동 승인하지 않습니다.
- 문서·판·장·절·페이지·span은 `SourceProvenance`로 보존할 수 있습니다.
- 내부 schema node와 기존 ontology/evidence는 복제하지 않고 안정적인 외부 ID로 참조합니다.

## 무결성 규칙

`LegalReasoningSchema.validate()`는 schema/knowledge/node/relation ID, 중복 ID,
dangling internal reference, 허용되지 않은 relation endpoint 조합, 승인 node의
provenance, burden holder 및 follow-up template를 검사합니다. JSON 출력은 key를
정렬하므로 동일 입력의 round-trip 결과가 결정론적입니다.

최소 파일럿은
`examples/legal_reasoning/loan_repayment_claim.v0.json`에 있습니다. 이는 완성된
법률판단 데이터가 아니라 다음 수동 구축·검수 패치를 위한 `review_required`
구조 예시입니다.
