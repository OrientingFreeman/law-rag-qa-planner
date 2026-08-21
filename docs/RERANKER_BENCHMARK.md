# Optional Cross-Encoder Reranker

## 설계 경계

Reranker는 기존 BM25, semantic-lite, hybrid 또는 embedding retriever를 교체하지
않습니다. Retriever가 만든 상위 `retrieval_top_n` 후보를 query-document pair로
채점하여 최종 `top_k` 순서만 바꾸는 optional adapter입니다. 비활성 상태에서는
CrossEncoder를 import하거나 모델을 다운로드하지 않습니다.

```text
Query -> Retriever -> Top-N -> Optional CrossEncoder -> Top-K -> RAG
```

## Benchmark method

- `semantic_lite_reranker`
- `hybrid_reranker`
- `pretrained_embedding_reranker`
- `fine_tuned_embedding_reranker`

각 reranker method는 대응하는 비-reranker method와 동일 dataset, corpus,
Top-K에서 비교해야 합니다. fine-tuned method는 명시적인 checkpoint 경로가 없으면
실행을 거부합니다.

## Latency와 결과 기록

문항별로 retrieval latency, reranking latency와 두 값의 합을 저장합니다.
Reranked document에는 CrossEncoder score와 original retrieval rank가 함께 남습니다.
동일 score는 original rank를 유지하므로 결과가 비결정적으로 뒤집히지 않습니다.

실제 모델을 실행하기 전에는 품질 또는 latency 개선을 주장하지 않습니다. 향후
ablation에서는 baseline method와 reranker treatment를 동일한 45개 retrieval
evaluation case에서 비교합니다.
