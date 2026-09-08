# 평가 데이터 거버넌스와 Human Review

## 목적

평가 점수뿐 아니라 어떤 데이터·법령 코퍼스·검색기·프롬프트·모델을 사용했는지 재현 가능하게 기록합니다. 자동 생성 또는 자동 검증 결과는 사람의 확인 없이 승인된 정답 데이터로 승격하지 않습니다.

## 데이터셋 릴리스

`official_core_cases.json`은 같은 이름의 sidecar manifest와 함께 관리합니다. Manifest에는 데이터셋·정답·스키마 버전, 사례 수, SHA-256, 승인 사례 수, 원천 snapshot 및 변경 요약을 기록합니다. JSON은 key 정렬과 공백 제거를 거친 canonical content로 해시하므로 운영체제의 LF/CRLF 및 들여쓰기 차이는 checksum에 영향을 주지 않습니다. 실제 의미 내용이나 사례 수가 manifest와 다르면 실험을 중단합니다.

현재 61개 공식 사례는 기존 수동 검수 결과를 `legacy_manual_review_bootstrap` 정책으로 이관한 기준선입니다. 이후 변경되는 사례는 Evaluation UI의 검수 큐에서 별도 이력을 남겨야 합니다.

## 검수 흐름

상태는 `draft`, `review_required`, `approved`, `rejected`, `deprecated`로 제한합니다. 검수 이력은 `evaluation/reviews/review_records.jsonl`에 append-only 방식으로 기록하며, 최신 상태는 마지막 레코드로 계산합니다.

- 승인: 의견은 선택 사항
- 수정 요청·거절·폐기: 의견 필수
- 공개 데모: 검수 쓰기 비활성화, 내부 평가·검수 화면과 관리 API는 HTTPS 관리자 인증 적용, 정적 HTML 직접 접근 차단
- 현재 단계: 단일 Reviewer만 지원

복수 Reviewer, adjudication, 사용자 인증 및 조직 기능은 현재 범위에 포함하지 않습니다.

## 재현 가능한 실험

실험에는 dataset/corpus SHA-256, seed, baseline/treatment 관계, retriever·embedding·reranker·prompt version과 provider/model을 기록합니다. 현재는 JSON 기반 경량 저장소를 유지하며 별도 MLOps 서버를 요구하지 않습니다.

Retrieval Benchmark의 `wrong_top1`, `retrieval_miss`, `over_retrieval`은 hard-negative 후보로 변환할 수 있습니다. 후보는 내용 기반 ID로 중복을 방지하고 `review_required` 상태로 저장합니다. 기존 Human Review에서 승인된 후보만 versioned training dataset으로 export하며, 미검수·수정 요청·거절 후보는 포함하지 않습니다. 이 단계는 학습 데이터를 준비할 뿐 embedding fine-tuning을 자동 실행하지 않습니다.

## LangChain 경계

`LawRagLangChainRetriever`는 기존 검색 결과를 LangChain `Document`로 변환하는 선택적 adapter입니다. Hybrid ranking, ontology reranking, evidence graph, reasoning, citation 검증 및 evaluation은 기존 core가 계속 담당합니다.

```bash
pip install -e '.[langchain]'
```

```python
from law_rag.integrations.langchain import LawRagLangChainRetriever

retriever = LawRagLangChainRetriever(service=service, domain_id="digital_business", top_k=5)
documents = retriever.invoke("개인정보 수집 요건은?")
```

Native와 adapter 경로의 문서 ID·순서·본문·metadata 동일성은 회귀 테스트로 확인합니다.
