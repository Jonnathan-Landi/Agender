(function () {
  let initialized = false;
  let frames = [];
  let position = -1;
  let timer = null;
  let followLatest = true;
  let exporting = false;
  let refreshTimer = null;
  let refreshing = false;

  function updateExportButton() {
    document.querySelector("#goes19-export").disabled = exporting || frames.length < 2;
  }

  async function exportVideo() {
    if (exporting || frames.length < 2) return;
    exporting = true;
    updateExportButton();
    const status = document.querySelector("#goes19-export-status");
    status.textContent = "Elige dónde guardar el MP4…";
    try {
      const response = await fetch("/api/goes19/export-mp4", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ frameIds: frames.map((frame) => frame.id) }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || "No se pudo exportar el video.");
      status.textContent = result.canceled ? "Exportación cancelada." :
        `MP4 guardado: ${result.path} · ${result.frames} imágenes`;
    } catch (error) {
      status.textContent = error.message;
      refresh();
    } finally {
      exporting = false;
      updateExportButton();
    }
  }

  function showFrame(index) {
    if (!frames.length) return;
    position = (index + frames.length) % frames.length;
    const item = frames[position];
    const image = document.querySelector("#goes19-frame");
    image.onload = () => { image.hidden = false; document.querySelector("#goes19-empty").hidden = true; };
    image.onerror = () => {
      document.querySelector("#goes19-cache-status").textContent = "No se pudo cargar esta toma. Se reintentará en la siguiente actualización.";
      image.removeAttribute("src");
    };
    if (image.getAttribute("src") !== item.imageUrl) image.src = item.imageUrl;
    document.querySelector("#goes19-frame-time").textContent =
      new Date(item.localTime).toLocaleString("es-EC", { dateStyle: "medium", timeStyle: "short" });
    document.querySelector("#goes19-position").textContent = `${position + 1} / ${frames.length} imágenes`;
  }

  async function refresh() {
    if (refreshing) return;
    refreshing = true;
    let busy = false;
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 15_000);
    try {
      const response = await fetch("/api/goes19/frames", { cache: "no-store", signal: controller.signal });
      if (!response.ok) throw new Error("No se pudo consultar GOES 19.");
      const catalog = await response.json();
      const currentId = frames[position]?.id;
      frames = catalog.frames || [];
      updateExportButton();
      const status = catalog.status || {};
      busy = ["starting", "listing", "downloading", "processing", "backfill"].includes(status.phase);
      document.querySelector("#goes19-cache-status").textContent =
        `${frames.length} tomas disponibles · ${status.message || "Esperando la próxima publicación de NOAA."}`;
      if (!frames.length) {
        position = -1;
        const image = document.querySelector("#goes19-frame");
        image.removeAttribute("src");
        image.hidden = true;
        document.querySelector("#goes19-empty").hidden = false;
        document.querySelector("#goes19-frame-time").textContent = status.phase === "error"
          ? "No se pudo preparar la imagen; se reintentará automáticamente."
          : "Esperando la primera toma disponible…";
        document.querySelector("#goes19-empty").textContent = status.message || "Buscando imágenes en NOAA…";
        document.querySelector("#goes19-position").textContent = "0 / 0 imágenes";
        return;
      }
      const retained = frames.findIndex((frame) => frame.id === currentId);
      showFrame(followLatest || retained < 0 ? frames.length - 1 : retained);
    } catch (error) {
      document.querySelector("#goes19-cache-status").textContent = error.name === "AbortError"
        ? "El servidor tardó demasiado en responder. Se reintentará automáticamente."
        : error.message;
    } finally {
      clearTimeout(timeout);
      refreshing = false;
      clearTimeout(refreshTimer);
      // Poll quickly only while work is active; NOAA may publish fewer than 19 scans.
      refreshTimer = window.setTimeout(refresh, busy ? 5_000 : 60_000);
    }
  }

  function togglePlay() {
    const button = document.querySelector("#goes19-play");
    if (timer) {
      clearInterval(timer);
      timer = null;
      button.textContent = "▶";
      return;
    }
    if (!frames.length) return;
    timer = setInterval(() => showFrame(position + 1), 750);
    button.textContent = "Ⅱ";
  }

  function init() {
    if (initialized || !document.querySelector("#goes19-view")) return;
    initialized = true;
    document.querySelector("#goes19-previous")?.addEventListener("click", () => { followLatest = false; showFrame(position - 1); });
    document.querySelector("#goes19-next")?.addEventListener("click", () => { followLatest = false; showFrame(position + 1); });
    document.querySelector("#goes19-play")?.addEventListener("click", togglePlay);
    document.querySelector("#goes19-export")?.addEventListener("click", exportVideo);
    refresh();
  }

  window.NotasGoes19 = { init };
})();
