# 재현 가능한 임베딩 학습

## 범위

이 파이프라인은 사람 검수에서 승인된 hard-negative만 법률 검색 임베딩
학습에 사용합니다. 자동 발견된 실패를 검증 없이 학습하거나, 로컬 기본 테스트에서
외부 모델을 다운로드하지 않습니다.

## 데이터 흐름

```text
검색 벤치마크
  -> Hard-negative 후보
  -> 사람 검수
  -> 승인된 버전 데이터셋
  -> Manifest·충돌 검증
  -> 그룹 누수를 방지한 학습·검증 triplet
  -> 실행 계획 또는 명시적 미세조정
  -> 체크포인트
  -> 검색 벤치마크 비교
```

split 기준은 `source.dataset_id + source.case_id`이며 case ID가 없으면 query hash를
사용합니다. 따라서 같은 질문에서 여러 retrieval method가 만든 후보가 train과
validation으로 갈라지는 누수를 방지합니다. seed와 split hash가 manifest에 남으므로
같은 입력과 설정에서 동일 split을 재생성할 수 있습니다.

## 실행

먼저 검수 페이지 `/internal/training-review`에서 후보를 승인하고 versioned dataset을
export합니다.

```bash
python -m tools.export_hard_negative_dataset --dataset-version 1.0.0
python -m tools.prepare_embedding_training --seed 42 --validation-ratio 0.2
python -m tools.train_embedding_model
```

마지막 명령의 기본값은 plan-only입니다. dataset과 설정을 검증하고
`evaluation/experiments/exp_embedding_*.json`을 만들지만 모델을 다운로드하거나
checkpoint를 생성하지 않습니다.

실제 학습은 선택 의존성을 설치하고 명시적으로 실행합니다.

```bash
pip install -e '.[ml]'
python -m tools.train_embedding_model --execute \
  --checkpoint-dir evaluation/training/checkpoints/legal-retrieval-v1
```

기본 loss는 query-anchor, gold-positive, reviewed-hard-negative로 구성된 TripletLoss입니다.
모델·loss 변경은 동일 dataset version과 seed를 유지한 treatment로 기록해야 합니다.

## 평가 원칙

학습 완료 자체는 retrieval 성능 개선의 증거가 아닙니다. checkpoint는 기존 embedding과
동일 evaluation set에서 Recall@K, Hit@K, MRR, nDCG@K, Top-1 Accuracy, latency로
비교합니다. 실제 benchmark를 실행하기 전에는 실험 기록의 metrics가 빈 객체로 남습니다.
