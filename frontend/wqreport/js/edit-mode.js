const preferencesKey = "agender.reports.water-quality.preferences";
const storedPreferences = window.parent?.NotasWaterQualitySession?.initialPreferences
  || window.parent?.NotasStorage?.loadJson(preferencesKey, null)
  || {};
let editModeEnabled = Boolean(storedPreferences.editMode);
let editInheritanceEnabled = editModeEnabled && Boolean(storedPreferences.editInheritance);
let editModeGuardsInitialized = false;
let editInheritanceObserver = null;
let isSyncingInheritedEdits = false;

export function isEditModeEnabled() {
  return editModeEnabled;
}

export function isEditInheritanceEnabled() {
  return editInheritanceEnabled;
}

export function applyEditMode(enabled = isEditModeEnabled(), toggle = null) {
  initializeEditModeGuards();
  document.body.dataset.editMode = enabled ? "true" : "false";

  if (toggle) {
    toggle.checked = enabled;
  }

  document.querySelectorAll(".editable-text-target").forEach(element => {
    if (!element.dataset.defaultContenteditable) {
      element.dataset.defaultContenteditable = element.getAttribute("contenteditable") || "false";
    }

    element.setAttribute("spellcheck", "false");

    const canEdit = enabled || isOperationalValueCell(element) || isAlwaysEditableTarget(element);

    element.setAttribute(
      "contenteditable",
      canEdit ? element.dataset.defaultContenteditable : "false"
    );
    element.toggleAttribute("aria-readonly", !canEdit);
    element.classList.toggle("is-readonly", !canEdit);
  });

  if (!enabled) {
    releaseEditableFocus();
  }

  applyEditInheritance();

  document.dispatchEvent(new CustomEvent("wqreport:editmodechange", {
    detail: { enabled }
  }));
}

export function saveEditMode(enabled, toggle = null) {
  editModeEnabled = Boolean(enabled);
  if (!editModeEnabled) editInheritanceEnabled = false;
  applyEditMode(editModeEnabled, toggle);
}

export function applyEditInheritance(enabled = isEditInheritanceEnabled(), toggle = null) {
  const canUseInheritance = isEditModeEnabled();
  const resolvedEnabled = canUseInheritance && enabled;

  document.body.dataset.editInheritance = resolvedEnabled ? "true" : "false";

  if (toggle) {
    toggle.checked = resolvedEnabled;
    toggle.disabled = !canUseInheritance;
    toggle.closest(".settings-row-card")?.classList.toggle("is-disabled", !canUseInheritance);
  }

  stopEditInheritanceObserver();

  if (!resolvedEnabled) {
    document.dispatchEvent(new CustomEvent("wqreport:editinheritancechange", {
      detail: { enabled: resolvedEnabled }
    }));
    return;
  }

  syncAllInheritedEdits();
  startEditInheritanceObserver();

  document.dispatchEvent(new CustomEvent("wqreport:editinheritancechange", {
    detail: { enabled: resolvedEnabled }
  }));
}

export function saveEditInheritance(enabled, toggle = null) {
  editInheritanceEnabled = isEditModeEnabled() && Boolean(enabled);
  applyEditInheritance(editInheritanceEnabled, toggle);
}

export function canEditTextTarget(target) {
  return isEditModeEnabled() || isOperationalValueCell(target) || isAlwaysEditableTarget(target);
}

export function isAlwaysEditableTarget(element) {
  const editKey = element?.dataset?.editKey || "";

  return editKey === "observations-title" || editKey === "observations-text";
}

export function syncAllInheritedEdits() {
  const firstPage = getFirstReportPage();

  if (!firstPage) return;

  isSyncingInheritedEdits = true;

  getEditableTargets(firstPage).forEach(source => {
    syncInheritedEditableTarget(source);
  });

  isSyncingInheritedEdits = false;
}

function initializeEditModeGuards() {
  if (editModeGuardsInitialized) return;
  editModeGuardsInitialized = true;

  document.addEventListener("beforeinput", blockReadOnlyTextEdit, true);
  document.addEventListener("paste", blockReadOnlyTextEdit, true);
  document.addEventListener("drop", blockReadOnlyTextEdit, true);
  document.addEventListener("cut", blockReadOnlyTextEdit, true);
  document.addEventListener("keydown", blockReadOnlyTextKey, true);
}

function startEditInheritanceObserver() {
  const firstPage = getFirstReportPage();

  if (!firstPage || !window.MutationObserver) return;

  editInheritanceObserver = new MutationObserver(mutations => {
    if (isSyncingInheritedEdits || !isEditModeEnabled() || !isEditInheritanceEnabled()) {
      return;
    }

    const targets = new Set();

    mutations.forEach(mutation => {
      const target = getEditableTargetFromNode(mutation.target);

      if (target && firstPage.contains(target)) {
        targets.add(target);
      }
    });

    if (!targets.size) return;

    isSyncingInheritedEdits = true;
    targets.forEach(target => syncInheritedEditableTarget(target));
    isSyncingInheritedEdits = false;
  });

  editInheritanceObserver.observe(firstPage, {
    attributes: true,
    attributeFilter: ["style", "class"],
    childList: true,
    characterData: true,
    subtree: true
  });

  firstPage.addEventListener("input", handleInheritedEditInput, true);
}

function stopEditInheritanceObserver() {
  if (editInheritanceObserver) {
    editInheritanceObserver.disconnect();
    editInheritanceObserver = null;
  }

  getFirstReportPage()?.removeEventListener("input", handleInheritedEditInput, true);
}

function handleInheritedEditInput(event) {
  if (isSyncingInheritedEdits || !isEditModeEnabled() || !isEditInheritanceEnabled()) {
    return;
  }

  const target = event.target.closest?.(".editable-text-target");

  if (!target || !getFirstReportPage()?.contains(target)) {
    return;
  }

  isSyncingInheritedEdits = true;
  syncInheritedEditableTarget(target);
  isSyncingInheritedEdits = false;
}

function syncInheritedEditableTarget(source) {
  const sourcePage = source.closest(".report-page");

  if (!sourcePage || sourcePage !== getFirstReportPage()) return;

  const sourceKey = source.dataset.editKey || "";
  const targetIndex = sourceKey ? -1 : getEditableTargets(sourcePage).indexOf(source);

  getReportPages().slice(1).forEach(page => {
    const target = sourceKey
      ? page.querySelector(`.editable-text-target[data-edit-key="${cssEscape(sourceKey)}"]`)
      : getEditableTargets(page)[targetIndex];

    if (!target) return;

    copyInheritedEditableState(source, target);
  });
}

function copyInheritedEditableState(source, target) {
  target.setAttribute("style", source.getAttribute("style") || "");

  if (source.classList.contains("footer")) {
    return;
  }

  const rowControls = Array.from(target.querySelectorAll(".remove-parameter-row-button"));
  target.innerHTML = getInheritedHtml(source);
  rowControls.forEach(control => target.appendChild(control));
}

function getReportPages() {
  return Array.from(document.querySelectorAll(".report-page"));
}

function getFirstReportPage() {
  return getReportPages()[0] || null;
}

function getEditableTargets(page) {
  return Array.from(page.querySelectorAll(".editable-text-target"));
}

function getInheritedHtml(source) {
  const clone = source.cloneNode(true);
  clone.querySelectorAll(".remove-parameter-row-button").forEach(button => button.remove());

  return clone.innerHTML;
}

function cssEscape(value) {
  if (window.CSS && typeof window.CSS.escape === "function") {
    return window.CSS.escape(value);
  }

  return String(value).replace(/["\\]/g, "\\$&");
}

function blockReadOnlyTextEdit(event) {
  if (isEditModeEnabled()) return;

  const target = event.target.closest?.(".editable-text-target");

  if (!target) return;
  if (isOperationalValueCell(target) || isAlwaysEditableTarget(target)) return;

  event.preventDefault();
  event.stopImmediatePropagation();
  releaseEditableFocus();
}

function blockReadOnlyTextKey(event) {
  if (isEditModeEnabled()) return;

  const target = event.target.closest?.(".editable-text-target");

  if (!target) return;
  if (isOperationalValueCell(target) || isAlwaysEditableTarget(target)) return;

  const blockedKeys = [
    "Backspace",
    "Delete",
    "Enter",
    "Tab"
  ];
  const isTextShortcut = event.ctrlKey && ["b", "i", "u", "v", "x"].includes(event.key.toLowerCase());
  const isPrintableKey = event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey;

  if (!blockedKeys.includes(event.key) && !isTextShortcut && !isPrintableKey) {
    return;
  }

  event.preventDefault();
  event.stopImmediatePropagation();
  releaseEditableFocus();
}

function releaseEditableFocus() {
  const activeElement = document.activeElement;

  if (
    activeElement?.closest?.(".editable-text-target") &&
    !activeElement.closest?.(".parameter-value") &&
    !isAlwaysEditableTarget(activeElement.closest(".editable-text-target"))
  ) {
    activeElement.blur();
  }

  const selection = window.getSelection?.();

  if (selection && selection.rangeCount > 0) {
    const selectedEditable = getSelectionEditableTarget(selection);

    if (selectedEditable) {
      selection.removeAllRanges();
    }
  }
}

function getSelectionEditableTarget(selection) {
  const anchorTarget = getEditableTargetFromNode(selection.anchorNode);
  const focusTarget = getEditableTargetFromNode(selection.focusNode);

  return anchorTarget || focusTarget;
}

function getEditableTargetFromNode(node) {
  if (!node) return null;

  const element = node.nodeType === Node.ELEMENT_NODE ? node : node.parentElement;
  return element?.closest?.(".editable-text-target") || null;
}

function isOperationalValueCell(element) {
  return element?.classList?.contains("parameter-value");
}
