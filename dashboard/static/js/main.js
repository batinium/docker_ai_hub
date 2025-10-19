const forms = document.querySelectorAll(".try-form");
const copyButtons = document.querySelectorAll(".copy-button");
const serviceToggles = Array.from(document.querySelectorAll(".service-toggle"));
const serviceChips = Array.from(document.querySelectorAll(".service-chip"));
const statusDots = Array.from(document.querySelectorAll("[data-service-status]"));
const topBar = document.querySelector(".top-bar");
const serviceNav = document.querySelector(".service-nav");
const apiKeyForm = document.querySelector(".api-key-form");
const apiKeyInput = document.querySelector(".api-key-input");
const apiKeyStatus = document.querySelector("[data-api-key-status]");
const apiKeyClear = document.querySelector(".api-key-clear");
const LOCAL_STORAGE_KEY = "dashboardApiKey";
let apiKey = localStorage.getItem(LOCAL_STORAGE_KEY) || "";
let initialActiveService = null;

function setApiKey(newKey) {
  apiKey = newKey.trim();
  if (apiKey) {
    localStorage.setItem(LOCAL_STORAGE_KEY, apiKey);
  } else {
    localStorage.removeItem(LOCAL_STORAGE_KEY);
  }
  updateApiKeyStatus();
  fetchStatuses();
}

function updateApiKeyStatus() {
  if (!apiKeyStatus) {
    return;
  }
  if (apiKey) {
    apiKeyStatus.textContent = "Key saved";
    apiKeyStatus.classList.add("active");
  } else {
    apiKeyStatus.textContent = "Not set";
    apiKeyStatus.classList.remove("active");
  }
}

if (apiKeyForm && apiKeyInput) {
  apiKeyForm.addEventListener("submit", (event) => {
    event.preventDefault();
    setApiKey(apiKeyInput.value);
    apiKeyInput.value = "";
  });
}

if (apiKeyClear) {
  apiKeyClear.addEventListener("click", () => {
    setApiKey("");
  });
}

setApiKey(apiKey);

function authFetch(url, options = {}) {
  const opts = { ...options };
  if (apiKey) {
    const headers =
      opts.headers instanceof Headers ? opts.headers : new Headers(opts.headers || {});
    headers.set("X-API-Key", apiKey);
    opts.headers = headers;
  }
  return fetch(url, opts);
}

function getServiceIdFromToggle(button) {
  return button.dataset.service;
}

function setActiveService(serviceId) {
  serviceToggles.forEach((button) => {
    button.classList.toggle("active", getServiceIdFromToggle(button) === serviceId);
  });
  serviceChips.forEach((chip) => {
    chip.classList.toggle("active", chip.dataset.service === serviceId);
  });
}

function collapseToggle(button) {
  const panelId = button.dataset.target;
  const panel = panelId ? document.getElementById(panelId) : null;
  if (!panel) {
    return;
  }
  button.setAttribute("aria-expanded", "false");
  panel.setAttribute("hidden", "true");
  button.classList.remove("active");

  const anyExpanded = serviceToggles.some((toggle) => toggle.getAttribute("aria-expanded") === "true");
  if (!anyExpanded) {
    setActiveService("");
  }
}

function expandToggle(button) {
  const panelId = button.dataset.target;
  const panel = panelId ? document.getElementById(panelId) : null;
  if (!panel) {
    return;
  }
  serviceToggles.forEach((other) => {
    if (other !== button) {
      collapseToggle(other);
    }
  });
  button.setAttribute("aria-expanded", "true");
  panel.removeAttribute("hidden");
  const serviceId = getServiceIdFromToggle(button);
  if (serviceId) {
    setActiveService(serviceId);
    const infoSection = panel.querySelector(`[data-service-info]`);
    if (infoSection) {
      loadServiceInfo(serviceId, infoSection);
    }
  }
}

function scrollPanelIntoView(panel) {
  if (!panel) {
    return;
  }
  const navHeight = serviceNav ? serviceNav.offsetHeight : 0;
  const topBarHeight = topBar ? topBar.offsetHeight : 0;
  const offset = topBarHeight + navHeight + 16;
  const y = panel.getBoundingClientRect().top + window.pageYOffset - offset;
  window.scrollTo({ top: y, behavior: "smooth" });
}

serviceToggles.forEach((button) => {
  const expanded = button.getAttribute("aria-expanded") === "true";
  const panelId = button.dataset.target;
  const panel = panelId ? document.getElementById(panelId) : null;
  if (!expanded && panel && !panel.hasAttribute("hidden")) {
    panel.setAttribute("hidden", "true");
  }

  if (expanded && !initialActiveService) {
    initialActiveService = getServiceIdFromToggle(button);
    if (panel) {
      const infoSection = panel.querySelector(`[data-service-info]`);
      if (infoSection) {
        loadServiceInfo(initialActiveService, infoSection);
      }
    }
  }

  button.addEventListener("click", () => {
    const isExpanded = button.getAttribute("aria-expanded") === "true";
    if (isExpanded) {
      collapseToggle(button);
    } else {
      expandToggle(button);
    }
  });

  button.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      button.click();
    }
  });
});

if (!initialActiveService && serviceToggles.length > 0) {
  initialActiveService = getServiceIdFromToggle(serviceToggles[0]);
  expandToggle(serviceToggles[0]);
}

if (initialActiveService) {
  setActiveService(initialActiveService);
}

serviceChips.forEach((chip) => {
  chip.addEventListener("click", () => {
    const serviceId = chip.dataset.service;
    if (!serviceId) {
      return;
    }
    const targetToggle = serviceToggles.find((toggle) => getServiceIdFromToggle(toggle) === serviceId);
    if (!targetToggle) {
      return;
    }
    expandToggle(targetToggle);
    const panelId = targetToggle.dataset.target;
    const panel = panelId ? document.getElementById(panelId) : null;
    scrollPanelIntoView(panel);
  });
});

function setStatusDot(serviceId, state, detail) {
  statusDots
    .filter((dot) => dot.dataset.serviceStatus === serviceId)
    .forEach((dot) => {
      dot.dataset.state = state;
      const title = detail || (state === "ok" ? "Gateway reachable" : "Status pending");
      dot.setAttribute("title", title);
    });
}

async function fetchStatuses() {
  if (statusDots.length === 0) {
    return;
  }
  if (!apiKey) {
    statusDots.forEach((dot) => {
      dot.dataset.state = "unknown";
      dot.setAttribute("title", "Set the dashboard API key to fetch status.");
    });
    return;
  }
  try {
    const response = await authFetch("/api/service-status");
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const payload = await response.json();
    const statuses = payload.statuses || {};
    statusDots.forEach((dot) => {
      const serviceId = dot.dataset.serviceStatus;
      const info = statuses[serviceId];
      if (!info) {
        setStatusDot(serviceId, "unknown", "Status unavailable");
        return;
      }
      setStatusDot(serviceId, info.ok ? "ok" : "error", info.detail || "");
    });
  } catch (error) {
    statusDots.forEach((dot) => {
      dot.dataset.state = "unknown";
      dot.setAttribute("title", `Status unavailable: ${error}`);
    });
  }
}

setInterval(fetchStatuses, 60000);

async function loadServiceInfo(serviceId, section, force = false) {
  if (!section || !serviceId) {
    return;
  }
  const body = section.querySelector(".live-body");
  if (!body) {
    return;
  }
  const state = section.dataset.state;
  if (!force && (state === "loaded" || state === "loading")) {
    return;
  }
  if (!apiKey) {
    section.dataset.state = "error";
    renderPlaceholder(body, "Set the dashboard API key (top bar) to load data.");
    return;
  }
  section.dataset.state = "loading";
  renderPlaceholder(body, "Loading...");
  try {
    const response = await authFetch(`/api/service-info/${serviceId}`);
    if (!response.ok) {
      const detail = await response.text();
      throw new Error(detail || `HTTP ${response.status}`);
    }
    const payload = await response.json();
    const content = payload.data ?? payload;
    renderLiveData(body, serviceId, content);
    section.dataset.state = "loaded";
  } catch (error) {
    section.dataset.state = "error";
    renderPlaceholder(body, `Unable to load info: ${error}`);
  }
}

document.querySelectorAll(".live-refresh").forEach((button) => {
  button.addEventListener("click", () => {
    const serviceId = button.dataset.service;
    const section = button.closest("[data-service-info]");
    loadServiceInfo(serviceId, section, true);
  });
});

async function copyToClipboard(text) {
  if (navigator.clipboard && window.isSecureContext) {
    await navigator.clipboard.writeText(text);
    return;
  }

  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.style.position = "fixed";
  textarea.style.top = "-1000px";
  textarea.style.left = "-1000px";
  document.body.appendChild(textarea);
  textarea.focus();
  textarea.select();
  const successful = document.execCommand("copy");
  document.body.removeChild(textarea);
  if (!successful) {
    throw new Error("Clipboard copy failed");
  }
}

function summarizeEntry(entry) {
  if (entry == null) {
    return "(unknown)";
  }
  if (typeof entry === "string") {
    return entry;
  }
  if (typeof entry === "number") {
    return entry.toString();
  }
  if (typeof entry === "object") {
    return (
      entry.id ||
      entry.name ||
      entry.model ||
      entry.label ||
      entry.voice ||
      JSON.stringify(entry)
    );
  }
  return String(entry);
}

function renderLiveData(container, serviceId, data) {
  const list = document.createElement("div");
  list.className = "live-list";
  let entries = [];
  let heading = "";
  let total = null;

  if (Array.isArray(data.models)) {
    heading = "Models";
    entries = data.models;
    total = data.count ?? entries.length;
  } else if (Array.isArray(data.voices)) {
    heading = "Voices";
    entries = data.voices;
    total = data.count ?? entries.length;
  } else if (Array.isArray(data)) {
    entries = data;
  }

  if (entries.length > 0) {
    const headingEl = document.createElement("p");
    headingEl.className = "live-meta";
    const compactHeading = heading || "Items";
    headingEl.textContent = total != null ? `${compactHeading}: ${total}` : compactHeading;

    const ul = document.createElement("ul");
    ul.className = "live-items";
    entries.slice(0, 10).forEach((entry) => {
      const li = document.createElement("li");
      li.textContent = summarizeEntry(entry);
      ul.append(li);
    });
    if (entries.length > 10) {
      const more = document.createElement("p");
      more.className = "live-meta";
      more.textContent = `...and ${entries.length - 10} more`;
      container.innerHTML = "";
      container.append(headingEl, ul, more);
      return;
    }
    container.innerHTML = "";
    container.append(headingEl, ul);
    return;
  }

  container.innerHTML = "";
  container.append(makePre(data));
}

function makePre(obj) {
  const pre = document.createElement("pre");
  pre.textContent = typeof obj === "string" ? obj : JSON.stringify(obj, null, 2);
  return pre;
}

function renderResponse(container, fragment) {
  container.innerHTML = "";
  container.append(fragment);
}

function renderPlaceholder(container, text) {
  container.innerHTML = "";
  const p = document.createElement("p");
  p.className = "placeholder";
  p.textContent = text;
  container.append(p);
}

function renderChat(container, data) {
  const wrapper = document.createElement("div");
  const status = document.createElement("p");
  status.innerHTML = `<strong>Status:</strong> ${data.status}`;
  const model = document.createElement("p");
  const firstChoice = data.response?.choices?.[0];
  const content = firstChoice?.message?.content ?? "(no content returned)";

  model.innerHTML = `<strong>Model:</strong> ${data.response?.model ?? "unknown"}`;
  const message = document.createElement("pre");
  message.textContent = content;

  wrapper.append(status, model, message);
  renderResponse(container, wrapper);
}

function renderTts(container, data) {
  const wrapper = document.createElement("div");
  const status = document.createElement("p");
  status.innerHTML = `<strong>Status:</strong> ${data.status}`;

  const audio = document.createElement("audio");
  audio.controls = true;
  audio.src = data.audio;

  const download = document.createElement("a");
  download.href = data.audio;
  download.download = data.filename || "speech.mp3";
  download.textContent = `Download ${data.filename || "speech.mp3"}`;

  wrapper.append(status, audio, download, makePre(data));
  renderResponse(container, wrapper);
}

function renderGeneric(container, data) {
  renderResponse(container, makePre(data));
}

function renderModels(container, data) {
  const wrapper = document.createElement("div");
  const status = document.createElement("p");
  status.innerHTML = `<strong>Status:</strong> ${data.status}`;

  const list = document.createElement("ul");
  list.style.paddingLeft = "1.2rem";
  const models = data.response?.data;
  if (Array.isArray(models) && models.length > 0) {
    models.forEach((item) => {
      const li = document.createElement("li");
      const id = item.id || "(unknown id)";
      const owned = item.owned_by ? ` — ${item.owned_by}` : "";
      li.textContent = `${id}${owned}`;
      list.append(li);
    });
  } else {
    const empty = document.createElement("p");
    empty.textContent = "No models reported.";
    wrapper.append(status, empty);
    renderResponse(container, wrapper);
    return;
  }

  wrapper.append(status, list, makePre(data.response));
  renderResponse(container, wrapper);
}

function renderEmbeddings(container, data) {
  const wrapper = document.createElement("div");
  const status = document.createElement("p");
  status.innerHTML = `<strong>Status:</strong> ${data.status}`;
  wrapper.append(status);

  const vector = data.response?.data?.[0]?.embedding;
  if (Array.isArray(vector)) {
    const dims = vector.length;
    const preview = vector.slice(0, 8).map((value) => {
      if (typeof value !== "number") {
        return String(value);
      }
      return Number.isFinite(value) ? value.toFixed(4) : String(value);
    });

    const dimensions = document.createElement("p");
    dimensions.innerHTML = `<strong>Dimensions:</strong> ${dims}`;

    const previewEl = document.createElement("p");
    previewEl.innerHTML = `<strong>Preview:</strong> [${preview.join(", ")}${dims > preview.length ? "…" : ""}]`;

    wrapper.append(dimensions, previewEl);
  }

  wrapper.append(makePre(data.response ?? data));
  renderResponse(container, wrapper);
}

async function handleSubmit(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const serviceId = form.dataset.service;
  const endpoint = form.dataset.endpoint;
  const method = form.dataset.method || "POST";
  const container = document.getElementById(`${serviceId}-response`);

  if (!endpoint) {
    renderPlaceholder(container, "Missing endpoint configuration.");
    return;
  }

  if (!apiKey) {
    renderPlaceholder(container, "Set the dashboard API key (top bar) before sending requests.");
    return;
  }

  renderPlaceholder(container, "Request in flight...");

  let response;
  try {
    const formData = new FormData(form);
    response = await authFetch(endpoint, {
      method,
      body: formData,
    });
  } catch (error) {
    renderPlaceholder(container, `Request failed: ${error}`);
    return;
  }

  let data;
  try {
    data = await response.json();
  } catch (error) {
    renderPlaceholder(container, `Unable to parse JSON: ${error}`);
    return;
  }

  if (!response.ok) {
    renderPlaceholder(container, data?.detail || `Request failed with status ${response.status}`);
    return;
  }

  if (
    serviceId === "lmstudio-chat" ||
    serviceId === "openwebui-chat" ||
    serviceId === "gateway-ollama-chat"
  ) {
    renderChat(container, data);
  } else if (serviceId === "lmstudio-models") {
    renderModels(container, data);
  } else if (serviceId === "kokoro-tts") {
    renderTts(container, data);
  } else if (serviceId === "lmstudio-embeddings") {
    renderEmbeddings(container, data);
  } else {
    renderGeneric(container, data);
  }
}

forms.forEach((form) => form.addEventListener("submit", handleSubmit));

copyButtons.forEach((button) => {
  button.addEventListener("click", async () => {
    const text = button.dataset.copy.replace(/&#10;/g, "\n").replace(/&quot;/g, '"');
    try {
      await copyToClipboard(text);
      button.textContent = "Copied!";
      setTimeout(() => {
        button.textContent = "Copy";
      }, 2000);
    } catch (error) {
      button.textContent = "Copy failed";
      setTimeout(() => {
        button.textContent = "Copy";
      }, 2000);
    }
  });
});
