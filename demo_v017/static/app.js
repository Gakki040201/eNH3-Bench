"use strict";

const state = {
  config: null,
  cases: [],
  selectedCase: null,
  currentRun: null,
  pollTimer: null,
  elapsedTimer: null,
  runStartedAt: null,
  preflightPassed: false,
  runInProgress: false,
};

const $ = (id) => document.getElementById(id);
const terminalStates = new Set(["succeeded_structured", "succeeded_unstructured", "failed"]);

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}

function setFullText(node, value, label) {
  const text = String(value ?? "—");
  node.textContent = text;
  node.title = text;
  node.setAttribute("aria-label", `${label}：${text}`);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {"Content-Type": "application/json", ...(options.headers || {})},
  });
  let body;
  try {
    body = await response.json();
  } catch (_) {
    body = {safe_error_code: "invalid_server_response", message: "服务器返回了无效响应。"};
  }
  if (!response.ok) {
    const error = new Error(body.message || body.safe_error_code || `HTTP ${response.status}`);
    error.payload = body;
    throw error;
  }
  return body;
}

function setConnection(online) {
  const node = $("server-status");
  node.textContent = online ? "服务器在线" : "服务器离线";
  node.classList.toggle("online", online);
}

function renderConfig(config) {
  state.config = config;
  state.preflightPassed = false;
  document.querySelector('input[name="mode"][value="fixture"]').checked = true;
  $("model-chip").textContent = `model ${config.model}`;
  $("mode-chip").textContent = config.live_enabled ? "FIXTURE + LIVE API" : "FIXTURE ONLY";
  $("live-mode").disabled = true;
  $("preflight-button").disabled = !config.live_enabled;
}

function renderCaseList() {
  const list = $("case-list");
  list.replaceChildren();
  state.cases.forEach((item) => {
    const button = element("button", "case-button");
    button.type = "button";
    button.dataset.caseId = item.case_id;
    button.setAttribute("aria-pressed", String(state.selectedCase?.case_id === item.case_id));
    if (state.selectedCase?.case_id === item.case_id) button.classList.add("selected");
    button.append(element("span", "case-number", item.case_number));
    const copy = element("span", "case-copy");
    const caseId = element("strong", "mono", item.case_id);
    setFullText(caseId, item.case_id, "完整案例 ID");
    const metadata = element("small");
    const taskType = element("span", "", item.task_type);
    setFullText(taskType, item.task_type, "完整任务类型");
    const answerability = element("span", "", item.expected_answerability);
    setFullText(answerability, item.expected_answerability, "完整可回答性");
    metadata.append(taskType, document.createTextNode(" · "), answerability);
    metadata.title = `${item.task_type} · ${item.expected_answerability}`;
    metadata.setAttribute("aria-label", `任务类型：${item.task_type}；可回答性：${item.expected_answerability}`);
    copy.append(caseId, metadata);
    button.append(copy);
    button.addEventListener("click", () => selectCase(item.case_id));
    list.append(button);
  });
  $("case-count").textContent = String(state.cases.length);
}

async function selectCase(caseId) {
  try {
    state.selectedCase = await api(`/api/cases/${encodeURIComponent(caseId)}`);
    renderCaseList();
    renderCaseDetail(state.selectedCase);
    $("run-button").disabled = state.runInProgress;
  } catch (error) {
    showStatus(`案例加载失败：${error.message}`, "failed");
  }
}

function renderCaseDetail(detail) {
  setFullText($("case-id"), detail.case_id, "完整案例 ID");
  setFullText($("paper-id"), detail.paper_id, "完整论文 ID");
  setFullText($("task-type"), detail.task_type, "完整任务类型");
  setFullText($("answerability"), detail.expected_answerability, "完整可回答性");
  $("question").textContent = detail.question;
  $("evidence-count").textContent = `${detail.bounded_evidence.length} blocks`;
  const evidenceList = $("evidence-list");
  evidenceList.replaceChildren();
  detail.bounded_evidence.forEach((block) => {
    const card = element("article", "evidence-card");
    card.append(element("p", "", block.excerpt || "（空证据块）"));
    const locator = element("div", "evidence-locator mono", `${block.context_role || "evidence"} · ${block.source_locator}`);
    locator.title = String(block.source_locator);
    locator.setAttribute("aria-label", `完整证据来源定位：${block.source_locator}`);
    card.append(locator);
    evidenceList.append(card);
  });
}

function selectedMode() {
  return document.querySelector('input[name="mode"]:checked')?.value || "fixture";
}

function showStatus(text, kind = "idle") {
  $("run-status-text").textContent = text;
  const badge = $("run-state-badge");
  badge.className = "state-badge";
  badge.classList.add(kind === "failed" ? "state-failed" : kind === "success" ? "state-success" : kind === "active" ? "state-active" : "state-idle");
  badge.textContent = kind === "failed" ? "FAILED" : kind === "success" ? "COMPLETED" : kind === "active" ? "RUNNING" : "IDLE";
}

function startElapsed() {
  stopElapsed();
  state.runStartedAt = Date.now();
  const update = () => {
    const elapsed = Math.floor((Date.now() - state.runStartedAt) / 1000);
    const minutes = String(Math.floor(elapsed / 60)).padStart(2, "0");
    const seconds = String(elapsed % 60).padStart(2, "0");
    $("elapsed-time").textContent = `${minutes}:${seconds}`;
  };
  update();
  state.elapsedTimer = window.setInterval(update, 1000);
}

function stopElapsed() {
  if (state.elapsedTimer) window.clearInterval(state.elapsedTimer);
  state.elapsedTimer = null;
}

async function runSelectedCase() {
  if (!state.selectedCase || state.runInProgress) return;
  const mode = selectedMode();
  if (mode === "live" && (!state.config.live_enabled || !state.preflightPassed || $("live-mode").disabled)) return;
  if (mode === "live") {
    const confirmed = window.confirm(
      `将对案例 ${state.selectedCase.case_id} 使用 ${state.config.model} 发起一次真实请求。\n` +
      `max_tokens=${state.config.max_output_tokens}，客户端等待上限=${state.config.timeout_seconds} 秒。\n` +
      "仅尝试一次 POST 请求，不自动重试，可能消耗 USTC 项目 Token。确认继续？",
    );
    if (!confirmed) {
      state.runInProgress = false;
      $("run-button").disabled = false;
      return;
    }
  }
  state.runInProgress = true;
  $("run-button").disabled = true;
  showStatus("正在创建本地运行记录…", "active");
  startElapsed();
  try {
    const queued = await api("/api/runs", {
      method: "POST",
      body: JSON.stringify({case_id: state.selectedCase.case_id, mode}),
    });
    state.currentRun = queued.run_id;
    showStatus("queued · 等待单工作线程", "active");
    await pollRun(queued.poll_url);
  } catch (error) {
    stopElapsed();
    state.runInProgress = false;
    showStatus(`运行创建失败：${error.message}`, "failed");
    $("run-button").disabled = false;
  }
}

async function pollRun(url) {
  if (state.pollTimer) window.clearTimeout(state.pollTimer);
  try {
    const record = await api(url);
    if (record.status === "queued") showStatus("queued · 等待单工作线程", "active");
    if (record.status === "running") showStatus("running · 后台执行中", "active");
    if (terminalStates.has(record.status)) {
      stopElapsed();
      state.runInProgress = false;
      renderRun(record);
      showStatus(record.status === "failed" ? "failed" : `completed · ${record.status}`, record.status === "failed" ? "failed" : "success");
      $("run-button").disabled = false;
      await loadHistory();
      return;
    }
    state.pollTimer = window.setTimeout(() => pollRun(url), 1000);
  } catch (error) {
    stopElapsed();
    state.runInProgress = false;
    showStatus(`轮询失败：${error.message}`, "failed");
    $("run-button").disabled = false;
  }
}

function addStructuredItems(target, values, emptyText) {
  target.replaceChildren();
  if (!Array.isArray(values) || values.length === 0) {
    target.append(element("div", "muted", emptyText));
    return;
  }
  values.forEach((value) => target.append(element("div", "structured-item mono", typeof value === "string" ? value : JSON.stringify(value, null, 2))));
}

function renderRun(record) {
  $("result-empty").hidden = true;
  $("result-content").hidden = false;
  const modeBadge = $("result-mode");
  modeBadge.textContent = record.mode === "live" ? "LIVE API" : "FIXTURE";
  modeBadge.className = `badge ${record.mode === "live" ? "badge-live" : "badge-fixture"}`;
  $("answer-heading").textContent = record.mode === "live" ? "模型回答" : "演示结果";
  const parseBadge = $("parse-level");
  parseBadge.textContent = record.status === "failed" ? "FAILED" : (record.parse_level || "NO PARSE").toUpperCase();
  parseBadge.className = `badge ${record.status === "failed" ? "badge-failed" : ""}`;
  $("answer-text").textContent = record.answer_text || "（无可读回答）";
  const structured = record.structured_output || {};
  addStructuredItems($("claims-list"), structured.claims || [], "无 claims；不会补造。" );
  addStructuredItems($("citations-list"), record.citations || [], "无 citations；不会补造。" );
  const warnings = $("warnings-list");
  warnings.replaceChildren();
  (record.warnings || []).forEach((warning) => warnings.append(element("li", "mono", warning)));
  if ((record.warnings || []).length === 0) warnings.append(element("li", "muted", "无警告"));
  const errorBox = $("error-box");
  errorBox.hidden = record.status !== "failed";
  errorBox.textContent = record.status === "failed" ? `${record.safe_error_code || "failed"}: ${record.safe_error_message || "运行失败"}` : "";
  renderMetadata(record);
}

function renderMetadata(record) {
  const fixture = record.mode === "fixture";
  const noProviderRequest = "N/A · no provider request";
  $("metadata-provider").textContent = fixture ? "deterministic fixture" : (record.provider ?? "N/A");
  $("metadata-configured-model").textContent = fixture
    ? `${record.requested_model} · not called`
    : (record.requested_model ?? "N/A");
  $("metadata-reported-model").textContent = fixture ? "deterministic-fixture" : (record.reported_model ?? "N/A");
  $("metadata-response-id").textContent = fixture ? noProviderRequest : (record.provider_response_id ?? "N/A");
  $("metadata-http-status").textContent = fixture ? noProviderRequest : (record.http_status ?? "N/A");
  $("metadata-finish-reason").textContent = fixture ? noProviderRequest : (record.finish_reason ?? "N/A");
  $("metadata-latency").textContent = record.latency_seconds == null ? "N/A" : `${record.latency_seconds}s`;
  $("metadata-usage").textContent = fixture ? noProviderRequest : (record.usage ? JSON.stringify(record.usage) : "N/A");
  $("metadata-timeout").textContent = fixture
    ? `${record.timeout_seconds}s · not used by fixture`
    : `${record.timeout_seconds}s`;
  $("metadata-max-tokens").textContent = fixture
    ? `${record.max_output_tokens} · not used by fixture`
    : String(record.max_output_tokens ?? "N/A");
}

function selectFixtureMode() {
  document.querySelector('input[name="mode"][value="fixture"]').checked = true;
  $("live-mode").checked = false;
}

function renderPreflight(result, passed) {
  const lines = [
    `status: ${result.status ?? "failed"}`,
    `HTTP status: ${result.http_status ?? "N/A"}`,
    `model count: ${result.model_count ?? 0}`,
    `target model: ${result.target_model ?? state.config.model}`,
    `target model visible: ${result.target_model_visible === true ? "true" : "false"}`,
    `latency: ${result.latency_seconds == null ? "N/A" : `${result.latency_seconds}s`}`,
    `checked time: ${result.checked_at_utc ?? "N/A"}`,
  ];
  if (result.safe_error_code) lines.push(`safe error code: ${result.safe_error_code}`);
  lines.push("模型权限检查不会发送 chat-completion 请求。");
  if (!passed) lines.push("Live 执行仍处于禁用状态。");
  const target = $("preflight-result");
  target.className = `preflight-result ${passed ? "preflight-success" : "preflight-failed"}`;
  target.textContent = lines.join("\n");
}

async function runPreflight() {
  const button = $("preflight-button");
  state.preflightPassed = false;
  $("live-mode").disabled = true;
  selectFixtureMode();
  button.disabled = true;
  $("preflight-result").className = "preflight-result";
  $("preflight-result").textContent = "正在执行显式模型权限检查…\n模型权限检查不会发送 chat-completion 请求。";
  try {
    const result = await api("/api/preflight/models", {method: "POST", body: "{}"});
    const passed = result.status === "succeeded" && result.http_status === 200 && result.target_model_visible === true;
    state.preflightPassed = passed;
    $("live-mode").disabled = !passed;
    if (!passed) selectFixtureMode();
    renderPreflight(result, passed);
  } catch (error) {
    state.preflightPassed = false;
    $("live-mode").disabled = true;
    selectFixtureMode();
    renderPreflight({
      status: "failed",
      http_status: error.payload?.http_status,
      model_count: 0,
      target_model: state.config.model,
      target_model_visible: false,
      safe_error_code: error.payload?.safe_error_code || "preflight_request_failed",
    }, false);
  } finally {
    button.disabled = !state.config.live_enabled;
  }
}

async function loadHistory() {
  try {
    const result = await api("/api/runs?limit=20");
    const body = $("history-body");
    body.replaceChildren();
    if (!result.runs.length) {
      const row = element("tr");
      const cell = element("td", "empty-cell", "暂无运行记录");
      cell.colSpan = 5;
      row.append(cell);
      body.append(row);
      return;
    }
    result.runs.forEach((run) => {
      const row = element("tr");
      row.dataset.runId = run.run_id;
      [
        new Date(run.created_at_utc).toLocaleString(), run.case_id, run.mode.toUpperCase(),
        run.status, run.latency_seconds == null ? "—" : `${run.latency_seconds}s`,
      ].forEach((value) => row.append(element("td", value === run.case_id ? "mono" : "", value)));
      row.tabIndex = 0;
      row.addEventListener("click", () => openHistory(run.run_id));
      row.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") openHistory(run.run_id);
      });
      body.append(row);
    });
  } catch (error) {
    $("history-body").replaceChildren(element("tr", "", `历史加载失败：${error.message}`));
  }
}

async function openHistory(runId) {
  try {
    const record = await api(`/api/runs/${encodeURIComponent(runId)}`);
    if (state.selectedCase?.case_id !== record.case_id) await selectCase(record.case_id);
    state.currentRun = runId;
    renderRun(record);
    showStatus(`history · ${record.status}`, record.status === "failed" ? "failed" : "success");
  } catch (error) {
    showStatus(`历史记录加载失败：${error.message}`, "failed");
  }
}

async function initialize() {
  try {
    const [health, config, cases] = await Promise.all([
      api("/health"), api("/api/config"), api("/api/cases"),
    ]);
    setConnection(health.status === "ok");
    renderConfig(config);
    state.cases = cases.cases;
    renderCaseList();
    if (state.cases.length) await selectCase(state.cases[0].case_id);
    await loadHistory();
  } catch (error) {
    setConnection(false);
    showStatus(`初始化失败：${error.message}`, "failed");
  }
}

$("run-button").addEventListener("click", runSelectedCase);
$("preflight-button").addEventListener("click", runPreflight);
$("refresh-history").addEventListener("click", loadHistory);
initialize();
