# 4.11.0 Legal Consistency & Scenario Simulation

- Added deterministic Legal Consistency Checker for graph integrity, recommendation alignment, status/readiness mismatches, switch-condition integrity, and statutory-basis isolation.
- Added Scenario Simulation that projects path status, confidence, recommendation score, and recommendation changes when path-specific missing facts are assumed true.
- Exposed `consistency_report` and `scenario_simulation` in the multi-path API contract and compact summary tool.
- Bumped service version to 4.11.0 and multi-path reasoning contract to 1.8.

## 4.9.1 - Semantic Decision Refinement

- Separate strategy comparison semantics into `advantages`, `requirements`, and `risks` while preserving legacy trade-offs.
- Generate switching conditions from each alternative path's differentiating facts rather than shared baseline facts.
- Add Korean fact labels and expose `differentiating_fact_ids` for auditable transition rules.
- Bump multi-path reasoning to 1.6, strategy layer to 1.3, strategy comparison to 1.1, and decision support to 1.1.

## 4.9.0 - Legal Decision Support Contract

- Preserve `strategy_comparison` in compact strategy verification output.
- Add deterministic `decision_support` with selected-strategy rationale, rejected alternatives, trade-off summary, switching conditions, and required next facts.
- Bump multi-path reasoning to 1.5 and strategy layer to 1.2.
- Add regression coverage for API-independent decision-support generation and compact serialization.

## 4.8.0 - Ranking Transparency & Comparative Explanation

- Align non-selected path ranking with recommendation_score, then confidence.
- Expose the conservative recommendation-policy override in ranking_mode.
- Generate non-recommendation reasons for every alternative path.
- Add strategy_comparison for the top three alternatives.
- Preserve comparison data in the compact multi-path summary.

## 4.7.1 - Strategy Output Verification Contract

- Added `tools/summarize_multi_path.py` for compact, strategy-aware API verification output.
- Compact summaries now retain `confidence`, `recommendation_score`, `recommendation_reasons`, and `strategy_profile`.
- Added API-level regression coverage proving strategy fields survive final response serialization.
- Clarified that v4.7 strategy fields were present in the full response; prior compact output omitted them.

# 4.6.0 - Path Evaluation Refinement

- Prioritize full cumulative paths for compound legal questions.
- Add statutory-basis-specific required and missing facts for cross-border transfer paths.
- Score alternative paths independently using branch evidence, context, missing-fact ratio, and dependencies.
- Add concrete processing-delegation + cross-border-basis cumulative paths.
- Preserve full path titles and expose separately truncated `display_title` values.
- Add direct sub-provision citations and recommendation rationale.

## 4.0.0 - Legal Logic Engine

- Added a deterministic `LegalLogicTree` between the evidence/reasoning layers and the sentence planner.
- Added explicit Issue, Rule, Requirement, Exception, Consequence, and Conclusion nodes with traceable citations and source rule IDs.
- Added logic validation for missing rules/conclusions, orphan exceptions, ungrounded consequences, and dangling edges.
- Added rule-priority output that promotes exception rules ahead of primary and supporting rules.
- Added an answer skeleton that controls section order before sentence-plan rendering.
- Exposed `legal_logic_tree`, `logic_validation`, `answer_skeleton`, and `rule_priority` in the API and expert report.
- Updated prompt version to `answer_v19` and package version to `4.0.0`.
- Regression suite: 114 tests passed.

## 3.8.0 - Dual Output and Graph-driven Presentation

- Added deterministic dual output with separate user and expert representations.
- Added graph-driven answer structure derived from the bound sentence plan.
- Added API-level reasoning trace with sentence, issue, citation, evidence node, and rendered hash provenance.
- Preserved the existing auditable reasoning engine while exposing user-facing and expert-facing views.
- Updated prompt version to `answer_v18` and package version to `3.8.0`.

## 3.5.0

- Add a deterministic `AnswerPlan` layer that converts legal reasoning steps and issue transitions into ordered sections and sentence nodes.
- Serialize the final legal answer directly from the plan, preventing the LLM from changing issue order, omitting transitions, or selecting new citations.
- Expose sentence-level provenance through `composition.answer_plan`, including source step, source transition, issue ID, and allowed citations.
- Add `answer_v15`; the model is limited to expression and may not add legal issues, rules, exceptions, or citations.
- Preserve the v3.4 contract validator as a compatibility and audit layer.
- Add v3.5 regression tests for step ordering, transition serialization, and sentence-level provenance.

## 3.4.1

- Add deterministic answer-contract validation and repair when an LLM returns legacy headings, wrong section order, or omits required issue-transition explanations.
- Add `answer_v14` and expose initial/final answer-contract validation in composition metadata.
- Restrict same-article structural edges to later-paragraph → earlier-rule direction.
- Classify explicit later-paragraph prohibitions as `prohibition_of` and delegation/supplement paragraphs as `supplements`.
- Treat an empty ontology issue set as insufficient legal grounding: graph coverage is `0.0`, `abstain` is true, and answer generation is skipped.
- Extend grounding metadata recognition to the v3.4 structured answer headings.
- Add dedicated v3.4.1 regression tests.

## 3.4.0

- Make Evidence Graph nodes the authoritative evidence set for query and answer generation.
- Add `answer_v13`, which treats the legal reasoning path as a binding answer-generation contract rather than advisory context.
- Add issue-transition relations such as `triggers_additional_rule` and `co_applies_with`.
- Split broad exception/limitation edges into `exception_of`, `prohibition_of`, and `supplements` semantics.
- Add answer-contract metadata containing section order, step-order enforcement, transition requirements, and allowed citations.
- Expose `authoritative_evidence_ids` for generation auditing.
- Add v3.4 regression tests while preserving 8/8 benchmark performance.

## 3.3.0

- Replace adjacent-only evidence links with typed legal relations based on explicit article references, same-article structure, statutory sanctions, and subordinate legislation.
- Add relation confidence, shared issue IDs, and human-readable legal reasons to every evidence edge.
- Add deterministic issue-centric `legal_reasoning_path` output covering primary rules, exceptions or limitations, supplementary rules, and legal consequences.
- Feed the legal reasoning path into the new `answer_v12` grounded-answer prompt.
- Correct branch-article parsing for citations such as `제28조의8`.
- Add v3.3 regression tests while preserving benchmark performance.

## 3.2.1

- Preserve ontology and issue-coverage metadata across evidence aggregation.
- Prevent generic descendant aliases such as `목적` from establishing unrelated legal-act issues.
- Re-annotate final paragraph/article evidence units without changing calibrated retrieval scores.
- Exclude evidence nodes that cannot connect to a requested issue, while retaining explicit graph-related results.
- Add regression coverage for ontology metadata preservation and generic-alias false positives.

## 3.2.0
- Added calibrated evidence graph ranking, issue coverage, evidence roles, and non-saturating scores.

## 3.0.0

- Added deterministic semantic labels for legal claims and evidence units.
- Added `assigned_evidence` to separate semantically assigned legal authority from preserved contextual evidence.
- Added assignment reasons and confidence values for every evidence candidate.
- Added semantic-assignment audit metrics without dropping cited-article evidence.
- Reclassified same-article but semantically unrelated sibling provisions as `contextual`.

## 2.9.0 - Evidence Role Taxonomy

- Preserved complete multi-evidence output while classifying each source by legal function.
- Added `primary`, `parent`, `child`, `implementing_regulation`, `supporting`, and `related` evidence roles.
- Added instrument classification for acts, enforcement decrees, and enforcement rules.
- Added grounding audit counts by evidence role without deleting or truncating cited evidence.
- Reclassified provenance graph rule roots as parent evidence while keeping sub-provisions primary.

## 2.8.0 - Hierarchical Provenance Graph

- Added deterministic `EvidenceNode` trees connecting checklist actions to rule, item, and sub-item evidence.
- Added `composition.presentation.provenance_graph` node/edge audit metadata.
- Added plural `supporting_citations` and structured `supporting_evidence` to grounding claims.
- Preserved legacy singular grounding fields for backwards compatibility.

## 2.7.0

- Converted verbose statutory subparagraphs into deterministic, action-oriented checklist labels.
- Added concise mappings for overseas-transfer consent, legal basis, disclosure, notice, certification, safeguards, and equivalent-protection checks.
- Added concise mappings for outsourcing purpose, scope, security controls, re-outsourcing, and liability terms.
- Preserved exact source text, citations, document IDs, and stable trace IDs in presentation metadata.
- Added regression coverage to prevent statutory text dumps from returning to the user-facing checklist.

## 2.6.1

- Fixed the grounding fallback boundary so an answer with `coverage == 0.80` but `valid == false` cannot bypass deterministic evidence fallback.
- Made fallback activation depend explicitly on grounding validity as well as citation validity and minimum coverage.
- Excluded standard legal-answer limitation and case-specific review notices from legal claim scoring.
- Restored the compact `결론 → 판단 순서 → 실무 체크리스트 → 근거 조문` presentation whenever any unsupported legal claim remains.
- Preserved v2.6.0 claim provenance and presentation trace metadata.

## 2.6.0

- Added claim-level grounding provenance with stable claim IDs, support methods, exact citations, source document IDs, and source excerpts.
- Fixed supported claims that could previously expose `supporting_citation: null` when explicit citations matched retrieved articles.
- Added grounding audit summaries with traceable claim counts and a `fully_traceable` flag.
- Added stable presentation trace IDs and checklist-to-source evidence mappings under `composition.presentation`.
- Added regression tests for complete claim audit trails and presentation provenance.

## 2.5.0

- Added deterministic compact requirement extraction for evidence fallback answers.
- Separated user-facing `display_text` from exact `source_text` and retained source checklist metadata.
- Rendered actionable checkbox items with citations instead of repeating full statutory sentences.
- Updated the default generation prompt contract to `answer_v11`.

## 2.4.0

- Added an action-oriented answer presentation layer for compound legal questions.
- Reworked evidence fallback into conclusion, decision order, practical checklist, legal basis, and facts-to-confirm sections.
- Added deterministic presentation metadata under `composition.presentation`.
- Updated the default generation prompt contract to `answer_v10`.
- Added regression tests for action grouping, readability, citation validity, and grounding preservation.

# Changelog

## 2.3.0

- Added Citation Scope Manager with direct, referenced, and graph citation provenance.
- Allowed article references that appear inside retrieved official evidence text, preventing false citation failures such as `제32조의2` inside `제28조의8`.
- Preserved rejection of citations absent from all evidence scopes.
- Added citation scope diagnostics to validation responses.
- Updated the default generation prompt contract to `answer_v9`.
- Added three regression tests for referenced citations, unseen citations, and fallback validation.

## 2.2.0

- Added a shared Korean statute article parser that preserves branch articles such as `제28조의8`.
- Fixed citation validation falsely truncating `제28조의8` to `제28조`.
- Unified citation repair, validation, and grounding extraction on the canonical article parser.
- Improved evidence fallback readability with article headings and exact evidence bullets.
- Prevented unrelated graph-expanded provisions from automatically flooding fallback answers.
- Added regression tests for branch-article parsing, citation validation, and readable fallback output.

## 2.1.0

- Added Structured Legal Composer rule cards and an explicit allowed-citation list.
- Added Prompt v7 to constrain generation to evidence-backed rules.
- Added safe repair for uniquely shortened article citations such as 제28조 → 제28조의8.
- Added deterministic evidence fallback when citation validation fails or grounding coverage is below 0.80.
- Added composition diagnostics to `/answer`, including rule plans, repairs, and fallback decisions.
- Refined grounding validation to exclude headings and explicit limitation/meta statements from legal-claim scoring.
- Added three regression tests for citation repair, fallback composition, and composer response metadata.

## 2.0.0

- Added deterministic Legal Intent Planner for actions, requested outputs, qualifiers, and compound-question detection.
- Added multi-query retrieval and reciprocal-rank fusion for compound legal questions.
- Added explicit article-anchor scoring for planner-generated statutory queries.
- Added `legal_intent` to retrieve, query, and answer responses.
- Added Prompt v6 with a Legal Intent Planner section.
- Added regression tests for compound privacy-law retrieval.

## 1.6.0

- `/answer` 기본 프롬프트를 `answer_v2`로 변경하고 결론, 법적 근거, 예외·주의사항, 추가 확인 사실 순서로 답변하도록 강화했습니다.
- LLM 공급자와 독립적인 `answer_structure` 응답 필드를 추가했습니다.
- 검색 결과 중 주 근거를 제외한 고유 조문을 `related_provisions`로 제공합니다.
- Top-1 선정 이유와 lexical, semantic, title, coverage, relation 신호를 `retrieval_explanation`으로 제공합니다.
- 구조화 법률 QA 응답에 대한 회귀 테스트를 추가했습니다.

## 1.5.0

- Added official-corpus evaluation using stable `law_id + article_no` expectations.
- Added domain query rules for common legal intents without coupling evaluation to paragraph/item IDs.
- Added article-title scoring and included titles in semantic-lite retrieval.
- Penalized chapter/section heading-only records and unrelated sanction provisions.
- Added hierarchy-aware ranking and capped duplicate fragments from the same article in Top-K.
- Added title and term-coverage signals to retrieval responses.
- Added eight official-corpus regression cases covering privacy, electronic finance, labor, and civil law.

# Changelog

## 0.7.0 - Question UI

- FastAPI 루트 경로(`/`)에 질문 입력형 웹 데모 추가
- 법률 질문, 검색 도메인, 결과 개수 선택 기능 추가
- `/domains`를 이용한 도메인 선택지 자동 구성
- `/query` 결과의 관련 조문, 원문, 검색 점수, 시행일, 공식 출처 표시
- 직접 근거와 관련 근거 구분 표시
- 근거 상태(활용 가능·일부 확보·부족) 표시
- 생성형 AI 연결용 grounded prompt 접이식 패널 추가
- 모바일 반응형 레이아웃 추가
- 기존 Swagger UI(`/docs`)와 API 엔드포인트 유지
- 애플리케이션 버전 0.7.0으로 갱신

## 0.9.0
- JSON 기반 회귀 평가셋 및 평가 CLI 추가
- Top-1, Hit@K, Recall@K, MRR 측정
- abstention 정확도와 시행일 적합성 검증
- 생성 답변 인용 정확도 측정
- 사례별 latency 및 JSON 리포트 출력
- `--fail-under` 회귀 게이트 추가

## 0.9.0

- FastAPI 루트에 내부 검증용 Web UI 연결
- 질의, 검색, 생성 답변 및 인용 검증 통합 화면 추가
- 평가 실행 및 최신 리포트 API 추가
- 평가 지표 카드와 실패 사례 필터 UI 추가
- 평가 데이터셋 및 리포트 경로 환경변수 지원
- API/UI 통합 테스트 추가

## 1.0.0
- Added confidence scoring with explainable reasons.
- Added corpus/service/generation metadata and latency measurement.
- Added retrieval signal details for lexical, semantic, and relation scores.
- Moved grounded prompts to versioned Markdown templates.
- Added JSONL execution logs for answer requests.
- Formalized deterministic and OpenAI-compatible provider configuration.

## 1.1.0

- Added a non-root production Docker image with an HTTP healthcheck.
- Added Docker Compose configuration with persistent logs and evaluation reports.
- Added GitHub Actions CI for Python 3.10/3.12 tests and regression evaluation.
- Added Docker build, health, and `/answer` smoke tests to CI.
- Updated service and package version metadata to 1.1.0.

## 1.2.0

- Added a dedicated OpenAI Responses API provider.
- Kept generic OpenAI-compatible servers on Chat Completions.
- Added bounded retries for rate limits, transient HTTP errors, connection failures, and timeouts.
- Added strict environment configuration validation.
- Added provider request IDs and normalized token usage to `/answer` responses and JSONL logs.
- Added mocked provider integration tests without requiring external API calls.
- Removed duplicated LLM settings from `.env.example` and updated version references.

## 1.3.0

- Added `python-dotenv` and automatic `.env` loading.
- Preserved OS/container environment precedence with `override=False`.
- Added optional `LAW_RAG_ENV_FILE` support.
- Added configuration loading tests and secret-file exclusions.
- Updated package, API metadata, UI, and provider user-agent versions.

## 1.4.0

- Added manifest-based multi-law synchronization for the official Korean law API.
- Added normalized per-law cache files and explicit offline cache fallback.
- Added an example manifest covering five portfolio domains.
- Added atomic corpus/cache writes and credential non-persistence tests.

## 1.4.1

- Fixed official law search parsing for the real lowercase `<law>` response element and Korean field tags.
- Added parsing for law name, law ID, MST, current/history code, effective date, and detail link with CDATA/whitespace normalization.
- Added search metadata validation for `resultCode`, `resultMsg`, and `totalCnt`, plus parse diagnostics when candidates exist but cannot be normalized.
- Changed name-based body retrieval to use the resolved `법령일련번호` as the `MST` parameter, with ID fallback for legacy fixtures.
- Redacted `OC` credentials from provenance URLs, detail links, transport errors, and diagnostics.
- Added regression coverage matching the production National Law Information Center XML structure.

## 1.4.2

- Isolated deterministic unit and regression tests from the mutable production corpus by adding `tests/fixtures/legal_corpus.json`.
- Changed manifest synchronization to atomically replace the output with the current manifest snapshot by default, preventing synthetic/demo records and removed laws from remaining in production retrieval.
- Added `--merge-output` for callers that explicitly need the previous append/update behavior.
- Added regression tests for replacement and opt-in merge behavior.

## 1.5.1

- 동일 법률·조문·항의 호/목 검색 조각을 하나의 evidence unit으로 집계
- 대표 인용을 조/항 단위로 정규화하고 `evidence_scope` 제공
- 집계된 하위 호/목을 `sub_provisions`로 반환
- `/query` 및 `/answer` 프롬프트에 전체 형제 조각을 함께 전달하여 목록형 법률 질문의 누락 완화
- Top-K를 고유 evidence unit 기준으로 적용


## 1.6.1

- 질문을 목록형·요건형·절차형·기간형·허용/금지형·효과/책임형으로 분류
- 집계된 하위 항·호·목에서 `key_points`를 직접 추출하는 grounded answer structure 추가
- 개인정보 처리방침 등 질문 맥락별 `facts_to_confirm` 생성
- 관련 조문에 최소 점수·내용 중첩·법령 계열 필터 적용
- grounded prompt를 `answer_v3`로 갱신

## 1.7.0

- Added persistent JSONL failure-case logging for failed evaluation cases.
- Added failure diagnosis codes and expected-versus-retrieved evidence snapshots.
- Added `python benchmark.py` and `python -m law_rag.benchmark` benchmark commands.
- Added human-readable and JSON summaries, report output, failure logging, and CI-friendly exit thresholds.

## 1.8.0
- Added sentence-level grounding validation for legal claims.
- Added confidence score components for retrieval, evidence coverage, citation validity, and grounding coverage.
- Added natural-language citation normalization and answer_v4 prompt.

## 1.9.0

- Added article-level `LawGraph` built from `related_article_ids` and explicit statutory references in provision text.
- Added bounded multi-hop graph expansion with direct/related evidence separation.
- Added `reasoning_chain` and `graph_expansion` fields to `/query` and `/answer` responses.
- Added `answer_v5` prompt with legal-rule sequencing and graph-evidence safeguards.
- Added graph expansion and reasoning-chain regression tests.
## 3.1.0 - Legal Ontology Layer

- Extracted legal semantic concepts from the grounding validator into a shared `law_rag.ontology` module.
- Added stable concept IDs, Korean labels, aliases, categories, parent concepts, related concepts, and legal-action mappings.
- Added deterministic ontology matching, parent/related expansion, relation validation, and serializable concept graphs.
- Added ontology analysis to `legal_intent` so planning and downstream stages share one normalized vocabulary.
- Added concept and relation annotations to claim-level and evidence-level grounding audit rows.
- Preserved the v3.0 semantic evidence-assignment contract and backwards-compatible semantic label fields.

## 3.1.1 - Ontology-Constrained Evidence Selection

- Added ontology-aware reranking for legal issue alignment.
- Added legal-instrument-aware article anchors so an Act article number does not automatically promote the same-numbered Enforcement Decree article.
- Added narrow-scope mismatch penalties for special-regime provisions not named in the question.
- Added planner expansion retrieval for single-issue definition questions.
- Added compound concept coverage selection and overseas-cloud detection as a cross-border-transfer signal.
- Added regression tests for Act/Decree article collisions, definition intent, and ontology-constrained reranking.

## 3.6.0 - Sentence Planner and Citation Binder

- Added deterministic sentence-level answer planning with stable sentence IDs.
- Added citation bindings from every cited sentence to source document and evidence node IDs.
- Added rendered sentence hashes and exact plan-to-answer validation.
- Changed planner composition mode to `sentence_plan_bound` and prompt version to `answer_v16`.
- Prevented unbound citations and out-of-order planned sentences from passing validation.

## 3.7.0 - Auditable Reasoning Verifier

- Added a reasoning verifier that checks step, transition, issue, section, and step-order completeness against the legal reasoning path.
- Added semantic citation coverage metrics for sentence-to-citation and sentence-to-evidence-node bindings.
- Added a weighted reasoning score independent from retrieval confidence.
- Added an explainability report with sentence-level provenance and rendered hashes.
- Updated prompt version to `answer_v17` and package version to `3.7.0`.

## 4.1.0
- Legal Logic Tree를 downstream planner의 authoritative reasoning source로 승격했습니다.
- Logic Tree에서 정규화된 `logic_driven_reasoning_path`를 생성합니다.
- 검색 근거 안에서만 대안 해석과 제한 규칙을 비교하는 `counter_reasoning`을 추가했습니다.
- API와 expert report에 logic-driven path 및 counter reasoning을 노출합니다.

## 4.2.0
- 쟁점별 적용 규칙을 후보 집합으로 구성하는 `rule_competition`을 추가했습니다.
- 예외·제한 규칙과 기본 규칙의 우선순위를 판정하는 `conflict_resolution`을 추가했습니다.
- 채택·배제된 규칙과 근거를 순서대로 남기는 `decision_trace`를 추가했습니다.
- 충돌 해결 결과를 `logic_driven_reasoning_path`의 최종 판단 단계로 주입해 Planner가 결정 이후에 결론을 구성하도록 변경했습니다.
- API 및 expert report에 규칙 경쟁, 충돌 해결, 결정 추적 정보를 노출합니다.

## 4.3.0

- Added a structured Answer Composer that classifies planned sentences into Fact, Rule, Application, and Conclusion roles.
- Added a stable sentence-level citation map with evidence-node bindings and rendered hashes.
- Added a concrete Missing Fact Detector for transaction details that materially affect legal analysis.
- Added a source-bound Practical Action Generator and connected it directly to the final answer plan.
- Exposed `answer_composer`, `sentence_citation_map`, `missing_fact_detector`, and `practical_action_generator` in API responses and expert reports.
- Updated service and prompt versions to 4.3.0 / answer_v22.


## 4.4.0 - Legal Argument Graph

- Added a deterministic Legal Argument Graph above retrieval and logic-tree layers.
- Connected question, issue, rule, evidence, fact, application, counterargument, conclusion, and missing-fact nodes.
- Added typed relations including raises, supports, governs, addresses, attacks, limits, justifies, and defeated_for.
- Added graph validation for dangling edges and sentence-level evidence support.
- Exposed `legal_argument_graph` in `/answer`, composition output, and expert reports.
- Updated package version to 4.4.0 and prompt contract version to answer_v22.

## 4.5.0
- Added deterministic Multi-Path Reasoning over the Legal Argument Graph.
- Separates alternative statutory bases from cumulative multi-issue compliance paths.
- Exposes path-level status, missing facts, evidence provenance, ranking and validation.
- Added `multi_path_reasoning` to `/answer`, expert output and composition metadata.

## 4.6.0 - Confidence Decomposition & Path Ranking

- Added decomposed path confidence: evidence strength, fact completeness, issue coverage, directness, conflict-selection support, and context fit.
- Aligned public path rank with `recommended_path_id`; preserved analytical ordering as `confidence_rank`.
- Prevented unresolved context signals from selecting a specific statutory basis prematurely.
- Added candidate pruning with a maximum of three concrete cumulative-basis routes while retaining dependency paths.
- Added pruning metadata, ranking mode, confidence model metadata, and recommendation markers.

## 4.10.0 - Productization Readiness: Reasoning Quality & Failure Analysis

- Added a reasoning-quality contract independent from path confidence.
- Scores evidence quality, fact completeness, issue coverage, structural integrity, decision clarity, and strategy differentiation.
- Added a failure analyzer that converts weak quality dimensions into severity-ranked remediation actions.
- Exposed `reasoning_quality` and `failure_analysis` in the multi-path API and compact audit summary.
- Corrected Korean particles in generated strategy-switch conditions.
