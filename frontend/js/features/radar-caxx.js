(function () {
  const NS = "http://www.w3.org/2000/svg";

  function svgElement(name, attributes = {}) {
    const element = document.createElementNS(NS, name);
    Object.entries(attributes).forEach(([key, value]) => element.setAttribute(key, value));
    return element;
  }

  function pathData(polygons) {
    return polygons.map((polygon) => polygon.map((ring) => ring
      .map(([x, y], index) => `${index ? "L" : "M"}${x} ${y}`)
      .join(" ") + " Z").join(" ")).join(" ");
  }

  function addFeature(group, feature, className, featureType = "Cantón") {
    const path = svgElement("path", { d: pathData(feature.polygons), class: className, "vector-effect": "non-scaling-stroke" });
    const title = svgElement("title");
    title.textContent = `${featureType} ${feature.name}`;
    path.appendChild(title);
    group.appendChild(path);
    return path;
  }

  function featureCenter(feature) {
    const points = feature.polygons.flat(2);
    const xs = points.map(([x]) => x);
    const ys = points.map(([, y]) => y);
    return [(Math.min(...xs) + Math.max(...xs)) / 2, (Math.min(...ys) + Math.max(...ys)) / 2];
  }

  function utm17sToWgs84(easting, northing) {
    const a = 6378137;
    const eccentricity = 0.00669437999014;
    const scale = 0.9996;
    const x = easting - 500000;
    const y = northing - 10000000;
    const meridian = y / scale;
    const mu = meridian / (a * (1 - eccentricity / 4 - 3 * eccentricity ** 2 / 64 - 5 * eccentricity ** 3 / 256));
    const e1 = (1 - Math.sqrt(1 - eccentricity)) / (1 + Math.sqrt(1 - eccentricity));
    const footpoint = mu
      + (3 * e1 / 2 - 27 * e1 ** 3 / 32) * Math.sin(2 * mu)
      + (21 * e1 ** 2 / 16 - 55 * e1 ** 4 / 32) * Math.sin(4 * mu)
      + 151 * e1 ** 3 / 96 * Math.sin(6 * mu)
      + 1097 * e1 ** 4 / 512 * Math.sin(8 * mu);
    const second = eccentricity / (1 - eccentricity) * Math.cos(footpoint) ** 2;
    const tangent = Math.tan(footpoint) ** 2;
    const prime = a / Math.sqrt(1 - eccentricity * Math.sin(footpoint) ** 2);
    const radius = a * (1 - eccentricity) / (1 - eccentricity * Math.sin(footpoint) ** 2) ** 1.5;
    const d = x / (prime * scale);
    const latitude = footpoint - prime * Math.tan(footpoint) / radius * (
      d ** 2 / 2
      - (5 + 3 * tangent + 10 * second - 4 * second ** 2 - 9 * eccentricity / (1 - eccentricity)) * d ** 4 / 24
      + (61 + 90 * tangent + 298 * second + 45 * tangent ** 2 - 252 * eccentricity / (1 - eccentricity) - 3 * second ** 2) * d ** 6 / 720
    );
    const longitude = -81 * Math.PI / 180 + (
      d - (1 + 2 * tangent + second) * d ** 3 / 6
      + (5 - 2 * second + 28 * tangent - 3 * second ** 2 + 8 * eccentricity / (1 - eccentricity) + 24 * tangent ** 2) * d ** 5 / 120
    ) / Math.cos(footpoint);
    return [longitude * 180 / Math.PI, latitude * 180 / Math.PI];
  }

  function wgs84ToUtm17s(longitude, latitude) {
    const a = 6378137;
    const eccentricity = 0.00669437999014;
    const scale = 0.9996;
    const lat = latitude * Math.PI / 180;
    const lon = longitude * Math.PI / 180;
    const central = -81 * Math.PI / 180;
    const prime = a / Math.sqrt(1 - eccentricity * Math.sin(lat) ** 2);
    const tangent = Math.tan(lat) ** 2;
    const second = eccentricity / (1 - eccentricity) * Math.cos(lat) ** 2;
    const arc = Math.cos(lat) * (lon - central);
    const meridian = a * (
      (1 - eccentricity / 4 - 3 * eccentricity ** 2 / 64 - 5 * eccentricity ** 3 / 256) * lat
      - (3 * eccentricity / 8 + 3 * eccentricity ** 2 / 32 + 45 * eccentricity ** 3 / 1024) * Math.sin(2 * lat)
      + (15 * eccentricity ** 2 / 256 + 45 * eccentricity ** 3 / 1024) * Math.sin(4 * lat)
      - 35 * eccentricity ** 3 / 3072 * Math.sin(6 * lat)
    );
    const easting = scale * prime * (arc + (1 - tangent + second) * arc ** 3 / 6
      + (5 - 18 * tangent + tangent ** 2 + 72 * second - 58 * eccentricity / (1 - eccentricity)) * arc ** 5 / 120) + 500000;
    const northing = scale * (meridian + prime * Math.tan(lat) * (arc ** 2 / 2
      + (5 - tangent + 9 * second + 4 * second ** 2) * arc ** 4 / 24
      + (61 - 58 * tangent + tangent ** 2 + 600 * second - 330 * eccentricity / (1 - eccentricity)) * arc ** 6 / 720)) + 10000000;
    return [easting, northing];
  }

  function tileLongitude(x, zoom) {
    return x / 2 ** zoom * 360 - 180;
  }

  function tileLatitude(y, zoom) {
    return Math.atan(Math.sinh(Math.PI * (1 - 2 * y / 2 ** zoom))) * 180 / Math.PI;
  }

  function tileCoordinate(longitude, latitude, zoom) {
    const size = 2 ** zoom;
    const x = Math.floor((longitude + 180) / 360 * size);
    const latitudeRadians = latitude * Math.PI / 180;
    const y = Math.floor((1 - Math.asinh(Math.tan(latitudeRadians)) / Math.PI) / 2 * size);
    return [x, y];
  }

  function addImageryTiles(svg, minX, minY, maxX, maxY) {
    const zoom = 11;
    const [west, south] = utm17sToWgs84(minX, minY);
    const [east, north] = utm17sToWgs84(maxX, maxY);
    const [visibleFirstX, visibleFirstY] = tileCoordinate(west, north, zoom);
    const [visibleLastX, visibleLastY] = tileCoordinate(east, south, zoom);
    // Sobrecobertura para ventanas panorámicas y la convergencia propia de UTM.
    const firstX = visibleFirstX - 3;
    const lastX = visibleLastX + 3;
    const firstY = visibleFirstY - 2;
    const lastY = visibleLastY + 2;
    const tiles = svgElement("g", { class: "radar-basemap" });
    for (let tileY = firstY; tileY <= lastY; tileY += 1) {
      for (let tileX = firstX; tileX <= lastX; tileX += 1) {
        const tileWest = tileLongitude(tileX, zoom);
        const tileEast = tileLongitude(tileX + 1, zoom);
        const tileNorth = tileLatitude(tileY, zoom);
        const tileSouth = tileLatitude(tileY + 1, zoom);
        const [left, top] = wgs84ToUtm17s(tileWest, tileNorth);
        const [right, bottom] = wgs84ToUtm17s(tileEast, tileSouth);
        tiles.appendChild(svgElement("image", {
          href: `/api/radar-caxx/imagery/${zoom}/${tileY}/${tileX}`,
          x: left,
          y: -top,
          width: right - left + 120,
          height: top - bottom + 120,
          preserveAspectRatio: "none"
        }));
      }
    }
    svg.appendChild(tiles);
  }

  function imageryExportUrl(area = "cuenca") {
    return `/api/radar-caxx/basemap.jpg?area=${encodeURIComponent(area)}&v=5`;
  }

  function addImageryExport(svg, radarX, radarY) {
    const image = svgElement("image", {
      x: radarX - 288_000,
      y: -(radarY + 105_000),
      width: 576_000,
      height: 240_000,
      preserveAspectRatio: "none",
      class: "radar-basemap"
    });
    image.addEventListener("load", () => image.classList.add("is-ready"));
    image.addEventListener("error", () => {
      const retry = new URL(image.getAttribute("href"), window.location.href);
      retry.searchParams.set("retry", String(Date.now()));
      image.setAttribute("href", retry.pathname + retry.search);
    });
    svg.appendChild(image);
    image.setAttribute("href", imageryExportUrl());
    return image;
  }

  function surveillanceFrame(features, aspect, verticalPadding) {
    const points = features.flatMap((feature) => feature.polygons.flat(2));
    const xs = points.map(([x]) => x);
    const ys = points.map(([, y]) => y);
    const minY = Math.min(...ys) - verticalPadding;
    const maxY = Math.max(...ys) + verticalPadding;
    const centerX = (Math.min(...xs) + Math.max(...xs)) / 2;
    const width = (maxY - minY) * aspect;
    return [centerX - width / 2, -maxY, width, maxY - minY];
  }

  function init() {
    const host = document.querySelector("#radar-caxx-map");
    const data = window.RADAR_CAXX_GEODATA;
    if (!host || !data || host.dataset.ready) return;
    if (!host.clientWidth || !host.clientHeight) {
      if (!host.dataset.prefetchStarted) {
        host.dataset.prefetchStarted = "true";
        fetch(imageryExportUrl(), { cache: "force-cache" }).catch(() => {});
      }
      if (!host.dataset.waitingForLayout) {
        host.dataset.waitingForLayout = "true";
        const observer = new ResizeObserver(() => {
          if (!host.clientWidth || !host.clientHeight) return;
          observer.disconnect();
          delete host.dataset.waitingForLayout;
          init();
        });
        observer.observe(host);
      }
      return;
    }
    host.dataset.ready = "true";

    const [radarX, radarY] = data.radar;
    // Encuadre local al estilo GOESHub: el radio de 100 km queda próximo al
    // borde y el radar se desplaza hacia arriba para mostrar más territorio al sur.
    const workspace = document.querySelector(".workspace");
    const availableWidth = host.clientWidth || workspace?.clientWidth || window.innerWidth;
    const availableHeight = host.clientHeight || Math.max(340, (workspace?.clientHeight || window.innerHeight) - 105);
    const viewportAspect = Math.max(0.9, Math.min(2.4, availableWidth / availableHeight));
    const minY = radarY - 135_000;
    const maxY = radarY + 105_000;
    const width = Math.round(((maxY - minY) * viewportAspect) / 10_000) * 10_000;
    const minX = radarX - width / 2;
    const maxX = radarX + width / 2;
    const height = maxY - minY;
    const svg = svgElement("svg", {
      viewBox: `${minX} ${-maxY} ${width} ${height}`,
      preserveAspectRatio: "xMidYMid meet",
      "aria-hidden": "true"
    });
    const basemapImage = addImageryExport(svg, radarX, radarY);
    const surveillanceFrames = {
      cuenca: [minX, -maxY, width, height],
      subcuencas: surveillanceFrame(data.subcuencas, viewportAspect, 10_000),
      urbana: surveillanceFrame(data.zonaUrbana, viewportAspect, 4_000)
    };
    const basemapBounds = {
      cuenca: [406_951, 9_559_793, 982_951, 9_799_793],
      subcuencas: [605_974, 9_639_119, 804_528, 9_721_850],
      urbana: [698_424, 9_671_257, 750_169, 9_692_836]
    };
    const radarOverlay = svgElement("image", {
      x: radarX - 100_000,
      y: -(radarY + 100_000),
      width: 200_000,
      height: 200_000,
      preserveAspectRatio: "none",
      class: "radar-data-overlay"
    });
    svg.appendChild(radarOverlay);
    const map = svgElement("g", { transform: "scale(1 -1)" });
    map.appendChild(svgElement("path", {
      d: pathData(data.country),
      class: "radar-country",
      "vector-effect": "non-scaling-stroke"
    }));

    [...data.radii].reverse().forEach((radius) => {
      map.appendChild(svgElement("circle", {
        cx: radarX, cy: radarY, r: radius,
        class: `radar-radius radar-radius-${radius / 1000}`,
        "vector-effect": "non-scaling-stroke"
      }));
    });

    const cuenca = data.cuenca[0];
    const areaGroups = {};
    if (cuenca) {
      areaGroups.cuenca = svgElement("g", { class: "radar-area-layer" });
      addFeature(areaGroups.cuenca, cuenca, "radar-cuenca-halo");
      addFeature(areaGroups.cuenca, cuenca, "radar-cuenca");
      map.appendChild(areaGroups.cuenca);
    }
    areaGroups.subcuencas = svgElement("g", { class: "radar-area-layer", hidden: "" });
    data.subcuencas.forEach((feature) => {
      addFeature(areaGroups.subcuencas, feature, "radar-area-halo", "Subcuenca");
      addFeature(areaGroups.subcuencas, feature, "radar-area-outline", "Subcuenca");
    });
    map.appendChild(areaGroups.subcuencas);
    areaGroups.urbana = svgElement("g", { class: "radar-area-layer", hidden: "" });
    data.zonaUrbana.forEach((feature) => {
      addFeature(areaGroups.urbana, feature, "radar-area-halo", "Zona urbana");
      addFeature(areaGroups.urbana, feature, "radar-area-outline", "Zona urbana");
    });
    map.appendChild(areaGroups.urbana);

    map.appendChild(svgElement("circle", { cx: radarX, cy: radarY, r: 2_800, class: "radar-site-pulse" }));
    map.appendChild(svgElement("circle", { cx: radarX, cy: radarY, r: 1_250, class: "radar-site" }));
    svg.appendChild(map);

    if (cuenca) {
      const [labelX, labelY] = featureCenter(cuenca);
      const labelGroup = svgElement("g", { transform: `translate(${labelX} ${-labelY})`, class: "radar-cuenca-label" });
      const halo = svgElement("text", { x: 0, y: 0, class: "radar-cuenca-label-halo" });
      halo.textContent = "CUENCA";
      const label = svgElement("text", { x: 0, y: 0 });
      label.textContent = "CUENCA";
      labelGroup.append(halo, label);
      svg.appendChild(labelGroup);
      areaGroups.cuencaLabel = labelGroup;
    }

    const markerSize = 9_000;
    svg.appendChild(svgElement("image", {
      href: "assets/radar-weather.svg",
      x: radarX - markerSize / 2,
      y: -radarY - markerSize * 1.12,
      width: markerSize,
      height: markerSize,
      class: "radar-site-icon"
    }));
    host.appendChild(svg);

    const previousButton = document.querySelector("#radar-caxx-previous");
    const playButton = document.querySelector("#radar-caxx-play");
    const nextButton = document.querySelector("#radar-caxx-next");
    const exportButton = document.querySelector("#radar-caxx-export");
    const exportStatus = document.querySelector("#radar-caxx-export-status");
    const timeLabel = document.querySelector("#radar-caxx-frame-time");
    const areaSelect = document.querySelector("#radar-caxx-area");
    const frameCountSelect = document.querySelector("#radar-caxx-frame-count");
    let frames = [];
    let availableFrames = [];
    let frameIndex = -1;
    let playbackTimer = null;

    function formatFrameTime(frame) {
      return new Intl.DateTimeFormat("es-EC", {
        day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", hour12: false
      }).format(new Date(frame.localTime)).replace(",", " ·");
    }

    async function exportVideo() {
      if (frames.length < 2) return;
      stopPlayback();
      const area = areaSelect.value;
      const controls = [exportButton, areaSelect, frameCountSelect, previousButton, playButton, nextButton];
      controls.forEach((control) => { control.disabled = true; });
      const original = exportButton.innerHTML;
      exportStatus.className = "radar-caxx-export-status";
      try {
        exportButton.textContent = "Exportando…";
        exportStatus.textContent = "Elige la carpeta y el nombre; Agender preparará el MP4…";
        const response = await fetch("/api/radar-caxx/export-mp4", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ area, frameIds: frames.map((frame) => frame.id) })
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.detail || "No se pudo exportar el MP4.");
        if (result.canceled) {
          exportStatus.textContent = "Exportación cancelada.";
        } else {
          exportStatus.textContent = `Exportado en: ${result.path}`;
          exportStatus.classList.add("is-success");
          exportStatus.title = result.path;
        }
      } catch (error) {
        exportStatus.textContent = error.message || "No se pudo exportar el MP4.";
        exportStatus.classList.add("is-error");
      } finally {
        exportButton.innerHTML = original;
        controls.forEach((control) => { control.disabled = false; });
        applyFrameLimit(frames[frameIndex]?.id);
      }
    }

    areaSelect.value = localStorage.getItem("agender.radar-caxx.area") || "cuenca";
    frameCountSelect.value = localStorage.getItem("agender.radar-caxx.frames") || "10";

    function showSelectedArea() {
      const selection = areaGroups[areaSelect.value] ? areaSelect.value : "cuenca";
      ["cuenca", "subcuencas", "urbana"].forEach((name) => {
        areaGroups[name]?.toggleAttribute("hidden", name !== selection);
      });
      areaGroups.cuencaLabel?.toggleAttribute("hidden", selection !== "cuenca");
      const [west, south, east, north] = basemapBounds[selection];
      basemapImage.setAttribute("x", west);
      basemapImage.setAttribute("y", -north);
      basemapImage.setAttribute("width", east - west);
      basemapImage.setAttribute("height", north - south);
      basemapImage.classList.remove("is-ready");
      basemapImage.setAttribute("href", imageryExportUrl(selection));
      svg.setAttribute("viewBox", surveillanceFrames[selection].join(" "));
      if (frames.length) showFrame(frameIndex);
    }
    showSelectedArea();

    function applyFrameLimit(latestId) {
      const limit = Math.min(49, Math.max(1, Number(frameCountSelect.value) || 10));
      frames = availableFrames.slice(-limit);
      previousButton.disabled = !frames.length;
      playButton.disabled = !frames.length;
      nextButton.disabled = !frames.length;
      exportButton.disabled = frames.length < 2;
      frames.forEach((frame) => {
        const preload = new Image();
        preload.src = `${frame.imageUrl}?area=${encodeURIComponent(areaSelect.value)}`;
      });
      if (!frames.length) {
        radarOverlay.removeAttribute("href");
        timeLabel.textContent = "Esperando imágenes recientes…";
        return;
      }
      const retainedIndex = latestId ? frames.findIndex((frame) => frame.id === latestId) : -1;
      showFrame(retainedIndex >= 0 ? retainedIndex : frames.length - 1);
    }

    function showFrame(index) {
      if (!frames.length) return;
      frameIndex = (index + frames.length) % frames.length;
      const frame = frames[frameIndex];
      radarOverlay.setAttribute("href", `${frame.imageUrl}?area=${encodeURIComponent(areaSelect.value)}`);
      timeLabel.textContent = formatFrameTime(frame);
    }

    function stopPlayback() {
      if (playbackTimer) window.clearInterval(playbackTimer);
      playbackTimer = null;
      playButton.textContent = "▶";
      playButton.setAttribute("aria-label", "Reproducir secuencia");
    }

    function togglePlayback() {
      if (!frames.length) return;
      if (playbackTimer) {
        stopPlayback();
        return;
      }
      playButton.textContent = "❚❚";
      playButton.setAttribute("aria-label", "Pausar secuencia");
      playbackTimer = window.setInterval(() => showFrame(frameIndex + 1), 800);
    }

    async function loadFrames() {
      try {
        const response = await fetch("/api/radar-caxx/frames", { cache: "no-store" });
        if (!response.ok) throw new Error("Radar no disponible");
        const payload = await response.json();
        const latestId = frames[frameIndex]?.id;
        availableFrames = (payload.frames || []).slice(-49);
        applyFrameLimit(latestId);
      } catch (_error) {
        timeLabel.textContent = "Radar temporalmente no disponible";
      }
    }

    previousButton.addEventListener("click", () => { stopPlayback(); showFrame(frameIndex - 1); });
    playButton.addEventListener("click", togglePlayback);
    nextButton.addEventListener("click", () => { stopPlayback(); showFrame(frameIndex + 1); });
    exportButton.addEventListener("click", exportVideo);
    areaSelect.addEventListener("change", () => {
      localStorage.setItem("agender.radar-caxx.area", areaSelect.value);
      showSelectedArea();
    });
    frameCountSelect.addEventListener("change", () => {
      stopPlayback();
      localStorage.setItem("agender.radar-caxx.frames", frameCountSelect.value);
      applyFrameLimit();
    });
    previousButton.disabled = true;
    playButton.disabled = true;
    nextButton.disabled = true;
    exportButton.disabled = true;
    loadFrames();
    window.setInterval(loadFrames, 60_000);
  }

  window.NotasRadarCaxx = { init };
})();
