const state = {
  items: [],
  filtered: [],
  sources: [],
  folder: "全部",
  query: "",
  sort: "modified",
  selectedPath: null,
  selectedItem: null,
  selectedPaths: new Set(),
  compareDetails: [],
  compareMode: false,
  libraryCollapsed: localStorage.getItem("h3-archive-library-collapsed") === "true",
  inspectorCollapsed: localStorage.getItem("h3-archive-inspector-collapsed") === "true",
  requestId: 0,
  theme: localStorage.getItem("h3-archive-theme") || "dark",
};

const elements = {};

document.addEventListener("DOMContentLoaded", () => {
  [
    "library-status", "sources-button", "theme-button", "refresh-button",
    "paired-count", "toggle-library-button", "search-input", "folder-filters", "sort-select",
    "visible-count", "compare-button", "selected-count", "video-list",
    "empty-state", "video-card-template", "stage-kicker", "current-title",
    "current-path", "exit-compare-button", "previous-button", "next-button",
    "single-view", "player-placeholder", "video-player", "current-badges",
    "media-facts", "copy-prompt-button", "compare-view", "compare-subtitle",
    "play-all-button", "pause-all-button", "compare-grid", "diff-count",
    "diff-table-wrap", "prompt-diff-content", "inspector-empty",
    "inspector-content", "metadata-status", "toggle-inspector-button", "summary-grid",
    "reference-section", "reference-content", "copy-prompt-detail-button",
    "prompt-content", "raw-content", "sources-dialog", "close-sources-button",
    "source-path-input", "source-label-input", "add-source-button",
    "source-count", "source-list", "done-sources-button", "toast",
  ].forEach((id) => {
    elements[toCamelCase(id)] = document.getElementById(id);
  });

  applyTheme();
  elements.refreshButton.addEventListener("click", () => loadLibrary(true));
  elements.sourcesButton.addEventListener("click", openSourcesDialog);
  elements.themeButton.addEventListener("click", toggleTheme);
  elements.toggleLibraryButton.addEventListener("click", () => togglePanel("library"));
  elements.toggleInspectorButton.addEventListener("click", () => togglePanel("inspector"));
  elements.searchInput.addEventListener("input", (event) => {
    state.query = event.target.value.trim().toLocaleLowerCase();
    applyFilters();
  });
  elements.sortSelect.addEventListener("change", (event) => {
    state.sort = event.target.value;
    applyFilters();
  });
  elements.compareButton.addEventListener("click", enterCompareMode);
  elements.exitCompareButton.addEventListener("click", exitCompareMode);
  elements.previousButton.addEventListener("click", () => moveSelection(-1));
  elements.nextButton.addEventListener("click", () => moveSelection(1));
  elements.copyPromptButton.addEventListener("click", copySelectedPrompt);
  elements.copyPromptDetailButton.addEventListener("click", copySelectedPrompt);
  elements.playAllButton.addEventListener("click", () => {
    elements.compareGrid.querySelectorAll("video").forEach((video) => video.play().catch(() => {}));
  });
  elements.pauseAllButton.addEventListener("click", () => {
    elements.compareGrid.querySelectorAll("video").forEach((video) => video.pause());
  });
  elements.addSourceButton.addEventListener("click", addSource);
  elements.videoPlayer.addEventListener("error", () => showToast("影片無法載入，請確認檔案仍在原位置。"));
  document.addEventListener("keydown", handleKeyboard);
  elements.sourcesDialog.addEventListener("close", () => {
    elements.sourcePathInput.value = "";
    elements.sourceLabelInput.value = "";
  });

  applyPanelLayout();
  loadLibrary(false);
});

function toCamelCase(value) {
  return value.replace(/-([a-z])/g, (_, letter) => letter.toUpperCase());
}

async function loadLibrary(preserveSelection) {
  setBusy(true);
  try {
    const response = await fetch("/api/library", { cache: "no-store" });
    if (!response.ok) throw new Error("library request failed");
    const payload = await response.json();
    state.items = Array.isArray(payload.items) ? payload.items : [];
    state.sources = Array.isArray(payload.sources) ? payload.sources : [];
    state.selectedPaths = new Set(
      Array.from(state.selectedPaths).filter((path) => state.items.some((item) => item.id === path)),
    );
    renderSources();
    renderFolderFilters();
    applyFilters();

    const selectedStillExists = preserveSelection
      && state.filtered.some((item) => item.id === state.selectedPath);
    if (selectedStillExists) {
      await selectItemById(state.selectedPath, false);
    } else if (state.filtered.length > 0) {
      await selectItemById(state.filtered[0].id, false);
    } else {
      clearSelection();
    }

    const ignored = payload.stats ? payload.stats.unpaired_videos : 0;
    elements.libraryStatus.textContent = state.items.length
      ? state.items.length + " 組配對" + (ignored ? " · " + ignored + " 支未納入" : "")
      : "尚未加入來源";
    elements.pairedCount.textContent = String(state.items.length).padStart(2, "0");
    elements.emptyState.querySelector("strong").textContent = state.sources.length
      ? "找不到配對影片"
      : "尚未加入影片資料夾";
    elements.emptyState.querySelector("p").textContent = state.sources.length
      ? "目前來源中沒有同檔名 MP4＋TXT 的配對。"
      : "請按右上角「資料夾來源」，加入包含同檔名 MP4＋TXT 的資料夾。";
  } catch (error) {
    elements.libraryStatus.textContent = "掃描失敗";
    showToast("無法取得影片清單，請確認伺服器仍在執行。");
    console.error(error);
  } finally {
    setBusy(false);
  }
}

function setBusy(isBusy) {
  elements.refreshButton.disabled = isBusy;
  elements.refreshButton.classList.toggle("is-loading", isBusy);
}

function renderSources() {
  elements.sourceList.replaceChildren();
  elements.sourceCount.textContent = state.sources.length + " 個來源";
  if (!state.sources.length) {
    const empty = document.createElement("p");
    empty.className = "source-empty";
    empty.textContent = "還沒有加入資料夾。";
    elements.sourceList.appendChild(empty);
    return;
  }

  state.sources.forEach((source) => {
    const row = document.createElement("div");
    row.className = "source-row";
    const copy = document.createElement("div");
    copy.className = "source-copy";
    const title = document.createElement("strong");
    title.textContent = source.label;
    const path = document.createElement("span");
    path.textContent = source.path;
    copy.append(title, path);
    const actions = document.createElement("div");
    actions.className = "source-actions";
    const status = document.createElement("span");
    status.className = "source-status " + (source.exists ? "is-ok" : "is-missing");
    status.textContent = source.exists ? "可讀取" : "不存在";
    actions.appendChild(status);
    if (source.persistent) {
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "button button-remove";
      remove.textContent = "移除";
      remove.addEventListener("click", () => removeSource(source.id));
      actions.appendChild(remove);
    } else {
      const temporary = document.createElement("span");
      temporary.className = "source-status";
      temporary.textContent = "本次測試";
      actions.appendChild(temporary);
    }
    row.append(copy, actions);
    elements.sourceList.appendChild(row);
  });
}

function openSourcesDialog() {
  renderSources();
  if (typeof elements.sourcesDialog.showModal === "function") elements.sourcesDialog.showModal();
  else elements.sourcesDialog.setAttribute("open", "");
}

async function addSource() {
  const path = elements.sourcePathInput.value.trim();
  const label = elements.sourceLabelInput.value.trim();
  if (!path) {
    showToast("請先輸入資料夾完整路徑。");
    elements.sourcePathInput.focus();
    return;
  }
  elements.addSourceButton.disabled = true;
  try {
    const response = await fetch("/api/sources", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path, label }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "add source failed");
    elements.sourcePathInput.value = "";
    elements.sourceLabelInput.value = "";
    showToast("資料夾已加入。");
    await loadLibrary(true);
    renderSources();
  } catch (error) {
    showToast(error.message || "加入資料夾失敗。");
  } finally {
    elements.addSourceButton.disabled = false;
  }
}

async function removeSource(id) {
  try {
    const response = await fetch("/api/sources?id=" + encodeURIComponent(id), { method: "DELETE" });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "remove source failed");
    showToast("資料夾來源已移除。");
    await loadLibrary(false);
  } catch (error) {
    showToast(error.message || "移除資料夾失敗。");
  }
}

function renderFolderFilters() {
  const counts = new Map();
  state.items.forEach((item) => counts.set(item.group, (counts.get(item.group) || 0) + 1));
  elements.folderFilters.replaceChildren();
  elements.folderFilters.appendChild(createFilterButton("全部", state.items.length));
  Array.from(counts.keys()).sort((a, b) => a.localeCompare(b, "zh-Hant")).forEach((folder) => {
    elements.folderFilters.appendChild(createFilterButton(folder, counts.get(folder)));
  });
  updateFolderFilterState();
}

function createFilterButton(folder, count) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "filter-chip";
  button.dataset.folder = folder;
  const label = document.createElement("span");
  label.textContent = folder;
  const number = document.createElement("b");
  number.textContent = count;
  button.append(label, number);
  button.addEventListener("click", () => {
    state.folder = folder;
    updateFolderFilterState();
    applyFilters();
  });
  return button;
}

function updateFolderFilterState() {
  elements.folderFilters.querySelectorAll(".filter-chip").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.folder === state.folder);
  });
}

function applyFilters() {
  const query = state.query;
  const filtered = state.items.filter((item) => {
    if (state.folder !== "全部" && item.group !== state.folder) return false;
    if (!query) return true;
    const metadata = item.metadata || {};
    const searchable = [
      item.filename, item.folder, metadata.kind, metadata.mode,
      metadata.seed, metadata.model, metadata.lora,
    ].filter((value) => value !== null && value !== undefined)
      .join(" ").toLocaleLowerCase();
    return searchable.includes(query);
  });

  filtered.sort(compareItems);
  state.filtered = filtered;
  renderVideoList();
  elements.visibleCount.textContent = filtered.length + " 支影片";
  updateSelectionControls();
  updateNavigationState();

  if (state.selectedPath && !filtered.some((item) => item.id === state.selectedPath)) {
    if (filtered.length) selectItemById(filtered[0].id, false);
    else clearSelection();
  }
}

function compareItems(a, b) {
  if (state.sort === "name") return a.filename.localeCompare(b.filename, "zh-Hant");
  if (state.sort === "resolution") return resolutionArea(b) - resolutionArea(a) || b.modified - a.modified;
  return b.modified - a.modified;
}

function resolutionArea(item) {
  const metadata = item.metadata || {};
  return (metadata.width || 0) * (metadata.height || 0);
}

function renderVideoList() {
  elements.videoList.replaceChildren();
  elements.emptyState.classList.toggle("hidden", state.filtered.length > 0);
  if (!state.filtered.length) return;

  const fragment = document.createDocumentFragment();
  state.filtered.forEach((item, index) => {
    const card = elements.videoCardTemplate.content.firstElementChild.cloneNode(true);
    const selectedForCompare = state.selectedPaths.has(item.id);
    card.classList.toggle("is-current", item.id === state.selectedPath);
    card.classList.toggle("is-selected-for-compare", selectedForCompare);
    const selectButton = card.querySelector(".select-toggle");
    selectButton.setAttribute("aria-pressed", String(selectedForCompare));
    selectButton.setAttribute("aria-label", selectedForCompare ? "取消選取 " + item.filename : "選取 " + item.filename);
    selectButton.addEventListener("click", (event) => {
      event.stopPropagation();
      toggleCompareSelection(item.id);
    });

    const mainButton = card.querySelector(".card-main");
    mainButton.setAttribute("aria-label", "播放 " + item.filename);
    mainButton.addEventListener("click", () => {
      if (state.compareMode) exitCompareMode();
      selectItemById(item.id, true);
    });
    card.querySelector(".card-title").textContent = item.filename;
    card.querySelector(".card-folder").textContent = item.folder;
    card.querySelector(".card-index").textContent = String(index + 1).padStart(2, "0");
    card.querySelector(".card-kind").textContent = item.metadata.kind || "Metadata";
    card.querySelector(".card-meta").textContent = [
      formatResolution(item.metadata.width, item.metadata.height),
      formatDuration(item.metadata.duration || item.media.duration),
      item.metadata.seed !== null && item.metadata.seed !== undefined ? "seed " + item.metadata.seed : "seed —",
    ].join("  ·  ");

    const thumb = card.querySelector(".card-thumb");
    thumb.src = item.video_url;
    thumb.addEventListener("loadeddata", () => {
      if (Number.isFinite(thumb.duration) && thumb.duration > 0) thumb.currentTime = Math.min(0.12, thumb.duration);
    }, { once: true });
    thumb.addEventListener("seeked", () => thumb.pause(), { once: true });
    fragment.appendChild(card);
  });
  elements.videoList.appendChild(fragment);
}

function toggleCompareSelection(id) {
  if (state.selectedPaths.has(id)) state.selectedPaths.delete(id);
  else state.selectedPaths.add(id);
  renderVideoList();
  updateSelectionControls();
}

function updateSelectionControls() {
  const count = state.selectedPaths.size;
  elements.selectedCount.textContent = count;
  elements.compareButton.disabled = count < 2;
  elements.compareButton.classList.toggle("is-ready", count >= 2);
}

async function selectItemById(id, shouldPlay) {
  const item = state.filtered.find((candidate) => candidate.id === id)
    || state.items.find((candidate) => candidate.id === id);
  if (!item) return;

  state.selectedPath = id;
  state.selectedItem = item;
  renderVideoList();
  updateNavigationState();
  updateStage(item);

  const requestId = ++state.requestId;
  try {
    const response = await fetch("/api/item?id=" + encodeURIComponent(id), { cache: "no-store" });
    if (!response.ok) throw new Error("item request failed");
    const detail = await response.json();
    if (requestId !== state.requestId) return;
    state.selectedItem = detail;
    updateStage(detail);
    renderInspector(detail);
  } catch (error) {
    showToast("無法讀取生成資訊。");
    console.error(error);
  }

  elements.videoPlayer.src = item.video_url;
  elements.videoPlayer.load();
  elements.videoPlayer.classList.remove("hidden");
  elements.playerPlaceholder.classList.add("hidden");
  if (shouldPlay) elements.videoPlayer.play().catch(() => {});
}

function updateStage(item) {
  if (state.compareMode) return;
  elements.currentTitle.textContent = item.filename;
  elements.currentPath.textContent = item.folder;
  elements.currentBadges.replaceChildren();
  appendBadge(elements.currentBadges, item.metadata.kind || "Metadata", "accent");
  appendBadge(elements.currentBadges, item.metadata.status === "complete" ? "TXT 完整" : "TXT 部分欄位", item.metadata.status === "complete" ? "good" : "warn");
  if (item.metadata.mode) appendBadge(elements.currentBadges, item.metadata.mode, "neutral");
  elements.mediaFacts.textContent = [
    formatResolution(item.metadata.width || item.media.width, item.metadata.height || item.media.height),
    formatDuration(item.metadata.duration || item.media.duration),
    formatFps(item.metadata.fps || item.media.fps),
  ].join("  ·  ");
}

function renderInspector(item) {
  elements.inspectorEmpty.classList.add("hidden");
  elements.inspectorContent.classList.remove("hidden");
  const metadata = item.metadata || {};
  elements.metadataStatus.textContent = metadata.status === "complete" ? "完整記錄" : "部分記錄";
  elements.metadataStatus.className = "status-badge " + (metadata.status === "complete" ? "status-good" : "status-warn");

  const fields = [
    ["類型", metadata.kind || "—"],
    ["模式", metadata.mode || "—"],
    ["Seed", metadata.seed ?? "—"],
    ["輸出尺寸", formatResolution(metadata.width, metadata.height)],
    ["片長", formatDuration(metadata.duration || item.media.duration)],
    ["FPS", formatFps(metadata.fps || item.media.fps)],
    ["模型", metadata.model || "—"],
    ["LoRA", metadata.lora || "—"],
  ];
  if (metadata.kind === "VOSR2") {
    fields.push(["來源", metadata.source_file || "—"]);
    fields.push(["來源尺寸", formatResolution(metadata.source_width, metadata.source_height)]);
    fields.push(["目標尺寸", formatResolution(metadata.target_width, metadata.target_height)]);
    fields.push(["Fit side", metadata.fit_side || "—"]);
  }

  elements.summaryGrid.replaceChildren();
  fields.forEach(([label, value]) => {
    const wrapper = document.createElement("div");
    wrapper.className = "summary-item";
    const labelElement = document.createElement("dt");
    labelElement.textContent = label;
    const valueElement = document.createElement("dd");
    valueElement.textContent = value;
    valueElement.title = String(value);
    if (["模型", "LoRA", "來源"].includes(label)) wrapper.classList.add("summary-item-wide");
    wrapper.append(labelElement, valueElement);
    elements.summaryGrid.appendChild(wrapper);
  });

  elements.referenceContent.replaceChildren();
  if (item.reference_mapping && item.reference_mapping.length) {
    item.reference_mapping.forEach((mapping) => {
      const line = document.createElement("div");
      line.className = "mapping-line";
      line.textContent = mapping;
      elements.referenceContent.appendChild(line);
    });
  } else {
    const empty = document.createElement("p");
    empty.className = "muted-text";
    empty.textContent = "此生成記錄沒有參考媒體映射。";
    elements.referenceContent.appendChild(empty);
  }
  elements.promptContent.textContent = item.prompt || "此 TXT 沒有 PROMPT BEGIN 區段。";
  elements.rawContent.textContent = item.raw_text || "沒有原始 TXT 內容。";
  elements.copyPromptButton.disabled = !item.prompt;
  elements.copyPromptDetailButton.disabled = !item.prompt;
}

function togglePanel(panel) {
  if (panel === "library") {
    state.libraryCollapsed = !state.libraryCollapsed;
    localStorage.setItem("h3-archive-library-collapsed", String(state.libraryCollapsed));
  } else {
    state.inspectorCollapsed = !state.inspectorCollapsed;
    localStorage.setItem("h3-archive-inspector-collapsed", String(state.inspectorCollapsed));
  }
  applyPanelLayout();
}

function applyPanelLayout() {
  const workspace = document.querySelector(".workspace");
  workspace.classList.toggle("library-collapsed", state.libraryCollapsed);
  workspace.classList.toggle("inspector-collapsed", state.inspectorCollapsed);

  elements.toggleLibraryButton.textContent = state.libraryCollapsed ? "›" : "‹";
  elements.toggleLibraryButton.setAttribute("aria-label", state.libraryCollapsed ? "展開影片清單" : "收合影片清單");
  elements.toggleLibraryButton.title = state.libraryCollapsed ? "展開影片清單" : "收合影片清單";
  elements.toggleInspectorButton.textContent = state.inspectorCollapsed ? "‹" : "›";
  elements.toggleInspectorButton.setAttribute("aria-label", state.inspectorCollapsed ? "展開生成資訊" : "收合生成資訊");
  elements.toggleInspectorButton.title = state.inspectorCollapsed ? "展開生成資訊" : "收合生成資訊";
}

function clearSelection() {
  state.selectedPath = null;
  state.selectedItem = null;
  renderVideoList();
  updateNavigationState();
  elements.currentTitle.textContent = "尚未選取影片";
  elements.currentPath.textContent = "從左側選擇一支影片開始";
  elements.videoPlayer.pause();
  elements.videoPlayer.removeAttribute("src");
  elements.videoPlayer.load();
  elements.videoPlayer.classList.add("hidden");
  elements.playerPlaceholder.classList.remove("hidden");
  elements.currentBadges.replaceChildren();
  elements.mediaFacts.replaceChildren();
  elements.copyPromptButton.disabled = true;
  elements.inspectorEmpty.classList.remove("hidden");
  elements.inspectorContent.classList.add("hidden");
}

function moveSelection(direction) {
  if (!state.filtered.length || state.compareMode) return;
  const currentIndex = Math.max(0, state.filtered.findIndex((item) => item.id === state.selectedPath));
  const nextIndex = (currentIndex + direction + state.filtered.length) % state.filtered.length;
  selectItemById(state.filtered[nextIndex].id, true);
}

function updateNavigationState() {
  const hasItems = state.filtered.length > 0;
  elements.previousButton.disabled = !hasItems || state.compareMode;
  elements.nextButton.disabled = !hasItems || state.compareMode;
}

async function copySelectedPrompt() {
  const prompt = state.selectedItem && state.selectedItem.prompt;
  if (!prompt) {
    showToast("目前影片沒有可複製的提示詞。");
    return;
  }
  await copyText(prompt);
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
  } catch (error) {
    const textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand("copy");
    textarea.remove();
  }
  showToast("提示詞已複製到剪貼簿。");
}

async function enterCompareMode() {
  if (state.selectedPaths.size < 2) return;
  state.compareMode = true;
  elements.singleView.classList.add("hidden");
  elements.compareView.classList.remove("hidden");
  elements.exitCompareButton.classList.remove("hidden");
  elements.previousButton.classList.add("hidden");
  elements.nextButton.classList.add("hidden");
  elements.stageKicker.textContent = "COMPARE MODE";
  elements.currentTitle.textContent = "多部影片比較";
  elements.currentPath.textContent = state.selectedPaths.size + " 部影片 · 可同時播放或個別控制";
  await loadCompareDetails();
}

function exitCompareMode() {
  state.compareMode = false;
  state.compareDetails = [];
  elements.singleView.classList.remove("hidden");
  elements.compareView.classList.add("hidden");
  elements.exitCompareButton.classList.add("hidden");
  elements.previousButton.classList.remove("hidden");
  elements.nextButton.classList.remove("hidden");
  elements.stageKicker.textContent = "NOW VIEWING";
  updateNavigationState();
  if (state.selectedItem) updateStage(state.selectedItem);
}

async function loadCompareDetails() {
  elements.compareGrid.innerHTML = "<div class=\"compare-loading\">正在載入 TXT 差異…</div>";
  const ids = Array.from(state.selectedPaths);
  try {
    const details = await Promise.all(ids.map(async (id) => {
      const response = await fetch("/api/item?id=" + encodeURIComponent(id), { cache: "no-store" });
      if (!response.ok) throw new Error("compare item request failed");
      return response.json();
    }));
    state.compareDetails = details;
    elements.compareSubtitle.textContent = details.length + " 支影片";
    renderCompareGrid(details);
    renderDifferences(details);
  } catch (error) {
    elements.compareGrid.textContent = "比較資料載入失敗。";
    showToast("無法載入比較資料。");
    console.error(error);
  }
}

function renderCompareGrid(details) {
  elements.compareGrid.replaceChildren();
  details.forEach((item, index) => {
    const cell = document.createElement("article");
    cell.className = "compare-cell";
    const header = document.createElement("div");
    header.className = "compare-cell-header";
    const title = document.createElement("strong");
    title.textContent = item.filename;
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "compare-remove";
    remove.textContent = "×";
    remove.title = "取消比較此影片";
    remove.addEventListener("click", () => {
      state.selectedPaths.delete(item.id);
      if (state.selectedPaths.size < 2) exitCompareMode();
      else loadCompareDetails();
      renderVideoList();
      updateSelectionControls();
    });
    header.append(title, remove);

    const video = document.createElement("video");
    video.className = "compare-video";
    video.src = item.video_url;
    video.controls = true;
    video.playsInline = true;
    video.preload = "metadata";
    const facts = document.createElement("div");
    facts.className = "compare-facts";
    facts.textContent = [
      item.folder,
      formatResolution(item.metadata.width, item.metadata.height),
      formatDuration(item.metadata.duration || item.media.duration),
      "seed " + (item.metadata.seed ?? "—"),
    ].join("  ·  ");

    const promptDetails = document.createElement("details");
    promptDetails.className = "compare-prompt";
    const summary = document.createElement("summary");
    summary.textContent = "查看／複製提示詞";
    const promptActions = document.createElement("div");
    promptActions.className = "compare-prompt-actions";
    const copy = document.createElement("button");
    copy.type = "button";
    copy.className = "button button-copy";
    copy.textContent = "複製";
    copy.disabled = !item.prompt;
    copy.addEventListener("click", () => copyText(item.prompt || ""));
    promptActions.appendChild(copy);
    const prompt = document.createElement("pre");
    prompt.className = "compare-prompt-text";
    prompt.textContent = item.prompt || "沒有提示詞區段。";
    promptDetails.append(summary, promptActions, prompt);
    cell.append(header, video, facts, promptDetails);
    elements.compareGrid.appendChild(cell);
  });
}

function renderDifferences(details) {
  const fields = Array.from(new Set(
    details.flatMap((item) => Object.keys(item.metadata_fields || {})),
  )).sort((a, b) => a.localeCompare(b));
  const differingFields = fields.filter((field) => {
    const values = details.map((item) => item.metadata_fields?.[field] ?? "—");
    return new Set(values).size > 1;
  });

  elements.diffCount.textContent = differingFields.length + " 個欄位";
  elements.diffTableWrap.replaceChildren();
  if (!differingFields.length) {
    const empty = document.createElement("p");
    empty.className = "diff-empty";
    empty.textContent = "已選影片的結構化 TXT 欄位完全一致。";
    elements.diffTableWrap.appendChild(empty);
  } else {
    const table = document.createElement("table");
    table.className = "diff-table";
    const head = document.createElement("thead");
    const headRow = document.createElement("tr");
    const fieldHead = document.createElement("th");
    fieldHead.textContent = "欄位";
    headRow.appendChild(fieldHead);
    details.forEach((item) => {
      const th = document.createElement("th");
      th.textContent = item.filename;
      headRow.appendChild(th);
    });
    head.appendChild(headRow);
    const body = document.createElement("tbody");
    differingFields.forEach((field) => {
      const row = document.createElement("tr");
      const name = document.createElement("th");
      name.textContent = field;
      row.appendChild(name);
      const values = details.map((item) => item.metadata_fields?.[field] ?? "—");
      values.forEach((value) => {
        const cell = document.createElement("td");
        cell.textContent = value;
        cell.className = values.some((other) => other !== value) ? "is-different" : "";
        row.appendChild(cell);
      });
      body.appendChild(row);
    });
    table.append(head, body);
    elements.diffTableWrap.appendChild(table);
  }

  elements.promptDiffContent.replaceChildren();
  const lineSources = new Map();
  details.forEach((item) => {
    const lines = new Set((item.prompt || "").split(/\r?\n/).map((line) => line.trim()).filter(Boolean));
    lines.forEach((line) => {
      if (!lineSources.has(line)) lineSources.set(line, []);
      lineSources.get(line).push(item.filename);
    });
  });
  const uniqueLines = Array.from(lineSources.entries()).filter(([, sources]) => sources.length < details.length);
  if (!uniqueLines.length) {
    const same = document.createElement("p");
    same.className = "diff-empty";
    same.textContent = "提示詞內容沒有影片獨有的行。";
    elements.promptDiffContent.appendChild(same);
  } else {
    uniqueLines.forEach(([line, sources]) => {
      const row = document.createElement("div");
      row.className = "prompt-diff-line";
      const owner = document.createElement("span");
      owner.className = "prompt-diff-owner";
      owner.textContent = sources.length === 1 ? sources[0] : sources.length + " 部影片";
      const content = document.createElement("code");
      content.textContent = line;
      row.append(owner, content);
      elements.promptDiffContent.appendChild(row);
    });
  }
}

function handleKeyboard(event) {
  const target = event.target;
  const isTyping = target.matches("input, textarea, select") || target.isContentEditable;
  if (isTyping && event.key !== "Escape") return;
  if (event.key === " ") {
    event.preventDefault();
    if (elements.videoPlayer.classList.contains("hidden")) return;
    if (elements.videoPlayer.paused) elements.videoPlayer.play().catch(() => {});
    else elements.videoPlayer.pause();
  } else if (event.key === "ArrowLeft" || event.key.toLowerCase() === "p") {
    event.preventDefault();
    moveSelection(-1);
  } else if (event.key === "ArrowRight" || event.key.toLowerCase() === "n") {
    event.preventDefault();
    moveSelection(1);
  } else if (event.key === "/") {
    event.preventDefault();
    elements.searchInput.focus();
  } else if (event.key === "Escape") {
    elements.searchInput.blur();
  }
}

function applyTheme() {
  document.documentElement.dataset.theme = state.theme;
  elements.themeButton.textContent = state.theme === "dark" ? "☀" : "☾";
  elements.themeButton.title = state.theme === "dark" ? "切換淺色模式" : "切換深色模式";
}

function toggleTheme() {
  state.theme = state.theme === "dark" ? "light" : "dark";
  localStorage.setItem("h3-archive-theme", state.theme);
  applyTheme();
}

function appendBadge(parent, text, tone) {
  const badge = document.createElement("span");
  badge.className = "badge badge-" + tone;
  badge.textContent = text;
  parent.appendChild(badge);
}

function formatResolution(width, height) {
  if (!width || !height) return "尺寸 —";
  return width + " × " + height;
}

function formatDuration(seconds) {
  if (!Number.isFinite(Number(seconds))) return "片長 —";
  const value = Number(seconds);
  const minutes = Math.floor(value / 60);
  const remainder = (value % 60).toFixed(2).padStart(5, "0");
  return (minutes ? minutes + ":" : "0:") + remainder;
}

function formatFps(fps) {
  if (!Number.isFinite(Number(fps))) return "FPS —";
  return "FPS " + Number(fps).toFixed(2).replace(/\\.00$/, "");
}

function showToast(message) {
  elements.toast.textContent = message;
  elements.toast.classList.add("is-visible");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => elements.toast.classList.remove("is-visible"), 3200);
}
