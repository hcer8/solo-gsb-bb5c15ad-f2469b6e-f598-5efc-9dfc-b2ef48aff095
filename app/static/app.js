// ---------------- 基础工具 ----------------

async function api(path, method = "GET", body = null) {
  const opts = { method, headers: { "Content-Type": "application/json" } };
  if (body !== null) opts.body = JSON.stringify(body);
  const res = await fetch(path, opts);
  if (!res.ok) {
    let msg = `请求失败 (${res.status})`;
    try { msg = (await res.json()).detail || msg; } catch (e) { /* ignore */ }
    throw new Error(msg);
  }
  return res.json();
}

function toast(msg, isError = false) {
  const el = document.getElementById("toast");
  el.textContent = msg;
  el.className = "show" + (isError ? " error" : "");
  setTimeout(() => { el.className = ""; }, 2600);
}

function parseTopics(text) {
  return text.split(/[,，]/).map(s => s.trim()).filter(Boolean);
}

function topicTags(topics) {
  return topics.map(t => `<span class="tag">${esc(t)}</span>`).join("");
}

function esc(s) {
  return String(s).replace(/[&<>"']/g,
    c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// ---------------- 全局状态 ----------------

let state = { papers: [], reviewers: [], conflicts: [], assignments: [] };

async function refresh() {
  state = await api("/api/state");
  renderPapers();
  renderReviewers();
  renderConflicts();
  renderAssignments();
}

// ---------------- 标签页 ----------------

document.querySelectorAll(".tab").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach(b => b.classList.remove("active"));
    document.querySelectorAll(".panel").forEach(p => p.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById("tab-" + btn.dataset.tab).classList.add("active");
  });
});

// ---------------- 稿件 ----------------

function renderPapers() {
  const tb = document.querySelector("#papers-table tbody");
  tb.innerHTML = state.papers.map(p => `
    <tr>
      <td>${p.id}</td>
      <td>${esc(p.title)}</td>
      <td>${topicTags(p.topics)}</td>
      <td>${p.required_reviews}</td>
      <td><button class="small danger" onclick="deletePaper(${p.id})">删除</button></td>
    </tr>`).join("");
}

document.getElementById("paper-form").addEventListener("submit", async e => {
  e.preventDefault();
  try {
    await api("/api/papers", "POST", {
      title: document.getElementById("paper-title").value.trim(),
      topics: parseTopics(document.getElementById("paper-topics").value),
      required_reviews: +document.getElementById("paper-required").value,
    });
    e.target.reset();
    document.getElementById("paper-required").value = 2;
    await refresh();
    toast("稿件已添加");
  } catch (err) { toast(err.message, true); }
});

async function deletePaper(id) {
  if (!confirm("删除该稿件及其相关冲突、分配记录？")) return;
  try {
    await api(`/api/papers/${id}`, "DELETE");
    await refresh();
    toast("已删除");
  } catch (err) { toast(err.message, true); }
}

// ---------------- 评审人 ----------------

function renderReviewers() {
  const tb = document.querySelector("#reviewers-table tbody");
  tb.innerHTML = state.reviewers.map(r => `
    <tr>
      <td>${r.id}</td>
      <td>${esc(r.name)}</td>
      <td>${topicTags(r.topics)}</td>
      <td>${r.capacity}</td>
      <td><button class="small danger" onclick="deleteReviewer(${r.id})">删除</button></td>
    </tr>`).join("");
}

document.getElementById("reviewer-form").addEventListener("submit", async e => {
  e.preventDefault();
  try {
    await api("/api/reviewers", "POST", {
      name: document.getElementById("reviewer-name").value.trim(),
      topics: parseTopics(document.getElementById("reviewer-topics").value),
      capacity: +document.getElementById("reviewer-capacity").value,
    });
    e.target.reset();
    document.getElementById("reviewer-capacity").value = 3;
    await refresh();
    toast("评审人已添加");
  } catch (err) { toast(err.message, true); }
});

async function deleteReviewer(id) {
  if (!confirm("删除该评审人及其相关冲突、分配记录？")) return;
  try {
    await api(`/api/reviewers/${id}`, "DELETE");
    await refresh();
    toast("已删除");
  } catch (err) { toast(err.message, true); }
}

// ---------------- 冲突 ----------------

function renderConflicts() {
  const paperSel = document.getElementById("conflict-paper");
  const revSel = document.getElementById("conflict-reviewer");
  paperSel.innerHTML = state.papers.map(p =>
    `<option value="${p.id}">#${p.id} ${esc(p.title)}</option>`).join("");
  revSel.innerHTML = state.reviewers.map(r =>
    `<option value="${r.id}">#${r.id} ${esc(r.name)}</option>`).join("");

  const tb = document.querySelector("#conflicts-table tbody");
  tb.innerHTML = state.conflicts.map(c => `
    <tr>
      <td>#${c.paper_id} ${esc(c.paper_title)}</td>
      <td>#${c.reviewer_id} ${esc(c.reviewer_name)}</td>
      <td><button class="small danger" onclick="deleteConflict(${c.id})">移除</button></td>
    </tr>`).join("");
}

document.getElementById("conflict-form").addEventListener("submit", async e => {
  e.preventDefault();
  try {
    await api("/api/conflicts", "POST", {
      paper_id: +document.getElementById("conflict-paper").value,
      reviewer_id: +document.getElementById("conflict-reviewer").value,
    });
    await refresh();
    toast("冲突已登记");
  } catch (err) { toast(err.message, true); }
});

async function deleteConflict(id) {
  try {
    await api(`/api/conflicts/${id}`, "DELETE");
    await refresh();
    toast("已移除");
  } catch (err) { toast(err.message, true); }
}

// ---------------- 求解 ----------------

document.getElementById("solve-btn").addEventListener("click", async () => {
  try {
    const result = await api("/api/solve", "POST", {
      mismatch_penalty: +document.getElementById("mismatch-penalty").value,
      load_weight: +document.getElementById("load-weight").value,
    });
    await refresh();
    renderSolveResult(result);
    toast(`求解完成：新增 ${result.stats.new_assignments} 条分配`);
  } catch (err) { toast(err.message, true); }
});

function renderSolveResult(result) {
  const s = result.stats;
  const box = document.getElementById("solve-summary");
  box.classList.remove("hidden");
  let warnHtml = "";
  if (result.warnings.length) {
    warnHtml = `<div class="card warn"><div class="num">!</div>
      <div class="lbl">${result.warnings.map(esc).join("<br>")}</div></div>`;
  }
  box.innerHTML = `
    <div class="card"><div class="num">${s.total_demand}</div><div class="lbl">总需求（份评审）</div></div>
    <div class="card"><div class="num">${s.total_capacity}</div><div class="lbl">总容量</div></div>
    <div class="card"><div class="num">${s.locked}</div><div class="lbl">锁定保留</div></div>
    <div class="card"><div class="num">${s.new_assignments}</div><div class="lbl">本次新分配</div></div>
    <div class="card"><div class="num">${s.min_cost}</div><div class="lbl">总费用</div></div>
    <div class="card ${s.unfulfilled_count ? "warn" : ""}">
      <div class="num">${s.unfulfilled_count}</div><div class="lbl">未满足稿件</div></div>
    ${warnHtml}`;

  const ub = document.getElementById("unfulfilled-box");
  if (result.unfulfilled.length) {
    ub.classList.remove("hidden");
    document.querySelector("#unfulfilled-table tbody").innerHTML =
      result.unfulfilled.map(u => `
        <tr>
          <td>${esc(u.title)}</td>
          <td>${u.required}</td>
          <td>${u.assigned}</td>
          <td>${u.shortage}</td>
          <td>${esc(u.reason)}</td>
        </tr>`).join("");
  } else {
    ub.classList.add("hidden");
  }

  renderLoads(s.reviewer_loads);
}

function renderLoads(loads) {
  const box = document.getElementById("loads-box");
  box.classList.remove("hidden");
  const chart = document.getElementById("loads-chart");
  if (!loads.length) { chart.innerHTML = ""; return; }
  const maxCap = Math.max(...loads.map(l => Math.max(l.capacity, l.load)), 1);
  chart.innerHTML = loads.map(l => `
    <div class="load-row">
      <span class="name">${esc(l.name)}</span>
      <div class="load-bar">
        <div class="load-fill ${l.load > l.capacity ? "over" : ""}"
             style="width:${Math.min(100, l.load / maxCap * 100)}%"></div>
      </div>
      <span class="val">${l.load} / ${l.capacity}</span>
    </div>`).join("");
}

// ---------------- 分配结果 ----------------

function renderAssignments() {
  const tb = document.querySelector("#assignments-table tbody");
  if (!state.assignments.length) {
    tb.innerHTML = `<tr><td colspan="4" style="color:#8494ab">暂无分配结果，请先求解。</td></tr>`;
    return;
  }
  tb.innerHTML = state.assignments.map(a => `
    <tr>
      <td>#${a.paper_id} ${esc(a.paper_title)}</td>
      <td>#${a.reviewer_id} ${esc(a.reviewer_name)}</td>
      <td>${a.locked
        ? '<span class="badge locked">锁定</span>'
        : `<span class="badge new">第 ${a.run_id} 轮求解</span>`}</td>
      <td><input type="checkbox" ${a.locked ? "checked" : ""}
           onchange="toggleLock(${a.id}, this.checked)"></td>
    </tr>`).join("");
}

async function toggleLock(id, locked) {
  try {
    await api(`/api/assignments/${id}/lock`, "POST", { locked });
    toast(locked ? "已锁定，重新求解时将保留" : "已解锁");
  } catch (err) { toast(err.message, true); }
  await refresh();
}

document.getElementById("clear-unlocked-btn").addEventListener("click", async () => {
  try {
    await api("/api/assignments", "DELETE");
    await refresh();
    document.getElementById("solve-summary").classList.add("hidden");
    toast("未锁定的分配已清除");
  } catch (err) { toast(err.message, true); }
});

// ---------------- 示例与重置 ----------------

document.getElementById("seed-btn").addEventListener("click", async () => {
  if (!confirm("将向数据库追加一组示例稿件与评审人，继续？")) return;
  try {
    await api("/api/seed", "POST");
    await refresh();
    toast("示例数据已载入");
  } catch (err) { toast(err.message, true); }
});

document.getElementById("reset-btn").addEventListener("click", async () => {
  if (!confirm("确定清空全部数据（稿件、评审人、冲突、分配）？")) return;
  try {
    await api("/api/reset", "POST");
    await refresh();
    document.getElementById("solve-summary").classList.add("hidden");
    document.getElementById("unfulfilled-box").classList.add("hidden");
    document.getElementById("loads-box").classList.add("hidden");
    toast("已清空全部数据");
  } catch (err) { toast(err.message, true); }
});

// ---------------- 启动 ----------------

refresh().catch(err => toast(err.message, true));
