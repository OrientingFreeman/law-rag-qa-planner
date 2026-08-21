# Retrieval Ablation Runner

v4.22의 Retrieval Ablation Runner는 검색 조합의 구현 여부와 실제 실행 결과를
분리하여 관리합니다. 특정 법률 분야에 종속되지 않으며 동일한 dataset, corpus,
사례 선택, Top-K 조건에서 완료된 조합만 비교합니다.

## 비교 조합

- BM25
- Semantic-lite
- Hybrid
- Pretrained Embedding
- Pretrained Embedding + Reranker
- Fine-tuned Embedding
- Fine-tuned Embedding + Reranker

각 조합은 `not_run`, `unavailable`, `completed`, `failed` 중 하나의 상태를
가집니다. 기본 실행은 plan-only이므로 사용 가능한 조합도 `not_run`으로만
기록됩니다. 선택 의존성 또는 fine-tuned checkpoint가 없으면 `unavailable`과
사유를 기록합니다. 성능 지표는 `completed` 조합에만 존재합니다.

```bash
# 실행 계획만 Experiment Store에 저장
python -m tools.run_retrieval_ablation

# 로컬에서 사용 가능한 경량 조합을 실제 실행
python -m tools.run_retrieval_ablation \
  --methods bm25 semantic_lite hybrid \
  --top-k 5 \
  --execute
```

실제 pretrained 또는 fine-tuned 모델 조합은 ML 선택 의존성과 모델 또는
checkpoint를 명시적으로 준비한 환경에서만 실행합니다.

```bash
pip install -e '.[ml]'
python -m tools.run_retrieval_ablation \
  --methods pretrained_embedding pretrained_embedding_reranker \
  --embedding-model sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 \
  --reranker-model BAAI/bge-reranker-v2-m3 \
  --retrieval-top-n 20 \
  --top-k 5 \
  --execute

python -m tools.run_retrieval_ablation \
  --methods fine_tuned_embedding fine_tuned_embedding_reranker \
  --fine-tuned-embedding-model evaluation/training/checkpoints/legal-retrieval-v1 \
  --retrieval-top-n 20 \
  --top-k 5 \
  --execute
```

## 비교와 회귀 판정

Runner는 각 treatment의 정의된 baseline이 함께 완료되었을 때만 비교합니다.
Top-1 Accuracy, Hit@K, Recall@K, MRR, nDCG@K의 감소는 허용 오차를 반영해
품질 회귀로 판정합니다. latency 증가는 품질 회귀로 합치지 않고 별도의
trade-off delta로 남깁니다.

결과에는 전체 metric delta, 법률 분야별 metric delta, 사례 단위 개선·악화·동일
건수가 포함됩니다. 서로 다른 dataset/corpus checksum 또는 사례 선택이 발견되면
비교를 중단합니다. 결과 JSON은 기존 `evaluation/experiments/` Experiment Store에
저장되며 `/experiments/ablations`와 내부 Evaluation UI에서 조회할 수 있습니다.

현재 개인정보보호법을 포함한 기존 공식 데이터와 회귀 baseline은 유지합니다.
향후 민법 중심의 ML 학습·검수 데이터는 별도 버전으로 추가하고, 이 runner의
법률 분야별 결과로 전체 성능과 민법 실험 성능을 구분합니다.
