import { canEditTextTarget, isEditModeEnabled } from "./edit-mode.js";

let savedRange = null;
let currentEditableElement = null;

export function initializeFormatMenu() {
  const menu = document.getElementById("contextFormatMenu");
  const fontFamilySelect = document.getElementById("fontFamilySelect");
  const fontSizeInput = document.getElementById("fontSizeInput");
  const fontSizeToggle = document.getElementById("fontSizeToggle");
  const fontSizeDropdown = document.getElementById("fontSizeDropdown");
  const fontSizeOptions = Array.from(document.querySelectorAll("#fontSizeDropdown button[data-size]"));
  const boldBtn = document.getElementById("boldBtn");
  const italicBtn = document.getElementById("italicBtn");
  const underlineBtn = document.getElementById("underlineBtn");
  const alignButtons = Array.from(document.querySelectorAll(".align-button"));

  menu.addEventListener("mousedown", function(event) {
    if (event.target.closest("select, input")) {
      event.stopPropagation();
      return;
    }

    event.preventDefault();
    event.stopPropagation();
  });

  menu.addEventListener("click", function(event) {
    event.stopPropagation();
  });

  document.addEventListener("contextmenu", function(event) {
    const target = event.target.closest(".editable-text-target");

    if (!target || !canEditTextTarget(target)) {
      hideFormatMenu();
      currentEditableElement = null;
      savedRange = null;
      return;
    }

    event.preventDefault();
    currentEditableElement = target;

    const selection = window.getSelection();

    if (
      selection.rangeCount > 0 &&
      !selection.isCollapsed &&
      target.contains(selection.anchorNode) &&
      target.contains(selection.focusNode)
    ) {
      savedRange = selection.getRangeAt(0).cloneRange();
    } else {
      savedRange = null;
    }

    updateFontFamilySelectValue(fontFamilySelect, getCurrentFontFamily(target));
    updateFontSizeInputLabel(fontSizeInput, getCurrentFontSize(target));
    updateFormatToggleButtons(target, boldBtn, italicBtn, underlineBtn);
    updateAlignmentButtons(alignButtons, getCurrentTextAlign(target));
    closeFontSizeDropdown(fontSizeDropdown, fontSizeToggle);

    menu.style.left = `${event.clientX}px`;
    menu.style.top = `${event.clientY}px`;
    menu.style.display = "flex";
  });

  document.addEventListener("click", function(event) {
    if (!event.target.closest("#contextFormatMenu")) {
      hideFormatMenu();
      closeFontSizeDropdown(fontSizeDropdown, fontSizeToggle);
    }
  });

  document.addEventListener("wqreport:editmodechange", event => {
    if (event.detail?.enabled) return;

    hideFormatMenu();
    closeFontSizeDropdown(fontSizeDropdown, fontSizeToggle);
    currentEditableElement = null;
    savedRange = null;
  });

  fontFamilySelect.addEventListener("change", function() {
    if (!this.value) return;
    applyTextStyle({ fontFamily: this.value });
  });

  fontSizeInput.addEventListener("change", function() {
    applyFontSizeFromInput(this);
    closeFontSizeDropdown(fontSizeDropdown, fontSizeToggle);
  });

  fontSizeInput.addEventListener("keydown", function(event) {
    if (event.key !== "Enter") return;

    event.preventDefault();
    applyFontSizeFromInput(this);
    closeFontSizeDropdown(fontSizeDropdown, fontSizeToggle);
  });

  fontSizeToggle.addEventListener("click", event => {
    event.stopPropagation();
    toggleFontSizeDropdown(fontSizeDropdown, fontSizeToggle);
  });

  fontSizeOptions.forEach(option => {
    option.addEventListener("click", () => {
      fontSizeInput.value = option.dataset.size;
      applyFontSizeFromInput(fontSizeInput);
      closeFontSizeDropdown(fontSizeDropdown, fontSizeToggle);
    });
  });

  boldBtn.addEventListener("click", () => {
    applyBoldToSelection();
    updateFormatToggleButtons(currentEditableElement, boldBtn, italicBtn, underlineBtn);
  });
  italicBtn.addEventListener("click", () => {
    applyItalicToSelection();
    updateFormatToggleButtons(currentEditableElement, boldBtn, italicBtn, underlineBtn);
  });
  underlineBtn.addEventListener("click", () => {
    applyUnderlineToSelection();
    updateFormatToggleButtons(currentEditableElement, boldBtn, italicBtn, underlineBtn);
  });

  alignButtons.forEach(button => {
    button.addEventListener("click", () => {
      applyTextAlignment(button.dataset.align);
      updateAlignmentButtons(alignButtons, button.dataset.align);
    });
  });
}

function hideFormatMenu() {
  const menu = document.getElementById("contextFormatMenu");

  if (menu) {
    menu.style.display = "none";
  }
}

function restoreSelection() {
  if (!savedRange) return false;

  const selection = window.getSelection();
  selection.removeAllRanges();
  selection.addRange(savedRange);

  return true;
}

function toggleFontSizeDropdown(dropdown, toggleButton) {
  if (!dropdown || !toggleButton) return;

  const willOpen = dropdown.hidden;
  dropdown.hidden = !willOpen;
  toggleButton.setAttribute("aria-expanded", String(willOpen));
}

function closeFontSizeDropdown(dropdown, toggleButton) {
  if (dropdown) {
    dropdown.hidden = true;
  }

  if (toggleButton) {
    toggleButton.setAttribute("aria-expanded", "false");
  }
}

function applyFontSizeFromInput(input) {
  const size = Number(input.value);

  if (!Number.isFinite(size) || size <= 0) return;

  const normalizedSize = Math.max(6, Math.min(120, Math.round(size)));
  input.value = String(normalizedSize);
  applyTextStyle({ fontSize: `${normalizedSize}px` });
}

function applyTextStyle(styles) {
  if (!currentEditableElement || !canEditTextTarget(currentEditableElement)) return;

  const restored = restoreSelection();

  const selection = window.getSelection();

  if (!restored || !selection.rangeCount || selection.isCollapsed) {
    Object.assign(currentEditableElement.style, styles);
    return;
  }

  const range = selection.getRangeAt(0);

  if (!currentEditableElement.contains(range.commonAncestorContainer)) return;

  removeStylesFromSelection(Object.keys(styles), false);
  restoreSelection();

  const refreshedSelection = window.getSelection();

  if (!refreshedSelection.rangeCount || refreshedSelection.isCollapsed) return;

  wrapSelectionWithStyles(refreshedSelection.getRangeAt(0), refreshedSelection, styles);
}

function applyBoldToSelection() {
  const isBold = currentEditableElement ? getCurrentTextFormat(currentEditableElement).bold : false;

  if (isBold) {
    removeStylesFromSelection(["fontWeight"]);
    applyTextStyle({ fontWeight: "400" });
    return;
  }

  applyTextStyle({ fontWeight: "900" });
}

function applyItalicToSelection() {
  const isItalic = currentEditableElement ? getCurrentTextFormat(currentEditableElement).italic : false;

  if (isItalic) {
    removeStylesFromSelection(["fontStyle"]);
    applyTextStyle({ fontStyle: "normal" });
    return;
  }

  applyTextStyle({ fontStyle: "italic" });
}

function applyUnderlineToSelection() {
  const isUnderline = currentEditableElement ? getCurrentTextFormat(currentEditableElement).underline : false;

  if (isUnderline && removeStylesFromSelection(["textDecoration", "textDecorationLine"])) {
    return;
  }

  applyTextStyle({ textDecoration: "underline" });
}

function wrapSelectionWithStyles(range, selection, styles) {
  const span = document.createElement("span");

  Object.keys(styles).forEach(key => {
    span.style[key] = styles[key];
  });

  try {
    const contents = range.extractContents();
    span.appendChild(contents);
    range.insertNode(span);

    selection.removeAllRanges();

    const newRange = document.createRange();
    newRange.selectNodeContents(span);
    selection.addRange(newRange);

    savedRange = newRange.cloneRange();
  } catch (error) {
    console.error("No se pudo aplicar el formato al texto seleccionado:", error);
  }
}

function applyTextAlignment(alignment) {
  if (!currentEditableElement || !canEditTextTarget(currentEditableElement)) return;
  if (!["left", "center", "right", "justify"].includes(alignment)) return;

  currentEditableElement.style.textAlign = alignment;
}

function removeStylesFromSelection(styleNames, fallbackToCurrentElement = true) {
  if (!currentEditableElement) return false;

  const restored = restoreSelection();
  const selection = window.getSelection();

  if (!restored || !selection.rangeCount || selection.isCollapsed) {
    styleNames.forEach(styleName => {
      currentEditableElement.style[styleName] = "";
    });
    return true;
  }

  const range = selection.getRangeAt(0);

  if (!currentEditableElement.contains(range.commonAncestorContainer)) return false;

  let changed = false;
  const candidates = [
    currentEditableElement,
    ...currentEditableElement.querySelectorAll("span, strong, b, em, i, u")
  ];

  candidates.forEach(element => {
    if (!range.intersectsNode(element)) return;

    styleNames.forEach(styleName => {
      if (element.style && element.style[styleName]) {
        element.style[styleName] = "";
        changed = true;
      }
    });

    if ((element.tagName === "U" || element.tagName === "B" || element.tagName === "I") && element.parentNode) {
      unwrapElement(element);
      changed = true;
    }
  });

  if (!changed && fallbackToCurrentElement) {
    styleNames.forEach(styleName => {
      currentEditableElement.style[styleName] = "";
    });
    changed = true;
  }

  savedRange = range.cloneRange();
  return changed;
}

function unwrapElement(element) {
  const parent = element.parentNode;

  while (element.firstChild) {
    parent.insertBefore(element.firstChild, element);
  }

  parent.removeChild(element);
}

function getCurrentFontSize(target) {
  const selection = window.getSelection();
  let referenceNode = null;

  if (
    selection.rangeCount > 0 &&
    !selection.isCollapsed &&
    target.contains(selection.anchorNode)
  ) {
    referenceNode = selection.anchorNode;
  }

  if (!referenceNode) {
    referenceNode = target;
  }

  const referenceElement = referenceNode.nodeType === Node.ELEMENT_NODE
    ? referenceNode
    : referenceNode.parentElement;

  const fontSize = parseFloat(window.getComputedStyle(referenceElement || target).fontSize);

  return Number.isFinite(fontSize) ? Math.round(fontSize) : "";
}

function getCurrentFontFamily(target) {
  const selection = window.getSelection();
  let referenceNode = null;

  if (
    selection.rangeCount > 0 &&
    !selection.isCollapsed &&
    target.contains(selection.anchorNode)
  ) {
    referenceNode = selection.anchorNode;
  }

  if (!referenceNode) {
    referenceNode = target;
  }

  const referenceElement = referenceNode.nodeType === Node.ELEMENT_NODE
    ? referenceNode
    : referenceNode.parentElement;

  return window.getComputedStyle(referenceElement || target).fontFamily;
}

function getCurrentTextAlign(target) {
  return window.getComputedStyle(target).textAlign || "left";
}

function getCurrentTextFormat(target) {
  const referenceElement = getSelectionReferenceElement(target);
  const styles = window.getComputedStyle(referenceElement || target);
  const fontWeight = Number(styles.fontWeight);
  const textDecoration = styles.textDecorationLine || styles.textDecoration || "";

  return {
    bold: Number.isFinite(fontWeight) ? fontWeight >= 600 : styles.fontWeight === "bold",
    italic: styles.fontStyle === "italic" || styles.fontStyle === "oblique",
    underline: textDecoration.includes("underline")
  };
}

function getSelectionReferenceElement(target) {
  const selection = window.getSelection();
  let referenceNode = null;

  if (
    selection.rangeCount > 0 &&
    !selection.isCollapsed &&
    target.contains(selection.anchorNode)
  ) {
    referenceNode = selection.anchorNode;
  }

  if (!referenceNode) {
    referenceNode = target;
  }

  return referenceNode.nodeType === Node.ELEMENT_NODE
    ? referenceNode
    : referenceNode.parentElement;
}

function updateFontFamilySelectValue(select, fontFamily) {
  if (!select) return;

  const normalizedFamily = String(fontFamily || "").toLowerCase();
  const matchingOption = Array.from(select.options).find(option => {
    const optionValue = option.value.toLowerCase();
    const optionLabel = option.textContent.toLowerCase();
    const primaryFamily = optionValue
      .split(",")[0]
      .replace(/['"]/g, "")
      .trim();

    return (
      normalizedFamily.includes(optionLabel) ||
      normalizedFamily.includes(primaryFamily) ||
      normalizedFamily === optionValue
    );
  });

  select.value = matchingOption ? matchingOption.value : "Arial, sans-serif";
}

function updateFontSizeInputLabel(input, size) {
  const numericSize = Number(size);

  if (!Number.isFinite(numericSize) || numericSize <= 0) {
    input.value = "";
    return;
  }

  input.value = String(Math.round(numericSize));
}

function updateFormatToggleButtons(target, boldButton, italicButton, underlineButton) {
  if (!target) return;

  const format = getCurrentTextFormat(target);
  const buttonStates = [
    [boldButton, format.bold],
    [italicButton, format.italic],
    [underlineButton, format.underline]
  ];

  buttonStates.forEach(([button, isActive]) => {
    if (!button) return;

    button.classList.toggle("is-selected", isActive);
    button.setAttribute("aria-pressed", String(isActive));
  });
}

function updateAlignmentButtons(buttons, alignment) {
  const normalizedAlignment = alignment === "start" ? "left" : alignment;

  buttons.forEach(button => {
    const isSelected = button.dataset.align === normalizedAlignment;

    button.classList.toggle("is-selected", isSelected);
    button.setAttribute("aria-pressed", String(isSelected));
  });
}

