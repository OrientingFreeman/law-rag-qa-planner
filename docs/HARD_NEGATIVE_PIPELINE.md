# Hard-negative 후보와 사람 검수

## 목적

검색 벤치마크의 `wrong_top1`, `retrieval_miss`, `over_retrieval`을
학습 데이터 후보로 환류합니다. 검색 결과에 등장했다는 이유만으로 실제
negative라고 단정하지 않으며, 자동 후보는 항상 `review_required`로 생성됩니다.

```text
검색 벤치마크
→ Hard-negative 후보
→ 사람 검수
→ 승인된 후보
→ 버전이 지정된 학습 데이터셋
```

## 후보 생성

먼저 retrieval benchmark 원시 결과를 생성합니다.

```bash
python -m tools.run_retrieval_benchmark \
  --methods hybrid \
  --output evaluation/benchmarks/retrieval_latest.json

python -m tools.build_hard_negative_candidates \
  evaluation/benchmarks/retrieval_latest.json \
  --methods hybrid \
  --candidate-pool-version 0.1.0
```

후보는 query–positive 집합–hard negative 1개 단위로 생성합니다. 후보 ID는
case, method, positive와 negative ID의 canonical content로 결정합니다.
같은 결과를 다시 실행하면 기존 후보를 덧붙이지 않습니다. Positive와 negative가
겹치거나 corpus에서 실제 본문을 확인할 수 없는 후보도 저장하지 않습니다.

## 검수

개발 서버의 전용 페이지 `/internal/training-review`에서 Hard-negative 후보를 검수합니다.
기존 append-only review store를 재사용하되 `target_type=training_candidate`로
평가 사례 검수와 구분합니다.

- `approve`: training dataset export 대상
- `revise`: 추가 검토 필요
- `reject`: 관련 문서 등 negative로 부적절
- `deprecate`: 이후 사용 중단

승인·수정 요청·거절 중 하나를 저장한 후보는 처리 완료 상태로 기본 큐에서
제외됩니다. 검수 화면의 `처리된 후보도 표시`를 선택하면 결과와 검수 의견을
읽기 전용으로 다시 확인할 수 있습니다. 재검수 이력을 자동으로 덮어쓰지 않으며
기존 기록은 append-only로 유지합니다.

공개 데모에서는 기존 정책과 동일하게 검수 쓰기가 비활성화됩니다.

## 승인 데이터 내보내기

```bash
python -m tools.export_hard_negative_dataset \
  --dataset-version 1.0.0 \
  --output evaluation/training/hard_negative_dataset.jsonl
```

승인 이력이 없는 후보는 export되지 않습니다. 결과 manifest에는 dataset version,
record count, content SHA-256, review policy와 원천 candidate store를 기록합니다.
생성된 데이터는 아직 학습을 수행하지 않으며 다음 embedding fine-tuning 패치의
입력 경계만 제공합니다.

## 실제 후보 생성 검증

2026-08-19 공식 dataset v2.0.0의 hybrid Top-5 결과로 후보 생성기를 실행했습니다.
45개 source case에서 query–positive–negative 후보 135건이 생성됐습니다. 원본
case 기준 유형 발생 수는 `over_retrieval` 34건, `wrong_top1` 13건,
`retrieval_miss` 11건이었으며 한 case에 여러 유형이 동시에 존재할 수 있습니다.
135건은 검수 전 후보 수이며 승인 학습 데이터 수나 모델 성능을 의미하지 않습니다.
