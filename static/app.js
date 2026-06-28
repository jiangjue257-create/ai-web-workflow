const state = {
  mode: "image",
  polling: new Set(),
};

const IMAGE_MODELS = {
  text: [
    ["nano_banana_2-1K-square", "nano_banana_2-1K-square"],
    ["nano_banana_pro-1K-square", "nano_banana_pro-1K-square"],
    ["gpt-image-2", "gpt-image-2"],
    ["auto-image", "auto-image"],
  ],
  image: [
    ["auto-image", "auto-image"],
    ["gpt-image-2", "gpt-image-2"],
    ["nano_banana_2-1K-portrait", "nano_banana_2-1K-portrait"],
    ["nano_banana_pro-1K-portrait", "nano_banana_pro-1K-portrait"],
  ],
};

const VIDEO_MODELS = {
  text: [
    ["grok-imagine-1.0-video", "grok-imagine-1.0-video"],
    ["veo_3_1-fast-landscape", "veo_3_1-fast-landscape"],
  ],
  image: [["grok-imagine-video-1.5-preview", "grok-imagine-video-1.5-preview"]],
};

const $ = (id) => document.getElementById(id);

document.addEventListener("DOMContentLoaded", () => {
  setupModes();
  setupSettings();
  setupGenerationOptions();
  $("generateBtn").addEventListener("click", startGeneration);
  loadConfig();
});

function setupModes() {
  document.querySelectorAll(".mode").forEach((button) => {
    button.addEventListener("click", () => {
      state.mode = button.dataset.mode;
      document.querySelectorAll(".mode").forEach((item) => {
        item.classList.toggle("is-active", item === button);
        item.setAttribute("aria-selected", item === button ? "true" : "false");
      });
      $("imageOptions").classList.toggle("hidden", state.mode !== "image");
      $("videoOptions").classList.toggle("hidden", state.mode !== "video");
      setHint("");
    });
  });
}

function setupGenerationOptions() {
  $("imageMode").addEventListener("change", syncImageMode);
  $("videoMode").addEventListener("change", syncVideoMode);
  syncImageMode();
  syncVideoMode();
}

function syncImageMode() {
  const mode = $("imageMode").value;
  fillSelect($("imageModel"), IMAGE_MODELS[mode]);
  $("imageReferenceField").classList.toggle("hidden", mode !== "image");
  $("imageCount").value = "1";
}

function syncVideoMode() {
  const mode = $("videoMode").value;
  fillSelect($("videoModel"), VIDEO_MODELS[mode]);
  $("videoReferenceField").classList.toggle("hidden", mode !== "image");
}

function fillSelect(select, options) {
  const current = select.value;
  select.innerHTML = "";
  options.forEach(([value, label]) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = label;
    select.append(option);
  });
  if (options.some(([value]) => value === current)) {
    select.value = current;
  }
}

function setupSettings() {
  $("settingsToggle").addEventListener("click", () => $("settingsDialog").showModal());
  $("saveConfigBtn").addEventListener("click", saveConfig);
}

async function loadConfig() {
  try {
    const config = await fetchJson("/api/config");
    renderConfig(config);
  } catch (error) {
    $("keyState").textContent = "设置读取失败";
    $("configHint").textContent = error.message;
  }
}

async function saveConfig() {
  $("saveConfigBtn").disabled = true;
  try {
    const config = await fetchJson("/api/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        api_base_url: $("apiBaseUrl").value.trim() || "https://api.x.ai",
        api_key: $("apiKey").value.trim(),
        output_dir: $("outputDir").value.trim() || "outputs",
      }),
    });
    $("apiKey").value = "";
    renderConfig(config);
  } catch (error) {
    $("configHint").textContent = error.message;
  } finally {
    $("saveConfigBtn").disabled = false;
  }
}

function renderConfig(config) {
  $("apiBaseUrl").value = config.api_base_url || "https://api.x.ai";
  $("outputDir").value = config.output_dir || "outputs";
  if (config.api_key_set) {
    $("keyState").textContent = `API key 已保存：${config.api_key_preview}`;
    $("keyState").classList.add("is-ready");
    $("configHint").textContent = `已保存 API key：${config.api_key_preview}`;
  } else {
    $("keyState").textContent = "还没有保存 API key";
    $("keyState").classList.remove("is-ready");
    $("configHint").textContent = "请先保存 API key，再开始生成。";
  }
}

async function startGeneration() {
  const prompt = $("prompt").value.trim();
  if (!prompt) {
    setHint("请先填写 Prompt。");
    $("prompt").focus();
    return;
  }

  $("generateBtn").disabled = true;
  setHint("正在创建任务...");
  try {
    const result = state.mode === "image" ? await startImage(prompt) : await startVideo(prompt);
    addTaskCard(result.task_id, state.mode, prompt);
    setHint("任务已创建，可以继续提交新的任务。");
    pollTask(result.task_id);
  } catch (error) {
    setHint(error.message);
  } finally {
    $("generateBtn").disabled = false;
  }
}

async function startImage(prompt) {
  const imageMode = $("imageMode").value;
  const body = new FormData();
  body.set("prompt", prompt);
  body.set("mode", imageMode);
  body.set("model", $("imageModel").value);
  body.set("aspect_ratio", $("imageAspect").value);
  body.set("count", $("imageCount").value);

  const file = $("imageReference").files[0];
  if (imageMode === "image") {
    if (!file) {
      throw new Error("图生图需要先选择一张参考图。");
    }
    body.set("reference_image", file);
  }

  return fetchJson("/api/generate/image", {
    method: "POST",
    body,
  });
}

async function startVideo(prompt) {
  const videoMode = $("videoMode").value;
  const body = new FormData();
  body.set("prompt", prompt);
  body.set("mode", videoMode);
  body.set("model", $("videoModel").value);
  body.set("aspect_ratio", $("videoAspect").value);
  body.set("duration", $("duration").value);
  body.set("resolution", $("resolution").value);

  const file = $("referenceImage").files[0];
  if (videoMode === "image") {
    if (!file) {
      throw new Error("图生视频需要先选择一张参考图。");
    }
    body.set("reference_image", file);
  }

  return fetchJson("/api/generate/video", {
    method: "POST",
    body,
  });
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || `请求失败：HTTP ${response.status}`);
  }
  return data;
}

function addTaskCard(taskId, kind, prompt) {
  const list = $("taskList");
  const empty = list.querySelector(".empty-state");
  if (empty) empty.remove();

  const card = document.createElement("article");
  card.className = "task-card";
  card.id = `task-${taskId}`;
  card.innerHTML = `
    <div class="task-header">
      <div>
        <div class="task-title">${kind === "image" ? "图片任务" : "视频任务"}</div>
        <p class="task-prompt">${escapeHtml(prompt)}</p>
      </div>
      <span class="task-status" data-role="status">pending</span>
    </div>
    <p class="task-message" data-role="message">等待开始</p>
    <div class="task-result" data-role="result"></div>
  `;
  list.prepend(card);
}

async function pollTask(taskId) {
  if (state.polling.has(taskId)) return;
  state.polling.add(taskId);

  try {
    while (state.polling.has(taskId)) {
      const task = await fetchJson(`/api/tasks/${taskId}`);
      renderTask(task);
      if (task.status === "completed" || task.status === "failed") {
        state.polling.delete(taskId);
        break;
      }
      await wait(1500);
    }
  } catch (error) {
    const card = $(`task-${taskId}`);
    if (card) {
      card.classList.add("failed");
      card.querySelector('[data-role="message"]').textContent = error.message;
    }
    state.polling.delete(taskId);
  }
}

function renderTask(task) {
  const card = $(`task-${task.id}`);
  if (!card) return;

  card.classList.toggle("completed", task.status === "completed");
  card.classList.toggle("failed", task.status === "failed");
  card.querySelector('[data-role="status"]').textContent = task.status;
  card.querySelector('[data-role="message"]').textContent = task.message || "状态已更新";

  const result = card.querySelector('[data-role="result"]');
  if (task.status === "failed") {
    result.innerHTML = `<p class="task-error">${escapeHtml(task.error || "任务失败，但没有返回具体原因。")}</p>`;
    return;
  }

  if (task.status !== "completed" || !task.file_url) {
    result.innerHTML = "";
    return;
  }

  const safeUrl = encodeURI(task.file_url);
  if (task.kind === "video") {
    result.innerHTML = `
      <video class="preview" controls src="${safeUrl}"></video>
      <p><a class="result-link" href="${safeUrl}" target="_blank" rel="noreferrer">打开视频文件</a></p>
    `;
  } else {
    result.innerHTML = `
      <img class="preview" src="${safeUrl}" alt="生成图片" />
      <p><a class="result-link" href="${safeUrl}" target="_blank" rel="noreferrer">打开图片文件</a></p>
    `;
  }
}

function setHint(message) {
  $("formHint").textContent = message;
}

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;",
  })[char]);
}
