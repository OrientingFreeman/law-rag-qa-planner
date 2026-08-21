# 민법 ML Experiment Readiness Gate

v4.25는 실제 모델 실행 전에 민법 ML 실험의 입력 조건을 고정합니다. 이 도구는
모델을 다운로드하거나 학습·평가하지 않으며 성능 metric을 만들지 않습니다.

```bash
python -m tools.plan_civil_ml_experiment \
  --prepared-manifest evaluation/training/civil_embedding_dataset/manifest.json \
  --evaluation-dataset evaluation/datasets/official_core_cases.json \
  --target-domain civil_transactions \
  --checkpoint evaluation/training/checkpoints/civil-retrieval-v1
```

## 확인하는 Gate

- prepared dataset의 train/validation hash와 1건 이상의 split
- `civil_transactions` 단일 domain 격리
- train/validation group 누수 부재
- 민법 domain의 gold-bearing retrieval 평가 문항 존재
- Sentence Transformers 선택 의존성 설치 여부
- fine-tuned checkpoint 존재 여부

## Experiment Matrix

- Pretrained Embedding
- Pretrained Embedding + Reranker
- Embedding Fine-tuning
- Fine-tuned Embedding
- Fine-tuned Embedding + Reranker

모든 데이터·평가·의존성 조건이 있으면 pretrained와 fine-tuning 단계는
`not_run`으로 표시됩니다. 이는 성능이 검증됐다는 뜻이 아니라 실행 가능한 상태라는
뜻입니다. checkpoint가 없으면 fine-tuned 조합만 `unavailable`로 남습니다.

준비 결과는 `civil_ml_readiness_gate` 실험으로 기존 Experiment Store에 저장됩니다.
`summary.metrics`는 항상 비어 있으며, 실제 수치는 이후 동일한 민법 평가세트에서
모델을 실행한 Retrieval Ablation 결과에만 기록합니다.
