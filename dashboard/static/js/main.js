const forms = document.querySelectorAll(".try-form");
const copyButtons = document.querySelectorAll(".copy-button");

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

  renderPlaceholder(container, "Request in flight...");

  let response;
  try {
    const formData = new FormData(form);
    response = await fetch(endpoint, {
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

  if (serviceId === "lmstudio-chat" || serviceId === "openwebui-chat" || serviceId === "gateway-lmstudio-chat") {
    renderChat(container, data);
  } else if (serviceId === "lmstudio-models") {
    renderModels(container, data);
  } else if (serviceId === "kokoro-tts") {
    renderTts(container, data);
  } else {
    renderGeneric(container, data);
  }
}

forms.forEach((form) => form.addEventListener("submit", handleSubmit));

copyButtons.forEach((button) => {
  button.addEventListener("click", async () => {
    const text = button.dataset.copy.replace(/&#10;/g, "\n");
    try {
      await navigator.clipboard.writeText(text);
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
