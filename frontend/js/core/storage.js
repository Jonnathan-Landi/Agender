(function () {
  const supportedKeys = [
    "agender.profile.preferences",
    "agender.profile.onedrive-sources",
    "agender.agenda.events",
    "agender.diary.tasks",
    "agender.diary.focus",
    "agender.request.records",
    "agender.hydromet.qc-methods",
    "agender.reports.water-quality",
    "agender.reports.water-quality.preferences"
  ];
  const pending = new Map();

  async function init() {
    const response = await fetch("/api/user-data", { cache: "no-store" });
    if (!response.ok) throw new Error("No fue posible cargar los datos del usuario.");
    const result = await response.json();
    const serverData = result.data || {};

    const migrations = supportedKeys.map(async (key) => {
      const localKey = scopedKey(key);
      const queued = readLocal(pendingKey(key));
      if (queued.found) {
        await persist(key, queued.value, JSON.stringify(queued.value));
        localStorage.setItem(localKey, JSON.stringify(queued.value));
      } else if (Object.prototype.hasOwnProperty.call(serverData, key)) {
        localStorage.setItem(localKey, JSON.stringify(serverData[key]));
      } else {
        const localValue = readLocal(localKey);
        if (localValue.found) await persist(key, localValue.value, JSON.stringify(localValue.value));
      }
    });
    await Promise.all(migrations);
  }

  async function refreshFromServer() {
    const response = await fetch("/api/user-data", { cache: "no-store" });
    if (!response.ok) throw new Error("No fue posible actualizar los datos sincronizados.");
    const result = await response.json();
    const serverData = result.data || {};
    const changedKeys = [];
    supportedKeys.forEach((key) => {
      if (!Object.prototype.hasOwnProperty.call(serverData, key)) return;
      if (readLocal(pendingKey(key)).found) return;
      const localKey = scopedKey(key);
      const serialized = JSON.stringify(serverData[key]);
      if (localStorage.getItem(localKey) === serialized) return;
      localStorage.setItem(localKey, serialized);
      changedKeys.push(key);
    });
    if (changedKeys.length) {
      window.dispatchEvent(new CustomEvent("agender:data-refreshed", {
        detail: { keys: changedKeys }
      }));
    }
    return changedKeys;
  }

  function loadJson(key, fallback) {
    try {
      const value = JSON.parse(localStorage.getItem(scopedKey(key)));
      return value === null ? fallback : value;
    } catch (error) {
      return fallback;
    }
  }

  function saveJson(key, value, options = {}) {
    const serialized = JSON.stringify(value);
    localStorage.setItem(scopedKey(key), serialized);
    localStorage.setItem(pendingKey(key), serialized);
    const previous = pending.get(key) || Promise.resolve();
    const request = previous
      .catch(() => {})
      .then(() => persist(key, value, serialized, options))
      .catch((error) => console.error(error));
    pending.set(key, request);
    request.then(() => { if (pending.get(key) === request) pending.delete(key); });
    return request;
  }

  function updateJson(key, changes) {
    const current = loadJson(key, {});
    const next = { ...(current && typeof current === "object" ? current : {}), ...changes };
    return saveJson(key, next);
  }

  async function persist(key, value, serialized, options = {}) {
    const response = await fetch(`/api/user-data/${encodeURIComponent(key)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ value })
    });
    if (!response.ok) throw new Error("No fue posible guardar los datos del usuario.");
    if (localStorage.getItem(pendingKey(key)) === serialized) localStorage.removeItem(pendingKey(key));
    if (options.notify !== false) {
      window.dispatchEvent(new CustomEvent("agender:data-saved", { detail: { key } }));
    }
  }

  function readLocal(key) {
    const raw = localStorage.getItem(key);
    if (raw === null) return { found: false };
    try { return { found: true, value: JSON.parse(raw) }; }
    catch { return { found: false }; }
  }

  function scopedKey(key) {
    const user = localStorage.getItem("agender.auth.user") || "anonymous";
    return `user.${user}.${key}`;
  }

  function pendingKey(key) {
    return `${scopedKey(key)}.pending`;
  }

  window.NotasStorage = {
    init,
    refreshFromServer,
    loadJson,
    saveJson,
    updateJson
  };
})();
