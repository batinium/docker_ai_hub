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
const viewButtons = Array.from(document.querySelectorAll("[data-view-button]"));
const viewPanels = Array.from(document.querySelectorAll(".view-panel"));
const LOCAL_STORAGE_KEY = "dashboardApiKey";
let apiKey = localStorage.getItem(LOCAL_STORAGE_KEY) || "";
let apiKeyValid = false;
let initialActiveService = null;

let activeView = (viewButtons.find((btn) => btn.classList.contains("active"))?.dataset.viewButton) || "services";

const monitoringRefreshButton = document.querySelector("[data-monitoring-refresh]");
const monitoringWindowSelect = document.querySelector("[data-monitoring-window]");
const monitoringStatus = document.querySelector("[data-monitoring-status]");
const monitoringMetrics = {
  total: document.querySelector("[data-metric-total]"),
  clients: document.querySelector("[data-metric-clients]"),
  keys: document.querySelector("[data-metric-keys]"),
  flagged: document.querySelector("[data-metric-flagged]"),
  userAgents: document.querySelector("[data-metric-user-agents]"),
};
const monitoringLists = {
  statuses: document.querySelector("[data-monitoring-statuses]"),
  apiKeys: document.querySelector("[data-monitoring-api-keys]"),
  clients: document.querySelector("[data-monitoring-clients]"),
  endpoints: document.querySelector("[data-monitoring-endpoints]"),
  userAgents: document.querySelector("[data-monitoring-user-agents]"),
};
const monitoringAlertsContainer = document.querySelector("[data-monitoring-alerts]");
const monitoringTableBody = document.querySelector("[data-monitoring-table-body]");
const monitoringFilterInput = document.querySelector("[data-monitoring-filter]");

const monitoringActive = Boolean(monitoringStatus);
const MONITORING_SUMMARY_LIMIT = 2000;
const MONITORING_EVENTS_LIMIT = 200;
const FLAG_LABELS = {
  upstream_error: { label: "Upstream error", tone: "danger" },
  client_error: { label: "Client error", tone: "warning" },
  no_api_key: { label: "Missing API key", tone: "warning" },
  suspicious_path: { label: "Suspicious path", tone: "danger" },
  very_slow: { label: "Slow response", tone: "info" },
};

const numberFormatter = new Intl.NumberFormat();
let monitoringWindow = monitoringWindowSelect ? Number(monitoringWindowSelect.value) || 60 : 60;
let monitoringLoading = false;
let monitoringViewActive = activeView === "monitoring";
let monitoringEvents = [];
let monitoringFilterText = "";
const DEFAULT_MONITORING_EMPTY_MESSAGE = "No gateway traffic observed in the selected window.";
let monitoringEmptyMessage = DEFAULT_MONITORING_EMPTY_MESSAGE;

function setApiKeyStatus(text, state) {
  if (!apiKeyStatus) {
    return;
  }
  apiKeyStatus.textContent = text;
  apiKeyStatus.classList.remove("active", "error", "pending");
  if (state) {
    apiKeyStatus.classList.add(state);
  }
}

async function verifyApiKey(candidate) {
  if (!candidate) {
    return false;
  }
  try {
    const response = await fetch("/api/auth/verify", {
      headers: {
        "X-API-Key": candidate,
      },
      cache: "no-store",
    });
    return response.ok;
  } catch (error) {
    console.warn("API key verification failed:", error);
    return false;
  }
}

async function setApiKey(newKey, options = {}) {
  const { skipValidation = false, silent = false } = options;
  const candidate = (newKey || "").trim();

  if (!candidate) {
    apiKey = "";
    apiKeyValid = false;
    localStorage.removeItem(LOCAL_STORAGE_KEY);
    if (!silent) {
      setApiKeyStatus("Not set", null);
    }
    fetchStatuses();
    if (monitoringActive && monitoringViewActive) {
      loadMonitoringData();
    }
    return true;
  }

  if (!skipValidation) {
    setApiKeyStatus("Validating…", "pending");
    const valid = await verifyApiKey(candidate);
    if (!valid) {
      apiKeyValid = false;
      if (!silent) {
        setApiKeyStatus("Invalid key", "error");
      } else {
        setApiKeyStatus("Not set", null);
      }
      return false;
    }
  }

  apiKey = candidate;
  apiKeyValid = true;
  localStorage.setItem(LOCAL_STORAGE_KEY, apiKey);
  setApiKeyStatus("Key saved", "active");
  fetchStatuses();
  if (monitoringActive && monitoringViewActive) {
    loadMonitoringData();
  }
  return true;
}

if (apiKeyForm && apiKeyInput) {
  apiKeyForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const value = apiKeyInput.value;
    const ok = await setApiKey(value);
    if (ok) {
      apiKeyInput.value = "";
    }
  });
}

if (apiKeyClear) {
  apiKeyClear.addEventListener("click", async () => {
    await setApiKey("", { skipValidation: true });
  });
}

if (apiKey) {
  setApiKey(apiKey, { silent: true }).then((ok) => {
    if (!ok) {
      setApiKeyStatus("Invalid key", "error");
    }
  });
} else {
  setApiKeyStatus("Not set", null);
}

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

function formatNumber(value) {
  if (typeof value !== "number") {
    value = Number(value || 0);
  }
  return numberFormatter.format(value);
}

function abbreviateApiKey(key) {
  if (!key || key === "(none)") {
    return "No key";
  }
  if (key.length <= 12) {
    return key;
  }
  return `${key.slice(0, 4)}…${key.slice(-4)}`;
}

function formatDuration(ms) {
  if (ms == null || Number.isNaN(ms)) {
    return "—";
  }
  if (ms < 1000) {
    return `${ms} ms`;
  }
  return `${(ms / 1000).toFixed(2)} s`;
}

function formatTimestamp(iso) {
  if (!iso) {
    return "(unknown)";
  }
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return iso;
  }
  return date.toLocaleString();
}

function formatRelativeTime(iso) {
  if (!iso) {
    return "";
  }
  const now = Date.now();
  const value = new Date(iso).getTime();
  if (Number.isNaN(value)) {
    return "";
  }
  const diffMs = now - value;
  if (diffMs < 0) {
    return "in the future";
  }
  const minutes = Math.floor(diffMs / 60000);
  if (minutes < 1) {
    return "just now";
  }
  if (minutes < 60) {
    return `${minutes} min${minutes === 1 ? "" : "s"} ago`;
  }
  const hours = Math.floor(minutes / 60);
  if (hours < 24) {
    return `${hours} hour${hours === 1 ? "" : "s"} ago`;
  }
  const days = Math.floor(hours / 24);
  return `${days} day${days === 1 ? "" : "s"} ago`;
}

function normalizeFilterValue(value) {
  return (value || "").trim().toLowerCase();
}

function applyMonitoringFilter(events) {
  if (!monitoringFilterText) {
    return events;
  }
  const search = monitoringFilterText;
  return events.filter((event) => {
    const client = (event.client_ip || "").toLowerCase();
    if (client.includes(search)) {
      return true;
    }
    const scope = (event.network_scope || "").toLowerCase();
    return scope.includes(search);
  });
}

function setMonitoringFilter(value) {
  const normalized = normalizeFilterValue(value);
  if (normalized === monitoringFilterText) {
    return;
  }
  monitoringFilterText = normalized;
  if (monitoringFilterInput && monitoringFilterInput.value !== value) {
    monitoringFilterInput.value = value;
  }
  if (monitoringActive) {
    renderMonitoringEvents();
  }
}

function setActiveView(view) {
  if (!view) {
    return;
  }
  activeView = view;
  viewButtons.forEach((button) => {
    button.classList.toggle("active", button.dataset.viewButton === view);
  });
  viewPanels.forEach((panel) => {
    const panelView = panel.dataset.view;
    if (!panelView) {
      return;
    }
    if (panelView === view) {
      panel.removeAttribute("hidden");
    } else {
      panel.setAttribute("hidden", "true");
    }
  });
  monitoringViewActive = view === "monitoring";
  if (monitoringActive && monitoringViewActive) {
    loadMonitoringData();
  }
}

function ensureListContent(container, items, builder, emptyMessage) {
  if (!container) {
    return;
  }
  container.innerHTML = "";
  if (!items || items.length === 0) {
    const li = document.createElement("li");
    li.className = "placeholder";
    li.textContent = emptyMessage;
    container.append(li);
    return;
  }
  items.forEach((item) => {
    const node = builder(item);
    if (node) {
      container.append(node);
    }
  });
}

function renderStatusList(statusFamilies) {
  const items = Object.entries(statusFamilies || {}).sort((a, b) => a[0].localeCompare(b[0]));
  ensureListContent(
    monitoringLists.statuses,
    items,
    ([code, count]) => {
      const li = document.createElement("li");
      const label = document.createElement("strong");
      label.textContent = code;
      const value = document.createElement("span");
      value.textContent = formatNumber(count);
      li.append(label, value);
      return li;
    },
    "No requests tracked."
  );
}

function renderTopApiKeys(apiKeys) {
  ensureListContent(
    monitoringLists.apiKeys,
    apiKeys,
    (item) => {
      const li = document.createElement("li");
      const label = document.createElement("strong");
      label.textContent = abbreviateApiKey(item.api_key);
      if (item.is_anonymous) {
        label.textContent = "No key";
      }
      const value = document.createElement("span");
      value.textContent = formatNumber(item.count);
      li.append(label, value);
      return li;
    },
    "No API key activity."
  );
}

function renderTopClients(clients) {
  ensureListContent(
    monitoringLists.clients,
    clients,
    (client) => {
      const li = document.createElement("li");
      const label = document.createElement("strong");
      const scope = client.network_scope ? ` (${client.network_scope})` : "";
      label.textContent = `${client.client}${scope}`;
      const value = document.createElement("span");
      value.textContent = formatNumber(client.count);
      li.append(label, value);
      return li;
    },
    "No client activity."
  );
}

function renderTopEndpoints(endpoints) {
  ensureListContent(
    monitoringLists.endpoints,
    endpoints,
    (endpoint) => {
      const li = document.createElement("li");
      const label = document.createElement("strong");
      label.textContent = endpoint.endpoint;
      const value = document.createElement("span");
      value.textContent = formatNumber(endpoint.count);
      li.append(label, value);
      return li;
    },
    "No endpoint activity."
  );
}

function renderTopUserAgents(userAgents) {
  ensureListContent(
    monitoringLists.userAgents,
    userAgents,
    (entry) => {
      const li = document.createElement("li");
      const label = document.createElement("strong");
      const agent = entry.user_agent || "(unknown)";
      const maxLen = 80;
      label.textContent = agent.length > maxLen ? `${agent.slice(0, maxLen - 1)}…` : agent;
      label.setAttribute("title", agent);
      const value = document.createElement("span");
      value.textContent = formatNumber(entry.count);
      li.append(label, value);
      return li;
    },
    "No user agent data."
  );
}

function renderMonitoringAlerts(alerts) {
  if (!monitoringAlertsContainer) {
    return;
  }
  monitoringAlertsContainer.innerHTML = "";
  if (!alerts || alerts.length === 0) {
    const p = document.createElement("p");
    p.className = "placeholder";
    p.textContent = "No alerts detected.";
    monitoringAlertsContainer.append(p);
    return;
  }
  alerts.forEach((alert) => {
    const item = document.createElement("div");
    const tone = alert.level || "info";
    item.className = `alert-item ${tone}`;
    const title = document.createElement("h4");
    title.textContent = alert.message || alert.type || "Alert";
    item.append(title);
    const details = [];
    if (alert.client) {
      details.push(`Client ${alert.client}`);
    }
    if (alert.count != null) {
      details.push(`${alert.count} events`);
    }
    if (alert.window_minutes) {
      details.push(`Window ${alert.window_minutes} min`);
    }
    if (alert.type && alert.type !== alert.message) {
      details.push(alert.type.replace(/_/g, " "));
    }
    if (details.length > 0) {
      const meta = document.createElement("p");
      meta.textContent = details.join(" · ");
      item.append(meta);
    }
    monitoringAlertsContainer.append(item);
  });
}

function resetMonitoringMetrics() {
  monitoringEvents = [];
  monitoringEmptyMessage = DEFAULT_MONITORING_EMPTY_MESSAGE;
  Object.values(monitoringMetrics).forEach((el) => {
    if (el) {
      el.textContent = "—";
    }
  });
  renderStatusList({});
  renderTopApiKeys([]);
  renderTopClients([]);
  renderTopEndpoints([]);
  renderTopUserAgents([]);
  renderMonitoringAlerts([]);
  if (monitoringTableBody) {
    monitoringTableBody.innerHTML = "";
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 7;
    cell.className = "placeholder";
    cell.textContent = "No monitoring data.";
    row.append(cell);
    monitoringTableBody.append(row);
  }
}

function renderMonitoringSummary(summary) {
  if (!monitoringActive) {
    return;
  }
  if (!summary) {
    resetMonitoringMetrics();
    return;
  }
  const totals = summary.totals || {};
  if (monitoringMetrics.total) {
    monitoringMetrics.total.textContent = formatNumber(totals.requests || 0);
  }
  if (monitoringMetrics.clients) {
    monitoringMetrics.clients.textContent = formatNumber(totals.unique_clients || 0);
  }
  if (monitoringMetrics.keys) {
    monitoringMetrics.keys.textContent = formatNumber(totals.unique_api_keys || 0);
  }
  if (monitoringMetrics.flagged) {
    monitoringMetrics.flagged.textContent = formatNumber(totals.flagged_requests || 0);
  }
  if (monitoringMetrics.userAgents) {
    monitoringMetrics.userAgents.textContent = formatNumber(totals.unique_user_agents || 0);
  }
  renderStatusList(summary.status_families || {});
  renderTopApiKeys(summary.top_api_keys || []);
  renderTopClients(summary.top_clients || []);
  renderTopEndpoints(summary.top_endpoints || []);
  renderTopUserAgents(summary.top_user_agents || []);
  renderMonitoringAlerts(summary.alerts || []);
}

function buildFlagBadges(flags) {
  if (!flags || flags.length === 0) {
    return null;
  }
  const wrapper = document.createElement("div");
  wrapper.className = "flags";
  flags.forEach((flag) => {
    const info = FLAG_LABELS[flag];
    const span = document.createElement("span");
    span.className = "flag";
    if (info?.tone) {
      span.classList.add(info.tone);
    }
    span.textContent = info?.label || flag;
    wrapper.append(span);
  });
  return wrapper;
}

function renderMonitoringEvents(data) {
  if (!monitoringTableBody) {
    return;
  }
  if (data !== undefined) {
    monitoringEvents = Array.isArray(data?.events) ? [...data.events].reverse() : [];
    const emptyMessage = data?.empty_message || data?.message;
    if (typeof emptyMessage === "string" && emptyMessage.trim().length > 0) {
      monitoringEmptyMessage = emptyMessage;
    } else {
      monitoringEmptyMessage = DEFAULT_MONITORING_EMPTY_MESSAGE;
    }
  }
  const visibleEvents = applyMonitoringFilter(monitoringEvents);

  monitoringTableBody.innerHTML = "";
  if (visibleEvents.length === 0) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 7;
    cell.className = "placeholder";
    const message = !apiKey
      ? "Set the dashboard API key to load monitoring data."
      : monitoringEvents.length === 0
      ? monitoringEmptyMessage
      : "No events match the current filter.";
    cell.textContent = message;
    row.append(cell);
    monitoringTableBody.append(row);
    return;
  }
  visibleEvents.forEach((event) => {
    const row = document.createElement("tr");
    if (event.is_flagged) {
      row.classList.add("is-flagged");
    }
    const timeCell = document.createElement("td");
    const timePrimary = document.createElement("div");
    timePrimary.textContent = formatTimestamp(event.timestamp);
    const timeSecondary = document.createElement("div");
    timeSecondary.className = "muted";
    timeSecondary.textContent = formatRelativeTime(event.timestamp);
    timeCell.append(timePrimary, timeSecondary);

    const clientCell = document.createElement("td");
    clientCell.textContent = event.client_ip || "-";

    const scopeCell = document.createElement("td");
    scopeCell.textContent = event.network_scope || "-";

    const apiKeyCell = document.createElement("td");
    const apiTag = document.createElement("span");
    apiTag.className = "tag";
    if (!event.api_key || event.api_key === "(none)") {
      apiTag.classList.add("anonymous");
      apiTag.textContent = "No key";
    } else {
      apiTag.textContent = abbreviateApiKey(event.api_key);
    }
    apiKeyCell.append(apiTag);

    const endpointCell = document.createElement("td");
    const pathLine = document.createElement("div");
    const method = event.request_method || "GET";
    const endpoint = event.request_path || event.request_uri || "/";
    pathLine.textContent = `${method} ${endpoint}`;
    endpointCell.append(pathLine);
    const flagBadges = buildFlagBadges(event.flags);
    if (flagBadges) {
      endpointCell.append(flagBadges);
    }
    if (event.user_agent) {
      const uaLine = document.createElement("div");
      uaLine.className = "muted user-agent";
      const userAgent = String(event.user_agent);
      const maxAgentLength = 120;
      uaLine.textContent =
        userAgent.length > maxAgentLength ? `${userAgent.slice(0, maxAgentLength - 1)}…` : userAgent;
      uaLine.setAttribute("title", userAgent);
      endpointCell.append(uaLine);
    }

    const statusCell = document.createElement("td");
    const statusLabel = event.status != null ? `${event.status}` : "-";
    statusCell.textContent = event.status_family
      ? `${statusLabel} (${event.status_family})`
      : statusLabel;

    const durationCell = document.createElement("td");
    durationCell.textContent = formatDuration(event.request_time_ms);

    row.append(timeCell, clientCell, scopeCell, apiKeyCell, endpointCell, statusCell, durationCell);
    monitoringTableBody.append(row);
  });
}

async function loadMonitoringData() {
  if (!monitoringActive) {
    return;
  }
  if (!monitoringViewActive) {
    return;
  }
  if (!apiKey) {
    monitoringStatus.textContent = "Set the dashboard API key to load monitoring data.";
    renderMonitoringSummary(null);
    renderMonitoringEvents({});
    return;
  }
  if (monitoringLoading) {
    return;
  }
  monitoringLoading = true;
  monitoringStatus.textContent = "Loading gateway insights…";
  try {
    const summaryPromise = authFetch(`/api/monitoring/summary?limit=${MONITORING_SUMMARY_LIMIT}`);
    const query = new URLSearchParams({ limit: String(MONITORING_EVENTS_LIMIT) });
    if (monitoringWindow && Number.isFinite(monitoringWindow)) {
      query.set("minutes", String(monitoringWindow));
    }
    const eventsPromise = authFetch(`/api/monitoring/events?${query.toString()}`);

    const [summaryResponse, eventsResponse] = await Promise.all([summaryPromise, eventsPromise]);

    if (!summaryResponse.ok || !eventsResponse.ok) {
      const status = summaryResponse.status || eventsResponse.status;
      if (status === 401 || status === 403) {
        throw new Error("Invalid or missing dashboard API key.");
      }
      const detail = !summaryResponse.ok
        ? await summaryResponse.text()
        : await eventsResponse.text();
      throw new Error(detail || `Monitoring HTTP ${status}`);
    }

    const summaryData = await summaryResponse.json();
    const eventsData = await eventsResponse.json();

    renderMonitoringSummary(summaryData);
    renderMonitoringEvents(eventsData);

    const parts = [];
    const filtersMeta = summaryData?.filters || eventsData?.filters || {};
    const ignoredClients =
      Array.isArray(filtersMeta.ignored_clients) && filtersMeta.ignored_clients.length > 0
        ? filtersMeta.ignored_clients
        : Array.isArray(summaryData?.ignored_clients) && summaryData.ignored_clients.length > 0
        ? summaryData.ignored_clients
        : Array.isArray(eventsData?.ignored_clients) && eventsData.ignored_clients.length > 0
        ? eventsData.ignored_clients
        : [];
    const filtersActive = Boolean(filtersMeta.active) || ignoredClients.length > 0;
    if (eventsData.window_minutes) {
      parts.push(`Window: last ${eventsData.window_minutes} min`);
    } else if (summaryData.time_window?.minutes) {
      parts.push(`Window: ${summaryData.time_window.minutes} min`);
    }
    if (eventsData.total && eventsData.total > eventsData.count) {
      parts.push(`Showing ${eventsData.count} of ${eventsData.total} events`);
    } else {
      parts.push(`Events: ${eventsData.count}`);
    }
    if (summaryData.totals?.requests != null) {
      const label = filtersActive ? "Requests counted (filtered)" : "Requests counted";
      parts.push(`${label}: ${formatNumber(summaryData.totals.requests)}`);
    }
    if (eventsData.ignored_request_count) {
      parts.push(`Ignored requests: ${formatNumber(eventsData.ignored_request_count)}`);
    }
    if (eventsData.truncated) {
      parts.push("Log truncated to recent entries");
    }
    if (ignoredClients.length > 0) {
      const displayList = ignoredClients.slice(0, 3).join(", ");
      const suffix = ignoredClients.length > 3 ? ", …" : "";
      parts.push(
        ignoredClients.length === 1
          ? `Ignoring client: ${displayList}${suffix}`
          : `Ignoring clients: ${displayList}${suffix}`
      );
    }
    monitoringStatus.textContent = parts.join(" · ");
  } catch (error) {
    monitoringStatus.textContent = `Monitoring unavailable: ${error.message || error}`;
    renderMonitoringSummary(null);
    renderMonitoringEvents({});
  } finally {
    monitoringLoading = false;
  }
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

viewButtons.forEach((button) => {
  button.addEventListener("click", () => {
    const view = button.dataset.viewButton;
    setActiveView(view || "services");
  });
});

setActiveView(activeView);

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

if (monitoringRefreshButton) {
  monitoringRefreshButton.addEventListener("click", () => {
    if (monitoringViewActive) {
      loadMonitoringData();
    }
  });
}

if (monitoringFilterInput) {
  monitoringFilterText = normalizeFilterValue(monitoringFilterInput.value);
  const handleMonitorFilterInput = (event) => {
    setMonitoringFilter(event.target.value);
  };
  monitoringFilterInput.addEventListener("input", handleMonitorFilterInput);
  monitoringFilterInput.addEventListener("search", handleMonitorFilterInput);
}

if (monitoringWindowSelect) {
  monitoringWindowSelect.addEventListener("change", () => {
    monitoringWindow = Number(monitoringWindowSelect.value) || 60;
    if (monitoringViewActive) {
      loadMonitoringData();
    }
  });
}

if (monitoringActive) {
  setInterval(() => {
    if (apiKey && monitoringViewActive) {
      loadMonitoringData();
    }
  }, 60000);
}

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
