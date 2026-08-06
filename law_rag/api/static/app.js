const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => document.querySelectorAll(selector);
const form = $("#query-form");

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function displayEvidenceLevel(level) {
  return { usable: "근거 충분", partial: "근거 일부", insufficient: "근거 부족" }[level] || level;
}

const ANSWER_SECTION_LABELS = new Map([
  ['결론', '결론'],
  ['요약 답변', '결론'],
  ['쟁점별 법적 판단', '상세 판단'],
  ['판단 기준', '판단 기준'],
  ['사안 적용', '사안 적용'],
  ['유보사항', '유보사항'],
  ['실무상 조치', '핵심 체크리스트'],
  ['추가 확인 사실', '추가 확인 사항'],
  ['추가 확인 사항', '추가 확인 사항'],
  ['답변 한계', '답변 한계'],
  ['판례상 해석', '판례상 해석'],
  ['적용상 주의사항', '적용상 주의사항'],
  ['근거 판례', '근거 판례'],
  ['근거 조문', '근거 조문'],
]);

function splitAnswerSections(text) {
  const sections = [];
  let current = { title: '결론', lines: [] };
  for (const rawLine of String(text || '').split(/\r?\n/)) {
    const line = rawLine.trim();
    if (ANSWER_SECTION_LABELS.has(line)) {
      if (current.lines.some(Boolean)) sections.push(current);
      current = { title: ANSWER_SECTION_LABELS.get(line), lines: [] };
      continue;
    }
    current.lines.push(rawLine);
  }
  if (current.lines.some((line) => line.trim())) sections.push(current);
  return sections;
}

function renderStructuredAnswer(text) {
  const container = $('#answer-content');
  container.innerHTML = '';
  const sections = splitAnswerSections(text).filter((section) => section.title !== '근거 조문');
  if (!sections.length) {
    const paragraph = document.createElement('p');
    paragraph.textContent = text || '(생성된 답변이 없습니다.)';
    container.append(paragraph);
    return;
  }
  sections.forEach((section) => {
    const block = document.createElement('section');
    block.className = `answer-section answer-${section.title === '결론' ? 'conclusion' : 'detail'}`;
    const heading = document.createElement('h4');
    heading.textContent = section.title;
    block.append(heading);
    const lines = section.lines.map((line) => line.trim()).filter(Boolean);
    const bulletLines = lines.filter((line) => /^[-•]|^\d+[.)]/.test(line));
    if (bulletLines.length === lines.length && lines.length) {
      const list = document.createElement('ul');
      lines.forEach((line) => {
        const item = document.createElement('li');
        item.textContent = line.replace(/^[-•]\s*/, '').replace(/^\d+[.)]\s*/, '');
        list.append(item);
      });
      block.append(list);
    } else {
      const paragraph = document.createElement('p');
      paragraph.textContent = lines.join('\n');
      block.append(paragraph);
    }
    container.append(block);
  });
}

function appendReviewText(parent, tagName, text, className = '') {
  const element = document.createElement(tagName);
  if (className) element.className = className;
  element.textContent = text || '';
  parent.append(element);
  return element;
}

function renderConditionalReview(data) {
  const panel = $('#conditional-review-panel');
  const review = data.conditional_review || {};
  const issueReviews = Array.isArray(review.issue_reviews) ? review.issue_reviews : [];
  if (!review.enabled || !issueReviews.length) {
    panel.hidden = true;
    $('#review-issue-list').innerHTML = '';
    return;
  }

  panel.hidden = false;
  const statusBadge = $('#review-status-badge');
  statusBadge.textContent = review.review_status_label || '검색 근거 범위 검토';
  statusBadge.className = `review-status ${review.review_status === 'additional_facts_required' ? 'needs-facts' : 'evidence-scoped'}`;
  $('#review-conclusion').textContent = review.conclusion || '';

  const priorityFacts = Array.isArray(review.priority_facts) ? review.priority_facts : [];
  const reviewLinks = Array.isArray(review.fact_issue_action_links)
    ? review.fact_issue_action_links : [];
  const linksByIssue = new Map(
    reviewLinks.map((link) => [String(link.issue_id || ''), link])
  );
  const actions = Array.isArray(data.practical_action_generator?.actions)
    ? data.practical_action_generator.actions : [];
  const factsByIssue = new Map();
  priorityFacts.forEach((fact) => {
    const issueId = String(fact.issue_id || '');
    if (!factsByIssue.has(issueId)) factsByIssue.set(issueId, []);
    factsByIssue.get(issueId).push(fact);
  });
  const actionsByIssue = new Map();
  actions.forEach((action) => {
    const issueId = String(action.issue_id || '');
    if (!actionsByIssue.has(issueId)) actionsByIssue.set(issueId, []);
    actionsByIssue.get(issueId).push(action);
  });

  const container = $('#review-issue-list');
  container.innerHTML = '';
  issueReviews.forEach((issue, index) => {
    const issueId = String(issue.issue_id || '');
    const issueLink = linksByIssue.get(issueId) || {};
    const linkedFactIds = new Set(issueLink.fact_ids || issue.priority_fact_ids || []);
    const linkedActionIds = new Set(issueLink.action_ids || issue.action_ids || []);
    const card = document.createElement('article');
    card.className = 'review-issue-card';

    const header = document.createElement('div');
    header.className = 'review-issue-header';
    appendReviewText(header, 'span', String(issue.issue_order || index + 1).padStart(2, '0'), 'review-issue-order');
    const titleGroup = document.createElement('div');
    appendReviewText(titleGroup, 'h5', issue.issue_label || issueId || '법적 쟁점');
    appendReviewText(titleGroup, 'p', issue.conditional_conclusion || '', 'review-issue-conclusion');
    header.append(titleGroup);
    card.append(header);

    const columns = document.createElement('div');
    columns.className = 'review-columns';
    const factsColumn = document.createElement('section');
    appendReviewText(factsColumn, 'h6', '우선 확인 사실');
    const factList = document.createElement('ol');
    factList.className = 'review-fact-list';
    (factsByIssue.get(issueId) || []).filter((fact) => linkedFactIds.has(fact.fact_id)).forEach((fact) => {
      const item = document.createElement('li');
      const line = document.createElement('div');
      appendReviewText(line, 'span', fact.priority_label || '확인', `fact-priority priority-${fact.priority || 3}`);
      appendReviewText(line, 'strong', fact.label || fact.fact_id || '확인사항');
      item.append(line);
      appendReviewText(item, 'p', fact.question || '');
      factList.append(item);
    });
    if (!factList.children.length) appendReviewText(factsColumn, 'p', '현재 구조화된 추가 확인사항이 없습니다.', 'review-empty');
    else factsColumn.append(factList);

    const actionsColumn = document.createElement('section');
    appendReviewText(actionsColumn, 'h6', '근거 연결 조치');
    const actionList = document.createElement('ul');
    actionList.className = 'review-action-list';
    (actionsByIssue.get(issueId) || []).filter((action) => linkedActionIds.has(action.action_id)).forEach((action) => {
      const item = document.createElement('li');
      appendReviewText(item, 'strong', action.title || action.action_id || '후속 조치');
      appendReviewText(item, 'p', action.instruction || '');
      actionList.append(item);
    });
    if (!actionList.children.length) appendReviewText(actionsColumn, 'p', '검색 근거 범위에서 별도 조치가 생성되지 않았습니다.', 'review-empty');
    else actionsColumn.append(actionList);
    columns.append(factsColumn, actionsColumn);
    card.append(columns);

    const citations = Array.isArray(issueLink.citations)
      ? issueLink.citations : (Array.isArray(issue.citations) ? issue.citations : []);
    if (citations.length) {
      const sourceRow = document.createElement('div');
      sourceRow.className = 'review-sources';
      appendReviewText(sourceRow, 'span', '연결 근거', 'review-source-label');
      citations.forEach((citation) => appendReviewText(sourceRow, 'span', citation, 'review-source-chip'));
      card.append(sourceRow);
    }
    container.append(card);
  });
}

async function loadHealth() {
  try {
    const response = await fetch("/health");
    if (!response.ok) throw new Error("상태 확인 실패");
    const data = await response.json();
    $("#health-dot").classList.add("ok");
    $("#health-text").textContent = "데모 서버 정상";
    $("#health-meta").textContent = `법령 문서 ${data.provision_count}건 · 도메인 ${data.domain_count}개 · v${data.version.replace(/^v/, "")}`;
    $("#brand-version").textContent = `v${data.version.replace(/^v/, "")}`;
  } catch {
    $("#health-text").textContent = "서버 연결 실패";
    $("#health-meta").textContent = "잠시 후 다시 시도해 주세요.";
    $("#brand-version").textContent = "오프라인";
  }
}

async function loadDemoConfig() {
  try {
    const response = await fetch("/demo-config");
    if (!response.ok) return;
    const config = await response.json();
    if (config.public_demo && config.max_requests) {
      const minutes = Math.round(config.window_seconds / 60);
      const note = $("#demo-limit-note");
      note.textContent = `공개 데모 보호를 위해 접속자별 ${minutes}분당 ${config.max_requests}회까지 질의할 수 있습니다.`;
      note.hidden = false;
    }
  } catch {
    // 설정 조회 실패는 핵심 데모 기능을 막지 않는다.
  }
}

async function loadDomains() {
  try {
    const response = await fetch("/domains");
    if (!response.ok) return;
    const domains = await response.json();
    domains.forEach((domain) => {
      const option = document.createElement("option");
      option.value = domain.domain_id;
      option.textContent = domain.display_name;
      $("#domain").append(option);
    });
  } catch {
    // 전체 법령 선택지는 기본으로 유지한다.
  }
}

$$('[data-question]').forEach((button) => button.addEventListener('click', () => {
  $('#question').value = button.dataset.question;
  if (button.dataset.domain) $('#domain').value = button.dataset.domain;
  $('#mode').value = 'answer';
  $$('[data-question]').forEach((item) => item.classList.toggle('selected', item === button));
  $('#question').focus();
}));

function renderQuery(data) {
  const status = data.evidence_status || { level: 'insufficient', message: '근거 상태를 확인할 수 없습니다.' };
  $('#result-question').textContent = data.question;
  $('#evidence-badge').textContent = displayEvidenceLevel(status.level);
  $('#evidence-badge').className = `evidence-badge ${status.level}`;
  $('#status-message').textContent = status.message;
  $('#result-list').innerHTML = '';
  $('#precedent-list').innerHTML = '';

  const answerCard = $('#answer-card');
  if ('answer' in data) {
    answerCard.hidden = false;
    renderConditionalReview(data);
    renderStructuredAnswer(data.display_answer || data.answer || '(생성된 답변이 없습니다.)');
    const generationText = {
      completed: '근거 검증 완료', citation_invalid: '인용 검증 실패', failed: '생성 실패', abstained: '답변 유보'
    }[data.generation_status] || data.generation_status;
    $('#generation-badge').textContent = generationText;
    $('#generation-badge').className = `generation ${data.generation_status}`;
    const precedentOnly = data.evidence_routing?.answer_basis === 'precedent';
    if (precedentOnly) {
      const validation = data.precedent_validation || {};
      const alignment = data.evidence_routing?.statute_precedent_alignment || {};
      const alignmentNote = alignment.checked && !alignment.aligned
        ? ' · 법령 Top-1과 판례 연결 조문 불일치 감지'
        : '';
      $('#citation-status').innerHTML = `판례 근거 검증: <strong>${validation.valid ? '통과' : '확인 필요'}</strong> · 공식 출처 기반 검증 요약 · 법령 검색과 별도 검증${alignmentNote}`;
    } else {
      const validation = data.citation_validation || {};
      $('#citation-status').innerHTML = `법령 인용 검증: <strong>${validation.valid ? '통과' : '확인 필요'}</strong>${validation.unsupported_articles?.length ? ` · 근거에서 확인되지 않은 인용 ${escapeHtml(validation.unsupported_articles.join(', '))}` : ''}`;
    }
  } else {
    answerCard.hidden = true;
    renderConditionalReview({});
  }

  const abstained = data.generation_status === 'abstained' || data.abstain === true;
  const precedentOnly = data.evidence_routing?.answer_basis === 'precedent';
  const evidenceHeading = document.querySelector('#result-section .subheading h3');
  const evidenceDescription = document.querySelector('#result-section .subheading p');
  if (evidenceHeading) evidenceHeading.textContent = abstained || precedentOnly ? '관련 법령 검색 후보' : '규범 근거 · 법령';
  const alignment = data.evidence_routing?.statute_precedent_alignment || {};
  if (evidenceDescription) evidenceDescription.textContent = abstained
    ? '답변 근거로 채택되지 않은 검색 후보입니다. 질문을 더 구체화하거나 도메인을 조정해 주세요.'
    : precedentOnly
      ? (alignment.checked && !alignment.aligned
          ? '법령 Top-1이 검증 판례의 연결 조문과 일치하지 않아 검색 후보로 강등했습니다. 아래 판례 카드의 관련 조문을 함께 확인하세요.'
          : '이 조문들은 판례 답변의 직접 근거로 채택되지 않았습니다. 판례와 연결된 정확한 조문은 아래 판례 카드에서 확인합니다.')
    : '검색 점수와 시행일, 공식 출처를 함께 표시합니다.';

  (data.results || []).forEach((result) => {
    const element = document.createElement('article');
    element.className = 'result-card';
    const linkedByPrecedent = result.retrieval_reason === 'precedent_linked';
    const reasonLabel = linkedByPrecedent
      ? '판례 연결 조문'
      : (abstained || precedentOnly ? '검색 후보' : (result.retrieval_reason === 'direct' ? '직접 근거' : '관련 근거'));
    const scoreMeta = linkedByPrecedent
      ? `<span>판례 관련도 ${Number(result.relation_score).toFixed(4)}</span><span>연결 출처 검증 판례</span>`
      : `<span>종합 점수 ${Number(result.score).toFixed(4)}</span><span>키워드 ${Number(result.lexical_score).toFixed(4)}</span><span>의미 ${Number(result.semantic_score).toFixed(4)}</span>`;
    element.innerHTML = `<div class="result-card-header"><h3><span class="rank">${result.rank}</span>${escapeHtml(result.citation)}</h3><span class="reason">${reasonLabel}</span></div><p>${escapeHtml(result.text)}</p><div class="result-meta">${scoreMeta}<span>시행일 ${escapeHtml(result.effective_from || '미상')}</span>${result.source_url ? `<a href="${escapeHtml(result.source_url)}" target="_blank" rel="noopener noreferrer">공식 출처 열기</a>` : ''}</div>`;
    $('#result-list').append(element);
  });

  const precedentSection = $('#precedent-section');
  const precedents = data.precedent_evidence || [];
  precedentSection.hidden = precedents.length === 0;
  $('#precedent-routing-note').textContent = data.evidence_routing?.precedent_reason
    || '질문의 해석·적용 쟁점과 관련된 검증 판례입니다.';
  precedents.forEach((precedent) => {
    const related = (precedent.related_statutes || [])
      .map((item) => `${item.law_name} ${item.article_no}`)
      .join(', ');
    const element = document.createElement('article');
    element.className = 'result-card precedent-card';
    element.innerHTML = `<div class="result-card-header"><h3><span class="rank">${precedent.rank}</span>${escapeHtml(precedent.court)} ${escapeHtml(precedent.decision_date)} 선고 ${escapeHtml(precedent.case_number)}</h3><span class="reason precedent-reason">해석·적용 근거</span></div><p class="case-name">${escapeHtml(precedent.case_name)}</p><p>${escapeHtml(precedent.holding_summary)}</p><details class="precedent-detail"><summary>판단 요소와 적용상 주의사항</summary><p>${escapeHtml(precedent.reasoning_summary)}</p><p class="context-note">${escapeHtml(precedent.legal_context_note)}</p></details><div class="result-meta"><span>관련 조문 ${escapeHtml(related || '미상')}</span><span>관련도 ${Number(precedent.score).toFixed(4)}</span><a href="${escapeHtml(precedent.source_url)}" target="_blank" rel="noopener noreferrer">공식 판례 열기</a></div>`;
    $('#precedent-list').append(element);
  });

  $('#prompt-panel').hidden = !data.prompt;
  $('#prompt-content').textContent = data.prompt || '';
  $('#result-section').hidden = false;
  $('#result-section').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  const button = $('#submit-button');
  button.disabled = true;
  button.textContent = '법령과 근거를 분석하는 중…';
  try {
    const mode = $('#mode').value;
    const body = {
      question: $('#question').value.trim(),
      domain: $('#domain').value,
      top_k: Number($('#top-k').value),
    };
    if ($('#as-of-date').value) body.as_of_date = $('#as-of-date').value;
    const response = await fetch(`/${mode}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail?.message || '요청을 처리하지 못했습니다.');
    renderQuery(data);
  } catch (error) {
    window.alert(error.message || '요청 중 오류가 발생했습니다.');
  } finally {
    button.disabled = false;
    button.textContent = '근거 기반 답변 확인';
  }
});

loadHealth();
loadDemoConfig();
loadDomains();
