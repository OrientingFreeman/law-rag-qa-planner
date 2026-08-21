from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class QueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=2, max_length=1000)
    domain: str = Field(default="all", min_length=1, max_length=100)
    top_k: int | None = Field(default=None, ge=1, le=50)
    as_of_date: date | None = None

    @field_validator("question")
    @classmethod
    def normalize_question(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("질문은 공백일 수 없습니다.")
        return normalized


class RetrievalResult(BaseModel):
    rank: int
    score: float
    lexical_score: float
    semantic_score: float
    citation: str
    document_id: str
    law_id: str | None = None
    article_no: str | None = None
    evidence_scope: Literal["fragment", "article", "paragraph"] | str = "fragment"
    sub_provisions: list[dict[str, str]] = Field(default_factory=list)
    text: str
    content_kind: str
    source_url: str | None = None
    retrieval_reason: Literal["direct", "related"] | str
    relation_score: float
    version_id: str
    effective_from: date | None = None
    matched_signals: dict[str, float] | None = None
    evidence_role: str = "supporting"
    issue_ids: list[str] = Field(default_factory=list)


class EvidenceStatus(BaseModel):
    level: Literal["insufficient", "partial", "usable"]
    message: str


class LegalIntentResponse(BaseModel):
    actions: list[str]
    subjects: list[str]
    objects: list[str]
    requested_outputs: list[str]
    qualifiers: list[str]
    subqueries: list[str]
    is_compound: bool
    ontology: dict[str, object] = Field(default_factory=dict)


class PrecedentEvidence(BaseModel):
    rank: int
    score: float
    precedent_id: str
    evidence_type: Literal["precedent"] = "precedent"
    court: str
    case_number: str
    decision_date: date
    case_name: str
    holding_summary: str
    reasoning_summary: str
    related_statutes: list[dict[str, str]] = Field(default_factory=list)
    source_url: str
    legal_context_note: str
    matched_terms: list[str] = Field(default_factory=list)


class EvidenceRouting(BaseModel):
    statute: bool = True
    precedent: bool = False
    precedent_reason: str = ""
    statute_sufficient: bool = False
    answer_basis: Literal["statute", "precedent"] = "statute"
    statute_precedent_alignment: dict[str, object] = Field(default_factory=dict)
    precedent_linked_statutes: list[dict[str, object]] = Field(default_factory=list)


class PrecedentValidation(BaseModel):
    valid: bool = False
    answer_supported: bool = False
    minimum_score: float = 0.35
    qualified_precedent_ids: list[str] = Field(default_factory=list)
    qualified_case_numbers: list[str] = Field(default_factory=list)
    source_urls: list[str] = Field(default_factory=list)
    support_method: str = "insufficient_precedent_score"


class RetrieveResponse(BaseModel):
    question: str
    domain: str
    results: list[RetrievalResult]
    abstain: bool
    evidence_status: EvidenceStatus
    legal_intent: LegalIntentResponse
    evidence_graph: dict[str, object] = Field(default_factory=dict)
    legal_reasoning_path: dict[str, object] = Field(default_factory=dict)
    precedent_evidence: list[PrecedentEvidence] = Field(default_factory=list)
    precedent_validation: PrecedentValidation = Field(default_factory=PrecedentValidation)
    evidence_routing: EvidenceRouting = Field(default_factory=EvidenceRouting)


class RunMetadata(BaseModel):
    service_version: str
    corpus_version: str
    generated_at: str
    latency_ms: float


class Confidence(BaseModel):
    score: float
    level: Literal["low", "medium", "high"]
    reasons: list[str]
    components: dict[str, float]


class QueryResponse(RetrieveResponse):
    prompt: str
    prompt_version: str
    reasoning_chain: list[ReasoningStep]
    graph_expansion: GraphExpansion
    metadata: RunMetadata


class GenerationUsage(BaseModel):
    input_tokens: int
    output_tokens: int
    total_tokens: int


class CitationValidation(BaseModel):
    valid: bool
    cited_articles: list[str]
    retrieved_articles: list[str]
    unsupported_articles: list[str]


class GroundingClaim(BaseModel):
    claim_id: str | None = None
    sentence: str
    supported: bool
    support_method: Literal["explicit_citation", "lexical_overlap", "unsupported"] | None = None
    supporting_citation: str | None = None
    supporting_citations: list[str] = Field(default_factory=list)
    supporting_evidence: list[dict[str, object]] = Field(default_factory=list)
    assigned_evidence: list[dict[str, object]] = Field(default_factory=list)
    semantic_labels: list[str] = Field(default_factory=list)
    semantic_label_ids: list[str] = Field(default_factory=list)
    ontology: dict[str, object] = Field(default_factory=dict)
    source_document_id: str | None = None
    source_excerpt: str | None = None
    evidence_scope: Literal["provision", "sub_provision"] | None = None
    overlap_score: float
    explicit_citation: bool
    cited_articles: list[str] = Field(default_factory=list)


class GroundingAudit(BaseModel):
    traceable_claim_count: int
    supported_evidence_count: int = 0
    multi_source_claim_count: int = 0
    evidence_role_counts: dict[str, int] = Field(default_factory=dict)
    assigned_evidence_count: int = 0
    contextual_evidence_count: int = 0
    semantic_assignment_coverage: float = 0.0
    fully_traceable: bool


class GroundingValidation(BaseModel):
    valid: bool
    claim_count: int
    supported_claim_count: int
    coverage: float
    unsupported_claims: list[str]
    claims: list[GroundingClaim]
    audit: GroundingAudit | None = None


class LegalBasisItem(BaseModel):
    citation: str
    law_id: str
    article_no: str
    scope: str
    role: Literal["primary", "supporting", "related"]
    summary: str


class AnswerStructure(BaseModel):
    answer_type: Literal["list", "requirement", "procedure", "period", "permission", "effect", "general"]
    conclusion: str
    key_points: list[str]
    legal_basis: list[LegalBasisItem]
    exceptions_and_cautions: list[str]
    facts_to_confirm: list[str]


class RelatedProvision(BaseModel):
    citation: str
    law_id: str
    article_no: str
    relationship: Literal["explicit_relation", "retrieval_support"]
    score: float
    summary: str


class RetrievalExplanation(BaseModel):
    selected: bool
    citation: str | None = None
    score: float | None = None
    evidence_scope: str | None = None
    reasons: list[str]
    signals: dict[str, float]


class ReasoningStep(BaseModel):
    step: int
    citation: str
    document_id: str
    law_id: str
    article_no: str
    reason: str
    relation: str
    score: float


class GraphExpansionItem(BaseModel):
    citation: str
    document_id: str
    law_id: str
    article_no: str
    relation: str
    relation_score: float


class GraphExpansion(BaseModel):
    enabled: bool
    expanded_count: int
    results: list[GraphExpansionItem]


class AnswerResponse(RetrieveResponse):
    answer: str
    display_answer: str | None = None
    generation_status: Literal["completed", "citation_invalid", "failed", "abstained"]
    provider: str
    model: str
    citation_validation: CitationValidation
    grounding_validation: GroundingValidation
    composition: dict[str, object]
    dual_output: dict[str, object] = Field(default_factory=dict)
    user_answer: dict[str, object] = Field(default_factory=dict)
    expert_report: dict[str, object] = Field(default_factory=dict)
    reasoning_trace: list[dict[str, object]] = Field(default_factory=list)
    graph_answer_structure: dict[str, object] = Field(default_factory=dict)
    legal_logic_tree: dict[str, object] = Field(default_factory=dict)
    logic_validation: dict[str, object] = Field(default_factory=dict)
    answer_skeleton: dict[str, object] = Field(default_factory=dict)
    rule_priority: list[dict[str, object]] = Field(default_factory=list)
    counter_reasoning: dict[str, object] = Field(default_factory=dict)
    logic_driven_reasoning_path: dict[str, object] = Field(default_factory=dict)
    rule_competition: dict[str, object] = Field(default_factory=dict)
    conflict_resolution: dict[str, object] = Field(default_factory=dict)
    decision_trace: dict[str, object] = Field(default_factory=dict)
    answer_composer: dict[str, object] = Field(default_factory=dict)
    sentence_citation_map: dict[str, object] = Field(default_factory=dict)
    missing_fact_detector: dict[str, object] = Field(default_factory=dict)
    practical_action_generator: dict[str, object] = Field(default_factory=dict)
    conditional_review: dict[str, object] = Field(default_factory=dict)
    legal_argument_graph: dict[str, object] = Field(default_factory=dict)
    multi_path_reasoning: dict[str, object] = Field(default_factory=dict)
    generation_error: str | None = None
    generation_request_id: str | None = None
    generation_usage: GenerationUsage | None = None
    prompt_version: str
    reasoning_chain: list[ReasoningStep]
    graph_expansion: GraphExpansion
    answer_structure: AnswerStructure
    related_provisions: list[RelatedProvision]
    retrieval_explanation: RetrievalExplanation
    confidence: Confidence
    metadata: RunMetadata


class DomainResponse(BaseModel):
    domain_id: str
    display_name: str
    laws: list[str]
    default_top_k: int


class LawResponse(BaseModel):
    law_id: str
    law_name: str
    document_type: str
    provision_count: int
    content_kinds: list[str]
    effective_from_min: date | None = None
    effective_from_max: date | None = None


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    version: str
    provision_count: int
    domain_count: int


class EvaluationRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_ids: list[str] | None = None
    limit: int | None = Field(default=None, ge=1, le=500)


class EvaluationReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_type: Literal["evaluation_case", "training_candidate"] = "evaluation_case"
    target_id: str = Field(min_length=1)
    decision: Literal["approve", "revise", "reject", "deprecate"]
    reviewer_id: str = Field(min_length=1, max_length=100)
    review_comment: str = Field(default="", max_length=2000)


class AgentRunRequest(QueryRequest):
    search_strategy: Literal["lexical", "semantic", "hybrid"] = "hybrid"
    query_rewrite: bool = True
    reranking: bool = True
    max_retries: int = Field(default=1, ge=0, le=2)
    retry_top_k_increment: int = Field(default=3, ge=1, le=20)
    abstention_policy: bool = True


class AgentRunResponse(BaseModel):
    run_id: str
    question: str
    domain: str
    config: dict[str, object]
    created_at: str
    completed_at: str | None = None
    status: str
    outcome: str | None = None
    stop_reason: str | None = None
    retry_count: int
    final_quality: str | None = None
    execution_trace: list[dict[str, object]]
    response: dict[str, object]


class ExperimentRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["baseline", "agent"]
    experiment_kind: Literal["rag", "retrieval", "embedding_training", "reranker", "llm_training"] = "rag"
    seed: int = Field(default=42, ge=0)
    baseline_experiment_id: str | None = None
    treatment_name: str | None = None
    retriever_version: str = "hybrid_v1"
    embedding_model: str = "current"
    reranker_model: str | None = None
    prompt_version: str = "answer_v22"
    search_strategy: Literal["lexical", "semantic", "hybrid"] = "hybrid"
    query_rewrite: bool = True
    reranking: bool = True
    case_ids: list[str] | None = None
    limit: int | None = Field(default=None, ge=1, le=100)
    max_retries: int = Field(default=1, ge=0, le=2)
    retry_top_k_increment: int = Field(default=3, ge=1, le=20)
    abstention_policy: bool = True


class ExperimentResponse(BaseModel):
    experiment_id: str
    executed_at: str
    dataset: dict[str, object]
    corpus: dict[str, object]
    code_version: str
    config: dict[str, object]
    model: dict[str, object]
    environment: dict[str, object]
    summary: dict[str, object]
    cases: list[dict[str, object]]


class ExperimentCompareRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    baseline_experiment_id: str
    candidate_experiment_id: str


class EvaluationSummary(BaseModel):
    total_cases: int
    passed_cases: int
    pass_rate: float
    top1_accuracy: float | None = None
    hit_at_k: float | None = None
    mean_recall_at_k: float | None = None
    mean_reciprocal_rank: float | None = None
    abstention_accuracy: float | None = None
    temporal_accuracy: float | None = None
    citation_accuracy: float | None = None
    average_latency_ms: float
    error_type_counts: dict[str, int] = {}


class EvaluationCaseResult(BaseModel):
    case_id: str
    question: str
    domain: str
    category: str = "direct_statute_retrieval"
    difficulty: str = "medium"
    expected_document_ids: list[str]
    retrieved_document_ids: list[str]
    expected_abstain: bool
    actual_abstain: bool
    top1_hit: bool
    hit_at_k: bool
    recall_at_k: float
    reciprocal_rank: float
    abstention_correct: bool
    temporal_valid: bool
    citation_valid: bool | None = None
    generation_status: str | None = None
    answer_point_coverage: float | None = None
    error_types: list[str] = []
    latency_ms: float
    passed: bool


class EvaluationRunResponse(BaseModel):
    version: str
    summary: EvaluationSummary
    metrics_by_category: dict[str, dict[str, object]] = {}
    metrics_by_difficulty: dict[str, dict[str, object]] = {}
    cases: list[EvaluationCaseResult]
