(function () {
  const AUTO_INTERVAL_MS = 60000;
  const SAVE_DEBOUNCE_MS = 5000;
  let enabled = false;
  let connected = false;
  let syncing = null;
  let saveTimer = null;
  let interval = null;

  async function bootstrap() {
    await refreshStatus();
    if (!enabled || !connected || !navigator.onLine) return null;
    return syncNow({ quiet: true });
  }

  function start() {
    clearInterval(interval);
    interval = setInterval(() => {
      if (!document.hidden) syncNow({ quiet: true });
    }, AUTO_INTERVAL_MS);
    window.addEventListener("agender:data-saved", scheduleAfterSave);
    window.addEventListener("online", () => syncNow({ quiet: true }));
    document.addEventListener("visibilitychange", () => {
      if (!document.hidden) syncNow({ quiet: true });
    });
  }

  async function refreshStatus() {
    try {
      const response = await fetch("/api/cloud/status", { cache: "no-store" });
      if (!response.ok) return null;
      const payload = await response.json();
      const oneDrive = (payload.providers && payload.providers.onedrive) || {};
      enabled = Boolean(oneDrive.syncEnabled);
      connected = Boolean(oneDrive.connected);
      emitStatus({
        state: !connected ? "disconnected" : enabled ? "ready" : "disabled",
        provider: oneDrive
      });
      return oneDrive;
    } catch {
      emitStatus({ state: "offline" });
      return null;
    }
  }

  async function setEnabled(value) {
    const response = await fetch("/api/cloud/onedrive/sync", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: Boolean(value) })
    });
    const result = await readResponse(response);
    enabled = Boolean(result.enabled);
    emitStatus({ state: enabled ? "ready" : "disabled" });
    if (enabled) await syncNow();
    return result;
  }

  function scheduleAfterSave() {
    if (!enabled || !connected) return;
    clearTimeout(saveTimer);
    saveTimer = setTimeout(() => syncNow({ quiet: true }), SAVE_DEBOUNCE_MS);
  }

  async function syncNow(options = {}) {
    if (syncing) return syncing;
    if (!enabled && options.quiet) return null;
    if (!navigator.onLine) {
      emitStatus({ state: "offline" });
      return null;
    }
    syncing = performSync(options).finally(() => { syncing = null; });
    return syncing;
  }

  async function performSync({ quiet = false } = {}) {
    if (!quiet) emitStatus({ state: "syncing" });
    try {
      const response = await fetch("/api/cloud/onedrive/sync", { method: "POST" });
      const result = await readResponse(response);
      connected = true;
      emitStatus({ state: result.busy ? "syncing" : "synced", result });
      if (Number(result.remoteApplied) > 0) await window.NotasStorage.refreshFromServer();
      return result;
    } catch (error) {
      emitStatus({ state: navigator.onLine ? "error" : "offline", error: error.message });
      if (!quiet) throw error;
      return null;
    }
  }

  async function readResponse(response) {
    let payload = {};
    try { payload = await response.json(); } catch {}
    if (!response.ok) throw new Error(payload.detail || "No fue posible sincronizar con OneDrive.");
    return payload;
  }

  function emitStatus(detail) {
    window.dispatchEvent(new CustomEvent("agender:sync-status", { detail }));
  }

  window.NotasSync = {
    bootstrap,
    start,
    refreshStatus,
    setEnabled,
    syncNow
  };
})();
