# 검색 벤치마크

## 목적과 평가 범위

동일한 법령 corpus와 공식 평가 데이터에서 검색 방법만 바꾸어 품질과
응답시간을 비교합니다. 공식 데이터 61문항 중 정답 문서 또는 정답 조문이
있고 답변 유보 대상이 아닌 45문항만 retrieval benchmark에 포함합니다.
나머지 16개 안전성·경계 문항은 기존 Agent Evaluation에서 별도로 평가합니다.

`semantic_lite`는 실제 dense embedding이 아니라 dependency-free 문자 n-gram
cosine 기준선입니다. `pretrained_embedding`을 선택했을 때만 Sentence
Transformers 모델을 로드합니다.

## 지표

- Top-1 Accuracy
- Hit@K
- Recall@K
- MRR
- binary relevance nDCG@K
- 평균 query latency
- index build time

복수 조문이 정답인 경우 Recall@K와 nDCG@K가 모든 정답 근거의 발견 범위와
순위를 반영합니다. 같은 조문의 항·호 fragment가 여러 번 검색돼도 조문 단위
평가에서는 한 번만 계산합니다.

## v4.18.0 로컬 기준선

2026-08-19에 Python 3.12, 공식 dataset v2.0.0, 현재 법령 corpus, Top-K 5,
query rewrite 사용 조건으로 직접 실행했습니다.

| Method | Top-1 | Hit@5 | Recall@5 | MRR | nDCG@5 | 평균 query latency |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| BM25 | 37.78% | 66.67% | 66.67% | 0.4689 | 0.5172 | 28.8ms |
| semantic-lite | 46.67% | 73.33% | 73.33% | 0.5748 | 0.6148 | 33.0ms |
| hybrid | 46.67% | 75.56% | 75.56% | 0.5730 | 0.6184 | 265.6ms |

위 수치는 폐쇄형 로컬 평가 결과이며 pretrained embedding 성능이 아닙니다.
실행 환경의 부하에 영향을 받는 latency는 품질 지표와 분리해 해석해야 합니다.
BM25·semantic-lite의 query latency는 재사용 가능한 index build 이후를 측정하며
index build time을 별도 기록합니다. 현재 production hybrid는 문항별 후보 index
구성을 포함한 end-to-end latency이므로 수치를 직접적인 모델 추론 속도 차이로
해석하지 않습니다.

## 재현과 회귀 판정

```bash
python -m tools.run_retrieval_benchmark \
  --methods bm25 semantic_lite hybrid \
  --top-k 5 \
  --fail-under-hit-at-k 0.60 \
  --fail-under-mrr 0.45
```

실행 결과에는 dataset/corpus SHA-256, code version, seed, method와 embedding
model ID가 함께 저장됩니다. 실제 pretrained embedding 결과는 해당 모델을
실행한 후에만 별도 비교표에 추가합니다.
