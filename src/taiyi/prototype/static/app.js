"use strict";

const app = document.querySelector("#app");
const toast = document.querySelector("#toast");
let currentState = null;
let toastTimer = null;

const steps = [
  ["identity", "创建身份"],
  ["incarnations", "派生同位体"],
  ["experiences", "输入经历"],
  ["memories", "记忆与来源"],
  ["compare", "比较世界线"],
  ["review", "人工审核"],
  ["apply", "生成快照"],
  ["rebirth", "回滚或重生"],
];

const stagePositions = {
  identity: 0,
  incarnations: 1,
  experiences: 2,
  compare: 4,
  review: 5,
  apply: 6,
  rebirth: 7,
  complete: 8,
};

const strategyLabels = {
  coexist: "并存｜保留多个视角",
  select: "择一｜选择一项进入身份",
  synthesize: "综合｜形成有来源的新结论",
  suspend: "悬置｜保留未决冲突",
  reject: "拒绝｜不写入身份",
};

const kindLabels = {
  duplicate: "重复",
  supplement: "补充",
  conflict: "冲突",
};

const eventLabels = {
  user_message: "用户经历",
  model_response: "模型回应",
  memory_extraction: "记忆提取",
  merge: "归一",
  rollback: "回滚",
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function shortId(value) {
  const text = String(value ?? "");
  return text.length > 18 ? `${text.slice(0, 9)}…${text.slice(-6)}` : text;
}

function eventContent(event) {
  if (!event.payload) return "正文已擦除，仅保留顺序与哈希";
  return event.payload.content || `${eventLabels[event.event_type] || event.event_type} 已记录`;
}

function showToast(message, isError = false) {
  window.clearTimeout(toastTimer);
  toast.textContent = message;
  toast.className = `toast show${isError ? " error" : ""}`;
  toastTimer = window.setTimeout(() => {
    toast.className = "toast";
  }, 3200);
}

async function request(path, payload) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || "操作未完成");
  return body;
}

async function loadState() {
  const response = await fetch("/api/state", { cache: "no-store" });
  if (!response.ok) throw new Error("无法读取本地身份状态");
  currentState = await response.json();
  render();
}

function renderJourney() {
  const position = stagePositions[currentState.stage] ?? 0;
  return `
    <aside class="journey" aria-label="核心体验进度">
      <p class="journey-eyebrow">Core journey</p>
      <h2>一体万化，万忆归一</h2>
      <p class="journey-intro">从共同身份出发，让不同经历留下有来源的记忆，再由你决定下一版本继承什么。</p>
      <ol class="steps">
        ${steps.map(([key, label], index) => {
          const state = index < position ? "done" : index === position ? "current" : "";
          const marker = index < position ? "✓" : index + 1;
          return `<li class="step ${state}" data-step="${key}"><span class="step-number">${marker}</span><span>${label}</span></li>`;
        }).join("")}
      </ol>
      <div class="local-note">所有数据保存在本地 SQLite。默认演示使用离线 MockProvider，不需要 API 密钥。</div>
    </aside>`;
}

function renderHero() {
  const core = currentState.core;
  const incarnationCount = currentState.incarnations.length;
  const memoryCount = currentState.incarnations.reduce((sum, item) => sum + item.memories.length, 0);
  return `
    <section class="hero">
      <div>
        <p class="eyebrow">PRODUCT PROTOTYPE · v0.1.1</p>
        <h1>${core ? `正在演化「${escapeHtml(core.name)}」` : "亲手治理一个 AI 身份的继承"}</h1>
        <p>经历不会自动成为身份。先观察不同世界线形成了什么，再检查来源、处理冲突并生成新的不可变快照。</p>
      </div>
      <div class="time-badge"><strong>10–15</strong><span>分钟核心体验</span></div>
    </section>
    <section class="summary-grid" aria-label="身份状态摘要">
      <div class="summary-item"><span>身份核心</span><strong>${core ? 1 : 0}</strong></div>
      <div class="summary-item"><span>同位体</span><strong>${incarnationCount}</strong></div>
      <div class="summary-item"><span>候选记忆</span><strong>${memoryCount}</strong></div>
      <div class="summary-item"><span>身份快照</span><strong>${currentState.snapshots.length}</strong></div>
    </section>`;
}

function panelClass(stageNames) {
  return stageNames.includes(currentState.stage) ? "panel active" : "panel";
}

function renderIdentity() {
  const demo = currentState.demo;
  if (!currentState.core) {
    return `
      <section class="${panelClass(["identity"])}" id="identity-panel">
        <div class="panel-heading"><div><span class="object-badge">稳定身份层</span><h2>创建身份核心</h2><p>身份核心是稳定标识和版本谱系，不等于人格、模型实例或意识。</p></div></div>
        <form data-action="identity.create">
          <div class="form-grid">
            <div class="field"><label for="identity-name">身份名称</label><input id="identity-name" name="name" maxlength="80" required value="${escapeHtml(demo.identity_name)}"></div>
            <div class="field full"><label for="identity-description">初始自我描述</label><textarea id="identity-description" name="description" maxlength="1000">${escapeHtml(demo.description)}</textarea></div>
          </div>
          <div class="concept-rule">第一条边界：身份核心保持稳定，经历只能先成为世界线中的候选内容。</div>
          <div class="form-actions"><button class="button" type="submit">创建身份与初始快照</button></div>
        </form>
      </section>`;
  }
  const core = currentState.core;
  return `
    <section class="panel" id="identity-panel">
      <div class="panel-heading"><div><span class="object-badge">稳定身份层</span><h2>身份核心</h2><p>当前指针指向一个不可变快照；普通经历不会自动改变它。</p></div><span class="status-badge">已建立</span></div>
      <div class="identity-card"><div class="identity-seal">一</div><div><h3>${escapeHtml(core.name)}</h3><p>${escapeHtml(currentState.current_snapshot.self_description)}</p><div class="meta-row"><span>核心 ${escapeHtml(shortId(core.id))}</span><span>当前快照 ${escapeHtml(shortId(core.current_snapshot_id))}</span></div></div></div>
    </section>`;
}

function renderIncarnationCards(incarnations, roleLabel) {
  return `<div class="worldline-grid">${incarnations.map((item) => `
    <div class="identity-card">
      <div class="identity-seal">${escapeHtml(item.name.slice(0, 1))}</div>
      <div>
        <h3>${escapeHtml(item.name)}</h3>
        <p>从快照 ${escapeHtml(shortId(item.base_snapshot_id))} 派生</p>
        <div class="meta-row"><span>${escapeHtml(roleLabel)}</span><span>${escapeHtml(shortId(item.worldline_id))}</span></div>
      </div>
    </div>`).join("")}</div>`;
}

function renderIncarnations() {
  if (!currentState.core) return "";
  const incarnationCount = currentState.incarnations.length;
  const comparisonGroup = currentState.incarnations.slice(0, 2);
  const laterGenerations = currentState.incarnations.slice(2);
  const demo = currentState.demo;
  const nextName = incarnationCount === 0 ? demo.left_name : demo.right_name;
  const currentSnapshot = currentState.core.current_snapshot_id;
  const comparisonBase = comparisonGroup[0]?.base_snapshot_id;
  const comparisonSharesBase = comparisonGroup.length === 2
    && comparisonGroup.every((item) => item.base_snapshot_id === comparisonBase);
  const status = incarnationCount < 2
    ? `${incarnationCount}/2 已就绪`
    : laterGenerations.length
      ? `已派生 ${incarnationCount} 个`
      : "比较组已就绪";
  const comparisonNote = comparisonSharesBase
    ? `本次比较组共享基础快照 ${escapeHtml(shortId(comparisonBase))}，但事件和候选记忆相互隔离。`
    : "本次比较组的基础快照不同，不能视为共享同一起点。";
  return `
    <section class="${panelClass(["incarnations"])}" id="incarnations-panel">
      <div class="panel-heading"><div><span class="object-badge">运行时经历层</span><h2>派生同位体</h2><p>同位体从明确快照启动，各自拥有隔离的世界线。核心流程先建立两个同源比较对象，归一后再从新快照重生下一代。</p></div><span class="status-badge">${status}</span></div>
      <div class="incarnation-groups">
        ${comparisonGroup.length ? `<div class="incarnation-group"><div class="incarnation-group-heading"><strong>本次比较组</strong><span>前两个同位体用于当前差异与归一提案</span></div>${renderIncarnationCards(comparisonGroup, "比较对象")}</div>` : ""}
        ${laterGenerations.length ? `<div class="incarnation-group next-generation-group"><div class="incarnation-group-heading"><strong>下一代同位体</strong><span>从归一后的身份快照派生，不属于上方既有比较组</span></div>${renderIncarnationCards(laterGenerations, "下一代")}</div>` : ""}
      </div>
      ${incarnationCount < 2 ? `<form data-action="incarnation.create"><input type="hidden" name="snapshot_id" value="${escapeHtml(currentSnapshot)}"><div class="form-grid"><div class="field"><label for="incarnation-name">第 ${incarnationCount + 1} 个同位体名称</label><input id="incarnation-name" name="name" maxlength="80" required value="${escapeHtml(nextName)}"></div><div class="field"><label for="base-snapshot">基础快照</label><input id="base-snapshot" value="${escapeHtml(shortId(currentSnapshot))}" disabled></div></div><div class="form-actions"><button class="button" type="submit">派生同位体</button></div></form>` : `<div class="concept-rule">${comparisonNote}</div>`}
    </section>`;
}

function renderSourceEvents(memory) {
  return memory.source_events.map((event) => `
    <div class="source-event">
      <strong>#${event.sequence_number} ${escapeHtml(eventLabels[event.event_type] || event.event_type)}</strong>
      <code>${escapeHtml(eventContent(event))}</code>
      <div class="meta-row"><span>${escapeHtml(shortId(event.id))}</span><span>哈希 ${escapeHtml(shortId(event.payload_hash))}</span></div>
    </div>`).join("");
}

function renderMemory(memory) {
  const status = memory.status === "candidate" ? "候选记忆" : memory.status === "accepted" ? "已继承" : memory.status === "deleted" ? "已删除" : memory.status;
  return `
    <article class="memory-card">
      <div class="memory-top"><span class="object-badge">${escapeHtml(memory.type)}</span><span class="status-badge">${escapeHtml(status)}</span></div>
      <p>${escapeHtml(memory.content)}</p>
      <div class="meta-row"><span>来源 ${memory.source_event_ids.length} 项</span><span>可信度 ${Math.round(memory.confidence * 100)}%</span><span>${escapeHtml(memory.extractor)}</span></div>
      <details><summary>查看来源与原始经历</summary>${renderSourceEvents(memory)}</details>
    </article>`;
}

function renderWorldlines() {
  if (currentState.incarnations.length < 2) return "";
  const demo = currentState.demo;
  return `
    <section class="${panelClass(["experiences", "compare"])}" id="worldlines-panel">
      <div class="panel-heading"><div><span class="object-badge">经历 → 候选记忆</span><h2>让世界线经历不同选择</h2><p>每条输入先记录为事件，再由模型提供器提取带来源的候选记忆。候选记忆尚未进入身份。</p></div></div>
      <div class="worldline-grid">
        ${currentState.incarnations.slice(0, 2).map((item, index) => {
          const message = index === 0 ? demo.left_message : demo.right_message;
          const visibleEvents = item.events.filter((event) => ["user_message", "model_response"].includes(event.event_type));
          return `<article class="worldline-card"><div class="worldline-head"><h3>${escapeHtml(item.name)}</h3><span class="status-badge">隔离世界线</span></div>
            ${visibleEvents.length ? `<div class="event-list">${visibleEvents.map((event) => `<div class="event-item"><strong>#${event.sequence_number} ${escapeHtml(eventLabels[event.event_type] || event.event_type)}</strong>${escapeHtml(eventContent(event))}</div>`).join("")}</div>` : `<div class="empty-state"><strong>还没有经历</strong>输入一项选择，让它形成第一条候选记忆。</div>`}
            <form data-action="experience.add"><input type="hidden" name="incarnation_name" value="${escapeHtml(item.name)}"><div class="field"><label for="message-${index}">输入经历</label><textarea id="message-${index}" name="message" required>${escapeHtml(item.memories.length ? "" : message)}</textarea></div><div class="form-actions"><button class="button" type="submit">记录经历</button></div></form>
            <div class="memory-list">${item.memories.map(renderMemory).join("")}</div>
          </article>`;
        }).join("")}
      </div>
      <div class="concept-rule">第二条边界：经历不等于记忆，记忆也不等于身份。只有审核后写入快照的内容才可继承。</div>
    </section>`;
}

function latestProposal() {
  return currentState.proposals.at(-1) || null;
}

function renderComparison() {
  if (currentState.incarnations.length < 2) return "";
  const ready = currentState.incarnations.slice(0, 2).every((item) => item.memories.length > 0);
  if (!ready) return "";
  const proposal = latestProposal();
  const canCreate = !proposal || proposal.status === "rejected";
  return `
    <section class="${panelClass(["compare", "review", "apply"])}" id="comparison-panel">
      <div class="panel-heading"><div><span class="object-badge">显式跨线操作</span><h2>比较世界线</h2><p>系统只在这里跨线读取候选记忆，并标记重复、补充和冲突。比较本身不会改变身份。</p></div>${proposal ? `<span class="status-badge">${proposal.is_stale ? "提案已陈旧" : `提案 ${escapeHtml(proposal.status)}`}</span>` : ""}</div>
      ${canCreate ? `<form data-action="comparison.create"><input type="hidden" name="left" value="${escapeHtml(currentState.incarnations[0].name)}"><input type="hidden" name="right" value="${escapeHtml(currentState.incarnations[1].name)}"><div class="form-actions"><button class="button" type="submit">生成差异与归一提案</button></div></form>` : ""}
      ${proposal ? renderProposal(proposal) : `<div class="empty-state"><strong>尚未比较</strong>两条世界线已准备好，可以生成一份不会自动应用的提案。</div>`}
    </section>`;
}

function renderProposal(proposal) {
  const isPending = proposal.status === "pending";
  return `
    <div class="diff-list">
      ${proposal.items.length ? proposal.items.map((item) => `
        <article class="diff-card">
          <div class="memory-top"><span class="kind-badge ${escapeHtml(item.kind)}">${escapeHtml(kindLabels[item.kind] || item.kind)}</span><span class="meta-row">${escapeHtml(shortId(item.id))}</span></div>
          <div class="diff-memory-pair">${item.memories.map((memory) => `<div class="diff-memory"><strong>${escapeHtml(memory.worldline_id.startsWith("merge:") ? "人工综合" : "世界线候选")}</strong><br>${escapeHtml(memory.content)}<details><summary>来源</summary>${renderSourceEvents(memory)}</details></div>`).join("")}</div>
          ${isPending ? `<div class="review-grid"><div class="field"><label for="strategy-${escapeHtml(item.id)}">处理策略</label><select id="strategy-${escapeHtml(item.id)}" name="resolution:${escapeHtml(item.id)}" form="review-form">${Object.entries(strategyLabels).map(([value, label]) => `<option value="${value}"${value === item.suggested_strategy ? " selected" : ""}>${label}</option>`).join("")}</select><p class="strategy-help">不确定的冲突默认悬置，不会被静默覆盖。</p></div><div class="field"><label for="content-${escapeHtml(item.id)}">人工内容（综合时使用）</label><textarea id="content-${escapeHtml(item.id)}" name="content:${escapeHtml(item.id)}" form="review-form">${item.kind === "conflict" ? escapeHtml(currentState.demo.synthesis) : ""}</textarea></div></div>` : `<p class="strategy-help">审核结果：${escapeHtml(strategyLabels[proposal.resolutions[item.id]] || proposal.resolutions[item.id] || "未设置")}</p>`}
        </article>`).join("") : `<div class="empty-state"><strong>没有差异项</strong>当前两条世界线没有可归一的候选记忆。</div>`}
    </div>
    ${isPending ? `<form id="review-form" data-action="proposal.review"><input type="hidden" name="proposal_id" value="${escapeHtml(proposal.id)}"><div class="concept-rule">第三条边界：模型只能提出建议。你明确批准前，身份核心不会改变。</div><div class="form-actions"><button class="button" type="submit" name="decision" value="approve">批准所选策略</button><button class="button secondary" type="submit" name="decision" value="reject">拒绝整个提案</button></div></form>` : ""}
    ${proposal.is_stale ? `<div class="concept-rule">当前身份已经离开提案的基础快照。为防止旧审核覆盖新状态，这份提案不能应用，请重新比较。</div>` : ""}
    ${proposal.status === "approved" && !proposal.is_stale ? `<form data-action="proposal.apply"><input type="hidden" name="proposal_id" value="${escapeHtml(proposal.id)}"><div class="concept-rule">提案已审核，但尚未应用。应用后将创建子快照，历史快照保持不可变。</div><div class="form-actions"><button class="button" type="submit">应用提案并生成新快照</button></div></form>` : ""}
    ${proposal.status === "applied" ? `<div class="concept-rule">新快照已生成：${escapeHtml(shortId(proposal.applied_snapshot_id))}。审核记录和双侧来源均已保留。</div>` : ""}`;
}

function renderHistory() {
  if (!currentState.core) return "";
  const applied = currentState.proposals.some((proposal) => proposal.status === "applied");
  return `
    <section class="${panelClass(["rebirth", "complete"])}" id="history-panel">
      <div class="panel-heading"><div><span class="object-badge">可继承身份层</span><h2>快照与下一代</h2><p>快照不可变；回滚只移动当前指针，重生则从当前快照派生新的隔离世界线。</p></div></div>
      <div class="snapshot-list">${currentState.snapshots.map((snapshot, index) => `
        <article class="snapshot-card ${snapshot.is_current ? "current" : ""}">
          <div class="memory-top"><h3>快照 ${index + 1}</h3>${snapshot.is_current ? `<span class="status-badge">当前指针</span>` : `<span class="object-badge">历史只读</span>`}</div>
          <p>${escapeHtml(snapshot.self_description)}</p>
          <div class="meta-row"><span>${escapeHtml(shortId(snapshot.id))}</span><span>父快照 ${snapshot.parent_snapshot_ids.length ? escapeHtml(shortId(snapshot.parent_snapshot_ids[0])) : "无"}</span><span>未决冲突 ${snapshot.unresolved_conflict_ids.length}</span></div>
          <div class="snapshot-memories">${snapshot.accepted_memories.length ? snapshot.accepted_memories.map((memory) => `<div class="snapshot-memory">${escapeHtml(memory.content)}</div>`).join("") : `<div class="empty-state"><strong>尚无可继承记忆</strong>这是身份的初始版本。</div>`}</div>
          ${!snapshot.is_current ? `<form data-action="identity.rollback"><input type="hidden" name="snapshot_id" value="${escapeHtml(snapshot.id)}"><div class="form-actions"><button class="button ghost" type="submit">将当前指针回滚到这里</button></div></form>` : ""}
        </article>`).join("")}</div>
      ${applied ? `<form data-action="identity.rebirth"><div class="form-grid"><div class="field"><label for="rebirth-name">下一代同位体名称</label><input id="rebirth-name" name="name" maxlength="80" required value="${escapeHtml(currentState.demo.rebirth_name)}"></div><div class="field"><label>继承基础</label><input value="当前快照 ${escapeHtml(shortId(currentState.core.current_snapshot_id))}" disabled></div></div><div class="form-actions"><button class="button" type="submit">从当前快照重生</button></div></form>` : ""}
    </section>`;
}

function renderCompletion() {
  if (currentState.stage !== "complete") return "";
  return `<section class="panel complete-panel"><div class="completion"><div class="completion-mark">✓</div><h2>核心体验已经闭环</h2><p>你从同一身份派生了不同世界线，检查了候选记忆与来源，亲自审核归一并生成新快照。身份演化发生了，但历史没有被改写。</p></div></section>`;
}

function render() {
  app.innerHTML = `${renderJourney()}<div class="content">${renderHero()}${renderIdentity()}${renderIncarnations()}${renderWorldlines()}${renderComparison()}${renderHistory()}${renderCompletion()}</div>`;
}

function formPayload(form, submitter) {
  const data = new FormData(form);
  const action = form.dataset.action;
  if (action === "proposal.review") {
    const resolutions = {};
    const content = {};
    for (const [key, value] of data.entries()) {
      if (key.startsWith("resolution:")) resolutions[key.slice(11)] = String(value);
      if (key.startsWith("content:") && String(value).trim()) content[key.slice(8)] = String(value).trim();
    }
    return {
      proposal_id: String(data.get("proposal_id")),
      approve: submitter?.value !== "reject",
      resolutions,
      content,
    };
  }
  return Object.fromEntries(Array.from(data.entries(), ([key, value]) => [key, String(value)]));
}

const actionPaths = {
  "identity.create": "/api/identity",
  "incarnation.create": "/api/incarnations",
  "experience.add": "/api/experiences",
  "comparison.create": "/api/comparisons",
  "proposal.review": "/api/proposals/review",
  "proposal.apply": "/api/proposals/apply",
  "identity.rebirth": "/api/rebirth",
  "identity.rollback": "/api/rollback",
};

app.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.target;
  const action = form.dataset.action;
  const path = actionPaths[action];
  if (!path) return;
  const button = event.submitter || form.querySelector("button[type=submit]");
  const originalText = button?.textContent;
  if (button) {
    button.disabled = true;
    button.textContent = "处理中…";
  }
  try {
    const body = await request(path, formPayload(form, event.submitter));
    currentState = body.state;
    render();
    showToast("操作已记录，身份状态已更新");
    document.querySelector(`.panel.active`)?.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    showToast(error.message || "操作未完成", true);
    if (button) {
      button.disabled = false;
      button.textContent = originalText;
    }
  }
});

loadState().catch((error) => {
  app.innerHTML = `<section class="loading-card"><p>${escapeHtml(error.message)}</p></section>`;
  showToast(error.message, true);
});
