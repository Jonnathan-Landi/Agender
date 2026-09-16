(function () {
  let initialized = false;
  let frames = [];
  let position = -1;
  let timer = null;
  let followLatest = true;
  let exporting = false;
  let refreshTimer = null;

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
    image.onerror = () => { document.querySelector("#goes19-cache-status").textContent = "La toma ya salió de la ventana; actualizando…"; refresh(); };
    image.src = item.imageUrl;
    document.querySelector("#goes19-frame-time").textContent =
      new Date(item.localTime).toLocaleString("es-EC", { dateStyle: "medium", timeStyle: "short" });
    document.querySelector("#goes19-position").textContent = `${position + 1} / ${frames.length} imágenes`;
  }

  async function refresh() {
    try {
      const response = await fetch("/api/goes19/frames", { cache: "no-store" });
      if (!response.ok) throw new Error("No se pudo consultar GOES 19.");
      const catalog = await response.json();
      const currentId = frames[position]?.id;
      frames = catalog.frames || [];
      updateExportButton();
      document.querySelector("#goes19-cache-status").textContent =
        frames.length < 19
          ? `${frames.length} tomas disponibles · completando las últimas 3 horas en segundo plano…`
          : `${frames.length} tomas disponibles · últimas 3 horas · actualización cada 10 minutos`;
      if (!frames.length) {
        position = -1;
        const image = document.querySelector("#goes19-frame");
        image.removeAttribute("src");
        image.hidden = true;
        document.querySelector("#goes19-empty").hidden = false;
        document.querySelector("#goes19-frame-time").textContent = "Preparando imágenes con el diseño actual…";
        document.querySelector("#goes19-position").textContent = "0 / 0 imágenes";
        return;
      }
      const retained = frames.findIndex((frame) => frame.id === currentId);
      showFrame(followLatest || retained < 0 ? frames.length - 1 : retained);
    } catch (error) {
      document.querySelector("#goes19-cache-status").textContent = error.message;
    } finally {
      clearTimeout(refreshTimer);
      // During the first fill, show each frame as soon as the background
      // worker finishes it. Once the window is full, a minute is sufficient.
      refreshTimer = window.setTimeout(refresh, frames.length < 19 ? 5_000 : 60_000);
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
