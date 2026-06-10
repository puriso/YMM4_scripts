const state = {
  scripts: [],
  selectedKey: null,
  activeRunId: null,
  pollTimer: null,
};

const el = {
  scriptList: document.querySelector("#scriptList"),
  scriptTitle: document.querySelector("#scriptTitle"),
  scriptDescription: document.querySelector("#scriptDescription"),
  warningBox: document.querySelector("#warningBox"),
  optionsForm: document.querySelector("#optionsForm"),
  runButton: document.querySelector("#runButton"),
  stopButton: document.querySelector("#stopButton"),
  copyCommandButton: document.querySelector("#copyCommandButton"),
  logOutput: document.querySelector("#logOutput"),
  logPath: document.querySelector("#logPath"),
  statusBadge: document.querySelector("#statusBadge"),
};

async function init() {
  const response = await fetch("/api/scripts");
  const data = await response.json();
  state.scripts = data.scripts;
  renderScriptList();
  selectScript(state.scripts[0]?.key);
}

function renderScriptList() {
  el.scriptList.innerHTML = "";
  for (const script of state.scripts) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "script-tab";
    button.textContent = script.title;
    button.dataset.key = script.key;
    button.addEventListener("click", () => selectScript(script.key));
    el.scriptList.appendChild(button);
  }
}

function selectScript(key) {
  const script = state.scripts.find((item) => item.key === key);
  if (!script) return;

  state.selectedKey = key;
  document.querySelectorAll(".script-tab").forEach((button) => {
    button.classList.toggle("active", button.dataset.key === key);
  });

  el.scriptTitle.textContent = script.title;
  el.scriptDescription.textContent = script.description;
  el.runButton.textContent = script.runLabel || "実行";
  el.logOutput.textContent = "ログはここに表示されます。";
  el.logPath.textContent = "";
  setStatus("idle", "待機中");

  if (script.warning) {
    el.warningBox.textContent = script.warning;
    el.warningBox.classList.remove("hidden");
  } else {
    el.warningBox.classList.add("hidden");
  }

  renderOptions(script);
}

function renderOptions(script) {
  el.optionsForm.innerHTML = "";

  for (const field of script.fields) {
    const wrapper = document.createElement("div");
    wrapper.className = field.kind === "bool" ? "field checkbox" : "field";

    const inputId = `field-${field.key}`;

    if (field.kind === "bool") {
      const input = document.createElement("input");
      input.type = "checkbox";
      input.id = inputId;
      input.name = field.key;
      input.checked = Boolean(field.default);

      const label = document.createElement("label");
      label.htmlFor = inputId;
      label.textContent = field.label;

      wrapper.append(input, label);
    } else {
      const label = document.createElement("label");
      label.htmlFor = inputId;
      label.textContent = field.required ? `${field.label} *` : field.label;

      const input = document.createElement("input");
      input.type = field.kind === "int" ? "number" : "text";
      input.id = inputId;
      input.name = field.key;
      input.value = field.default ?? "";
      input.placeholder = field.placeholder || "";
      if (field.kind === "int") input.min = "0";

      wrapper.append(label, input);
    }

    if (field.helpText) {
      const help = document.createElement("div");
      help.className = "field-help";
      help.textContent = field.helpText;
      wrapper.appendChild(help);
    }

    el.optionsForm.appendChild(wrapper);
  }
}

function collectOptions() {
  const script = getSelectedScript();
  const options = {};

  for (const field of script.fields) {
    const input = el.optionsForm.elements[field.key];
    if (!input) continue;
    options[field.key] = field.kind === "bool" ? input.checked : input.value.trim();
  }

  return options;
}

function getSelectedScript() {
  return state.scripts.find((script) => script.key === state.selectedKey);
}

async function runScript() {
  const script = getSelectedScript();
  if (!script) return;

  const options = collectOptions();
  const validationError = validateOptions(script, options);
  if (validationError) {
    setStatus("failed", "入力エラー");
    el.logOutput.textContent = validationError;
    return;
  }

  setRunning(true);
  el.logOutput.textContent = "起動中...\n";
  el.logPath.textContent = "";
  setStatus("running", "実行中");

  try {
    const response = await fetch("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scriptKey: script.key, options }),
    });
    const data = await readJsonResponse(response);

    if (!response.ok) {
      setRunning(false);
      setStatus("failed", "エラー");
      el.logOutput.textContent = data.error || "起動に失敗しました。";
      return;
    }

    state.activeRunId = data.runId;
    updateRun(data);
    startPolling();
  } catch (error) {
    setRunning(false);
    setStatus("failed", "エラー");
    el.logOutput.textContent = `起動に失敗しました。\n${error}`;
  }
}

function startPolling() {
  clearInterval(state.pollTimer);
  state.pollTimer = setInterval(async () => {
    if (!state.activeRunId) return;

    try {
      const response = await fetch(`/api/runs/${state.activeRunId}`);
      const data = await readJsonResponse(response);
      updateRun(data);

      if (data.status !== "running" && data.status !== "stopping") {
        clearInterval(state.pollTimer);
        state.pollTimer = null;
        state.activeRunId = null;
        setRunning(false);
      }
    } catch (error) {
      clearInterval(state.pollTimer);
      state.pollTimer = null;
      state.activeRunId = null;
      setRunning(false);
      setStatus("failed", "通信エラー");
      el.logOutput.textContent += `\nポーリングに失敗しました。\n${error}`;
    }
  }, 600);
}

function updateRun(run) {
  el.logOutput.textContent = run.output || "";
  el.logOutput.scrollTop = el.logOutput.scrollHeight;
  el.logPath.textContent = run.logPath || "";

  if (run.status === "running" || run.status === "stopping") {
    setStatus("running", run.status === "stopping" ? "停止中" : "実行中");
  } else if (run.status === "success") {
    setStatus("success", "完了");
  } else {
    setStatus("failed", "失敗");
  }
}

async function stopScript() {
  if (!state.activeRunId) return;
  try {
    await fetch(`/api/runs/${state.activeRunId}/stop`, { method: "POST" });
    setStatus("running", "停止中");
  } catch (error) {
    setStatus("failed", "停止失敗");
    el.logOutput.textContent += `\n停止リクエストに失敗しました。\n${error}`;
  }
}

async function copyCommand() {
  const script = getSelectedScript();
  if (!script) return;

  const parts = ["python", script.scriptPath];
  const options = collectOptions();
  for (const field of script.fields) {
    const value = options[field.key];
    if (field.kind === "bool") {
      if (value) parts.push(field.flag);
    } else if (value) {
      parts.push(field.flag, quoteForDisplay(value));
    }
  }

  const command = parts.join(" ");
  try {
    await navigator.clipboard.writeText(command);
    setStatus("idle", "コピー済み");
  } catch {
    el.logOutput.textContent = command;
    setStatus("idle", "ログ欄に表示");
  }
}

function quoteForDisplay(value) {
  return /\s/.test(value) ? `"${value.replaceAll('"', '\\"')}"` : value;
}

function validateOptions(script, options) {
  for (const field of script.fields) {
    const value = options[field.key];
    if (field.kind !== "bool" && field.required && !value) {
      return `${field.label} を指定してください。`;
    }
    if (field.kind === "int" && value !== "") {
      const number = Number(value);
      if (!Number.isInteger(number) || number < 0) {
        return `${field.label} は0以上の整数で指定してください。`;
      }
    }
  }
  return "";
}

async function readJsonResponse(response) {
  const text = await response.text();
  if (!text) return {};
  try {
    return JSON.parse(text);
  } catch (error) {
    throw new Error(`JSON応答の解析に失敗しました: ${error}`);
  }
}

function setRunning(isRunning) {
  el.runButton.disabled = isRunning;
  el.stopButton.disabled = !isRunning;
}

function setStatus(kind, text) {
  el.statusBadge.className = `status-badge ${kind === "idle" ? "" : kind}`;
  el.statusBadge.textContent = text;
}

el.runButton.addEventListener("click", runScript);
el.stopButton.addEventListener("click", stopScript);
el.copyCommandButton.addEventListener("click", copyCommand);

init().catch((error) => {
  setStatus("failed", "エラー");
  el.logOutput.textContent = String(error);
});
