(function () {
  function loadJson(key, fallback) {
    try {
      const value = JSON.parse(localStorage.getItem(scopedKey(key)));
      return value === null ? fallback : value;
    } catch (error) {
      return fallback;
    }
  }

  function saveJson(key, value) {
    localStorage.setItem(scopedKey(key), JSON.stringify(value));
  }

  function scopedKey(key) {
    const user = localStorage.getItem("agender.auth.user") || "anonymous";
    return `user.${user}.${key}`;
  }

  window.NotasStorage = {
    loadJson,
    saveJson
  };
})();
