(function () {
  const formats = Object.freeze([
    "caudales",
    "lluvias",
    "temperaturas",
    "pronostico-diario",
    "pronostico-semanal",
    "indice-ultravioleta"
  ]);

  function blobToDataUrl(blob) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result);
      reader.onerror = () => reject(new Error("No se pudo preparar una imagen para exportar."));
      reader.readAsDataURL(blob);
    });
  }

  async function exportImageSource(image) {
    const source = image.getAttribute("src") || "";
    if (!source || source.startsWith("data:")) return source;
    const response = await fetch(new URL(source, document.baseURI).href, {
      cache: "no-store",
      credentials: "same-origin"
    });
    if (!response.ok) {
      throw new Error("Una de las imágenes del diseño no pudo prepararse para exportar.");
    }
    return blobToDataUrl(await response.blob());
  }

  async function serializeDesignForExport(format) {
    const page = document.querySelector(
      `#hydromet-panel-design [data-hydromet-format="${format}"]`
    );
    if (!page) throw new Error(`No se encontró el diseño ${format}.`);
    const clone = page.cloneNode(true);
    const sourceImages = Array.from(page.querySelectorAll("img"));
    const clonedImages = Array.from(clone.querySelectorAll("img"));
    await Promise.all(sourceImages.map(async (image, index) => {
      const clonedImage = clonedImages[index];
      if (!clonedImage) return;
      if (image.classList.contains("hydromet-report-template")) {
        clonedImage.removeAttribute("src");
        clonedImage.removeAttribute("loading");
        return;
      }
      const source = await exportImageSource(image);
      if (source) clonedImage.setAttribute("src", source);
      else clonedImage.removeAttribute("src");
      clonedImage.hidden = image.hidden;
      clonedImage.removeAttribute("loading");
      clonedImage.classList.remove("is-selected");
    }));
    clone.classList.remove("is-cropping");
    clone.querySelectorAll(
      ".hydromet-upload-zone, .hydromet-crop-overlay, input[type='file']"
    ).forEach((element) => element.remove());
    clone.querySelectorAll("[contenteditable]").forEach((element) => {
      element.removeAttribute("contenteditable");
    });
    return { format, html: clone.outerHTML };
  }

  function syncSelection() {
    const selectAll = document.querySelector("#hydromet-design-export-all");
    const options = Array.from(document.querySelectorAll(
      "#hydromet-design-export-list input"
    ));
    if (!selectAll || !options.length) return;
    selectAll.checked = options.every((option) => option.checked);
    selectAll.indeterminate = (
      options.some((option) => option.checked) &&
      options.some((option) => !option.checked)
    );
  }

  function setMessage(message, isError = false) {
    const element = document.querySelector("#hydromet-design-export-message");
    if (!element) return;
    element.textContent = message;
    element.classList.toggle("is-error", isError);
  }

  function setBusy(busy) {
    const form = document.querySelector("#hydromet-design-export-form");
    const confirm = document.querySelector("#hydromet-design-export-confirm");
    const cancel = document.querySelector("#hydromet-design-export-cancel");
    const close = document.querySelector("#hydromet-design-export-close");
    const label = confirm?.querySelector("span:last-child");
    form?.setAttribute("aria-busy", String(busy));
    if (confirm) confirm.disabled = busy;
    if (cancel) cancel.disabled = busy;
    if (close) close.disabled = busy;
    if (label) label.textContent = busy ? "Exportando…" : "Exportar JPG";
  }

  function closeDialog() {
    const dialog = document.querySelector("#hydromet-design-export-dialog");
    if (dialog?.open) dialog.close();
  }

  function init(options) {
    const dialog = document.querySelector("#hydromet-design-export-dialog");
    const selectAll = document.querySelector("#hydromet-design-export-all");
    const list = document.querySelector("#hydromet-design-export-list");

    document.querySelector("#hydromet-design-export-open")
      ?.addEventListener("click", () => {
        options.cancelCrop();
        options.clearSelection();
        document.querySelectorAll("#hydromet-design-export-list input")
          .forEach((option) => { option.checked = true; });
        syncSelection();
        setMessage("");
        if (dialog && !dialog.open) dialog.showModal();
      });
    document.querySelector("#hydromet-design-export-close")
      ?.addEventListener("click", closeDialog);
    document.querySelector("#hydromet-design-export-cancel")
      ?.addEventListener("click", closeDialog);
    document.querySelector("#hydromet-design-export-form")
      ?.addEventListener("submit", async (event) => {
        event.preventDefault();
        const selected = Array.from(document.querySelectorAll(
          "#hydromet-design-export-list input:checked"
        )).map((option) => option.value);
        if (!selected.length) {
          setMessage("Selecciona al menos un diseño.", true);
          return;
        }
        if (selected.some((format) => !formats.includes(format))) {
          setMessage("La selección contiene un diseño no reconocido.", true);
          return;
        }
        setBusy(true);
        setMessage("Preparando los diseños…");
        try {
          const reports = [];
          for (const format of selected) {
            reports.push(await serializeDesignForExport(format));
          }
          setMessage("Selecciona la carpeta donde deseas guardar las imágenes.");
          const reportDate = options.getReportDate();
          const response = await fetch("/api/reports/hydromet-network/export-designs", {
            method: "POST",
            headers: { "Content-Type": "application/json", Accept: "application/json" },
            body: JSON.stringify({
              reportDate: options.formatCalendarDay(reportDate),
              reportTime: `${options.padNumber(reportDate.getHours())}:${options.padNumber(reportDate.getMinutes())}`,
              reports
            })
          });
          const responseText = await response.text();
          let result = {};
          try {
            result = responseText ? JSON.parse(responseText) : {};
          } catch {
            result = {
              detail: response.ok
                ? "El servidor devolvió una respuesta no válida."
                : "El servidor no pudo completar la exportación con el motor integrado."
            };
          }
          if (!response.ok) {
            throw new Error(result.detail || "No fue posible exportar los diseños.");
          }
          if (result.canceled) {
            setMessage("Exportación cancelada.");
            return;
          }
          setMessage(
            `${result.count} diseño${result.count === 1 ? "" : "s"} guardado${result.count === 1 ? "" : "s"} en ${result.folderName}.`
          );
        } catch (error) {
          setMessage(error.message || "No fue posible exportar los diseños.", true);
        } finally {
          setBusy(false);
        }
      });
    dialog?.addEventListener("cancel", (event) => {
      if (dialog.querySelector("form")?.getAttribute("aria-busy") === "true") {
        event.preventDefault();
      }
    });
    selectAll?.addEventListener("change", () => {
      list?.querySelectorAll("input").forEach((option) => {
        option.checked = selectAll.checked;
      });
      syncSelection();
    });
    list?.addEventListener("change", syncSelection);
  }

  window.NotasHydrometDesignExport = { init };
})();
