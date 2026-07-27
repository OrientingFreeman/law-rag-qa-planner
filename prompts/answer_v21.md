{system_prompt}

[사용자 질문]
{query}

[Legal Intent Planner]
{legal_intent}

[법령 추론 경로]
{reasoning_chain}

## 권위적 법적 추론 경로
{legal_reasoning_path}

위 경로는 참고자료가 아니라 답변 생성 계약이다. 단계 순서, 쟁점 순서, 단계별 허용 인용을 변경하거나 건너뛰지 않는다.

[Structured Legal Composer]
{composition_plan}

[검색 근거]
검증된 graph node만 답변 근거로 사용합니다.
{evidence}

[작성 원칙]
- 첫 문단에서 질문에 대한 직접 결론을 2문장 이내로 제시한다.
- 각 쟁점은 추론 경로의 순서대로 별도 소제목으로 작성한다.
- 각 쟁점에서 기본 규칙 → 요건 → 예외·금지·제한 → 보충 절차 → 위반 효과 순서를 따른다.
- 쟁점 전이가 있으면 "왜 다른 쟁점이 추가 적용되는지"를 한 문장으로 명시한다.
- 법적 의무·허용·금지·효과를 진술하는 문장은 해당 추론 단계의 허용 인용을 붙인다.
- 검색 근거에 없는 조문 또는 사실을 추가하지 않는다.
- 근거로 확정할 수 없는 사실은 "추가 확인 필요"로 분리한다.
- 체크리스트만 나열하지 말고 법률적 판단 문장을 먼저 작성한 뒤 실무 조치를 제시한다.

[출력 형식]
결론
...

쟁점별 법적 판단
### 1. [쟁점]
- 적용 규칙: ... (허용 인용)
- 요건·예외·제한: ... (허용 인용)
- 다른 쟁점과의 관계: ... (허용 인용)

실무상 조치
- ... (허용 인용)

근거 조문
- ...

추가 확인 사실
...


[계약 검증 경고]
출력 섹션명은 위 형식을 정확히 사용한다. "판단 순서", "실무 체크리스트", "요약 답변" 같은 대체 헤더를 사용하지 않는다.


[표현 제한]
답변의 법적 판단 순서와 인용 선택은 시스템의 Answer Planner가 결정한다. 모델은 제공된 계획과 근거를 벗어나 새로운 쟁점, 요건, 예외 또는 인용을 추가하지 않는다.


[Sentence Planner Contract]
최종 답변의 의미 단위는 서버가 생성한 sentence plan과 citation binding을 변경하지 않는다. 새로운 법적 주장이나 인용을 추가하지 않는다.


## v17 Auditable Reasoning Contract
- Preserve every planned reasoning step and issue transition.
- Do not add claims outside the sentence plan or citation bindings.
- The final answer must remain traceable to reasoning steps, transitions, citations, and evidence nodes.


## Dual Output Contract
최종 법적 주장과 인용은 Sentence Planner가 확정한다. 모델은 일반 사용자용 표현과 전문가용 감사 추적을 위한 새로운 사실·조문·판단을 추가하지 않는다.


## Legal Logic Engine
답변은 사전에 검증된 Legal Logic Tree와 Answer Skeleton의 순서를 따라야 한다. 새로운 법적 명제나 근거를 임의로 추가하지 말고, Issue → Rule → Exception/Requirement → Consequence → Conclusion 구조를 자연어로 표현한다.

## Logic-Driven Reasoning Contract
- Treat the validated Legal Logic Tree as the authoritative downstream reasoning source.
- Preserve issue order, rule priority, limitations, consequences, and source citations.
- Where an exception or limitation is present, state the primary interpretation and the limiting interpretation without inventing unsupported alternatives.

- 규칙 충돌 해결 단계가 제공되면 채택·배제 근거를 반영해 결론을 구성합니다.
