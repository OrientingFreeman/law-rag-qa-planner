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
  ['실무상 조치', '핵심 체크리스트'],
  ['추가 확인 사실', '추가 확인 사항'],
  ['추가 확인 사항', '추가 확인 사항'],
  ['답변 한계', '답변 한계'],
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
  $('#question').focus();
}));

function renderQuery(data) {
  const status = data.evidence_status || { level: 'insufficient', message: '근거 상태를 확인할 수 없습니다.' };
  $('#result-question').textContent = data.question;
  $('#evidence-badge').textContent = displayEvidenceLevel(status.level);
  $('#evidence-badge').className = `evidence-badge ${status.level}`;
  $('#status-message').textContent = status.message;
  $('#result-list').innerHTML = '';

  const answerCard = $('#answer-card');
  if ('answer' in data) {
    answerCard.hidden = false;
    renderStructuredAnswer(data.answer || '(생성된 답변이 없습니다.)');
    const generationText = {
      completed: '근거 검증 완료', citation_invalid: '인용 검증 실패', failed: '생성 실패', abstained: '답변 유보'
    }[data.generation_status] || data.generation_status;
    $('#generation-badge').textContent = generationText;
    $('#generation-badge').className = `generation ${data.generation_status}`;
    const validation = data.citation_validation || {};
    $('#citation-status').innerHTML = `인용 검증: <strong>${validation.valid ? '통과' : '확인 필요'}</strong>${validation.unsupported_articles?.length ? ` · 근거에서 확인되지 않은 인용 ${escapeHtml(validation.unsupported_articles.join(', '))}` : ''}`;
  } else {
    answerCard.hidden = true;
  }

  const abstained = data.generation_status === 'abstained' || data.abstain === true;
  const evidenceHeading = document.querySelector('#result-section .subheading h3');
  const evidenceDescription = document.querySelector('#result-section .subheading p');
  if (evidenceHeading) evidenceHeading.textContent = abstained ? '검색 후보 조문' : '근거 법령';
  if (evidenceDescription) evidenceDescription.textContent = abstained
    ? '답변 근거로 채택되지 않은 검색 후보입니다. 질문을 더 구체화하거나 도메인을 조정해 주세요.'
    : '검색 점수와 시행일, 공식 출처를 함께 표시합니다.';

  (data.results || []).forEach((result) => {
    const element = document.createElement('article');
    element.className = 'result-card';
    element.innerHTML = `<div class="result-card-header"><h3><span class="rank">${result.rank}</span>${escapeHtml(result.citation)}</h3><span class="reason">${abstained ? '검색 후보' : (result.retrieval_reason === 'direct' ? '직접 근거' : '관련 근거')}</span></div><p>${escapeHtml(result.text)}</p><div class="result-meta"><span>종합 점수 ${Number(result.score).toFixed(4)}</span><span>키워드 ${Number(result.lexical_score).toFixed(4)}</span><span>의미 ${Number(result.semantic_score).toFixed(4)}</span><span>시행일 ${escapeHtml(result.effective_from || '미상')}</span>${result.source_url ? `<a href="${escapeHtml(result.source_url)}" target="_blank" rel="noopener noreferrer">공식 출처 열기</a>` : ''}</div>`;
    $('#result-list').append(element);
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
