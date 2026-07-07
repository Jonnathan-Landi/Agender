(function () {
  const { escapeHtml } = window.NotasUtils;
  let geoProjector = null;
  let subcuencasLayer = null;
  let hydrometMapPoints = null;
  let basinMap = null;
  const baseView = { x: 0, y: 0, width: 900, height: 620 };
  let currentView = { ...baseView };
  let panStart = null;
  let visibleStations = [];
  let selectedStationCode = "";

  function initHydrometMap() {
    subcuencasLayer = document.querySelector("#subcuencas-layer");
    hydrometMapPoints = document.querySelector("#hydromet-map-points");
    basinMap = document.querySelector(".basin-map");
    bindMapNavigation();
    renderSubcuencas();
  }

  function bindMapNavigation() {
    document.querySelector("#map-zoom-in").addEventListener("click", () => {
      zoomAt(0.78, viewCenter());
    });
    document.querySelector("#map-reset-view").addEventListener("click", resetMapView);
    basinMap.addEventListener("wheel", handleMapWheel, { passive: false });
    basinMap.addEventListener("pointerdown", startMapPan);
    basinMap.addEventListener("pointermove", moveMapPan);
    basinMap.addEventListener("pointerup", endMapPan);
    basinMap.addEventListener("pointercancel", endMapPan);
    hydrometMapPoints.addEventListener("click", activateStationCluster);
    hydrometMapPoints.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      activateStationCluster(event);
    });
  }

  function handleMapWheel(event) {
    event.preventDefault();
    zoomAt(event.deltaY < 0 ? 0.84 : 1.16, clientToMapPoint(event.clientX, event.clientY));
  }

  function startMapPan(event) {
    if (event.button !== 0 || event.target.closest(".station-point, .station-cluster")) return;
    panStart = {
      clientX: event.clientX,
      clientY: event.clientY,
      view: { ...currentView }
    };
    basinMap.classList.add("panning");
    basinMap.setPointerCapture(event.pointerId);
  }

  function moveMapPan(event) {
    if (!panStart || !basinMap.hasPointerCapture(event.pointerId)) return;
    const rect = basinMap.getBoundingClientRect();
    const x = panStart.view.x - (event.clientX - panStart.clientX) * panStart.view.width / rect.width;
    const y = panStart.view.y - (event.clientY - panStart.clientY) * panStart.view.height / rect.height;
    setMapView({ ...panStart.view, x, y });
  }

  function endMapPan(event) {
    if (!panStart) return;
    if (basinMap.hasPointerCapture(event.pointerId)) basinMap.releasePointerCapture(event.pointerId);
    panStart = null;
    basinMap.classList.remove("panning");
  }

  function zoomAt(factor, anchor) {
    const width = Math.min(baseView.width, Math.max(180, currentView.width * factor));
    const height = width * baseView.height / baseView.width;
    const widthRatio = width / currentView.width;
    const heightRatio = height / currentView.height;
    setMapView({
      x: anchor.x - (anchor.x - currentView.x) * widthRatio,
      y: anchor.y - (anchor.y - currentView.y) * heightRatio,
      width,
      height
    });
  }

  function resetMapView() {
    setMapView({ ...baseView });
  }

  function setMapView(view) {
    currentView = {
      x: Math.min(baseView.width - view.width, Math.max(baseView.x, view.x)),
      y: Math.min(baseView.height - view.height, Math.max(baseView.y, view.y)),
      width: view.width,
      height: view.height
    };
    basinMap.setAttribute("viewBox", `${currentView.x} ${currentView.y} ${currentView.width} ${currentView.height}`);
    basinMap.classList.toggle("show-station-labels", currentView.width <= 560);
    drawStationPoints();
  }

  function activateStationCluster(event) {
    const cluster = event.target.closest(".station-cluster");
    if (!cluster) return;
    event.preventDefault();
    event.stopPropagation();
    zoomAt(0.58, {
      x: Number(cluster.dataset.clusterX),
      y: Number(cluster.dataset.clusterY)
    });
  }

  function clientToMapPoint(clientX, clientY) {
    const point = basinMap.createSVGPoint();
    point.x = clientX;
    point.y = clientY;
    const matrix = basinMap.getScreenCTM();
    return matrix ? point.matrixTransform(matrix.inverse()) : viewCenter();
  }

  function viewCenter() {
    return {
      x: currentView.x + currentView.width / 2,
      y: currentView.y + currentView.height / 2
    };
  }

  function renderSubcuencas() {
    const geojson = window.SUBCUENCAS_GEOJSON;
    if (!geojson || !Array.isArray(geojson.features)) {
      subcuencasLayer.innerHTML = `<text x="40" y="80" class="map-message">No se encontraron datos de subcuencas</text>`;
      return;
    }

    geoProjector = createProjector(geojson);
    subcuencasLayer.innerHTML = geojson.features.map((feature, index) => {
      const label = feature.properties && (feature.properties.Subcuenca || feature.properties.CODIGO || `Subcuenca ${index + 1}`);
      const basinKey = normalizeBasinName(label);
      return geometryToPaths(feature.geometry).map((ringSet) => {
        const d = ringSet.map((ring) => ringToPath(ring)).join(" ");
        return `<path class="basin-shape" data-basin="${escapeHtml(basinKey)}" d="${d}"><title>${escapeHtml(label)}</title></path>`;
      }).join("");
    }).join("");
  }

  function setVisibleBasins(basins) {
    const selected = basins === null
      ? null
      : new Set([...basins].map(normalizeBasinName));
    subcuencasLayer.querySelectorAll(".basin-shape").forEach((shape) => {
      shape.classList.toggle("filtered-out", selected !== null && !selected.has(shape.dataset.basin));
    });
  }

  function normalizeBasinName(value) {
    return String(value || "")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .trim()
      .toLowerCase();
  }

  function renderStationPoints(stations, selectedCode) {
    visibleStations = stations;
    selectedStationCode = selectedCode;
    drawStationPoints();
  }

  function drawStationPoints() {
    if (!hydrometMapPoints || !geoProjector) return;
    const projected = visibleStations.map((station) => ({
      station,
      point: projectUtm(station.x, station.y),
      kind: getStationKind(station)
    }));
    const threshold = 22 * currentView.width / baseView.width;
    const clusters = [];

    projected.forEach((item) => {
      if (item.station.code === selectedStationCode) {
        clusters.push({ x: item.point.x, y: item.point.y, members: [item], selected: true });
        return;
      }
      const cluster = clusters.find((candidate) =>
        !candidate.selected && Math.hypot(candidate.x - item.point.x, candidate.y - item.point.y) <= threshold);
      if (!cluster) {
        clusters.push({ x: item.point.x, y: item.point.y, members: [item], selected: false });
        return;
      }
      cluster.members.push(item);
      cluster.x = cluster.members.reduce((sum, member) => sum + member.point.x, 0) / cluster.members.length;
      cluster.y = cluster.members.reduce((sum, member) => sum + member.point.y, 0) / cluster.members.length;
    });

    hydrometMapPoints.innerHTML = clusters.map((cluster) => {
      if (cluster.members.length === 1) return stationPointTemplate(cluster.members[0], cluster.selected);
      return currentView.width <= 360 ? spiderClusterTemplate(cluster) : clusterTemplate(cluster);
    }).join("");
  }

  function stationPointTemplate(item, selected) {
    const scale = currentView.width / baseView.width;
    const poleTop = item.point.y - 22 * scale;
    const flagBottom = item.point.y - 9 * scale;
    const flagTipX = item.point.x - 17 * scale;
    const letter = getStationLetter(item.kind);
    const fontSize = (letter.length > 1 ? 6.3 : 8.5) * scale;
    return `
      <g class="station-point ${item.kind}${selected ? " selected" : ""}" data-code="${escapeHtml(item.station.code)}" tabindex="0">
        <title>${escapeHtml(item.station.code)}</title>
        <circle class="station-hit-area" cx="${item.point.x}" cy="${item.point.y - 11 * scale}" r="${14 * scale}"></circle>
        <line class="station-flag-pole" x1="${item.point.x}" y1="${item.point.y}" x2="${item.point.x}" y2="${poleTop}" vector-effect="non-scaling-stroke"></line>
        <path class="station-flag-shape" d="M ${item.point.x} ${poleTop} L ${flagTipX} ${item.point.y - 15.5 * scale} L ${item.point.x} ${flagBottom} Z" vector-effect="non-scaling-stroke"></path>
        <text class="station-flag-letter" x="${item.point.x - 5.6 * scale}" y="${item.point.y - 13 * scale}" style="font-size:${fontSize}px" text-anchor="middle">${letter}</text>
      </g>
    `;
  }

  function clusterTemplate(cluster) {
    const scale = currentView.width / baseView.width;
    const stationNames = cluster.members.map((item) => item.station.code).join(", ");
    return `
      <g class="station-cluster" data-cluster-x="${cluster.x}" data-cluster-y="${cluster.y}" tabindex="0">
        <title>${escapeHtml(`${cluster.members.length} estaciones: ${stationNames}`)}</title>
        <circle class="cluster-halo" cx="${cluster.x}" cy="${cluster.y}" r="${10 * scale}" vector-effect="non-scaling-stroke"></circle>
        <circle class="cluster-core" cx="${cluster.x}" cy="${cluster.y}" r="${7 * scale}" vector-effect="non-scaling-stroke"></circle>
        <text x="${cluster.x}" y="${cluster.y + 3 * scale}" style="font-size:${8 * scale}px" text-anchor="middle">${cluster.members.length}</text>
      </g>
    `;
  }

  function spiderClusterTemplate(cluster) {
    const scale = currentView.width / baseView.width;
    const radius = 30 * scale;
    const positions = cluster.members.map((member, index) => {
      const angle = -Math.PI / 2 + index * Math.PI * 2 / cluster.members.length;
      return {
        member,
        point: {
          x: cluster.x + Math.cos(angle) * radius,
          y: cluster.y + Math.sin(angle) * radius
        }
      };
    });
    const lines = positions.map(({ point }) => `
      <line class="station-spider-line" x1="${cluster.x}" y1="${cluster.y}" x2="${point.x}" y2="${point.y}" vector-effect="non-scaling-stroke"></line>
    `).join("");
    const points = positions.map(({ member, point }) =>
      stationPointTemplate({ ...member, point }, member.station.code === selectedStationCode)
    ).join("");
    return `<g class="station-spider">${lines}${points}</g>`;
  }

  function getStationKind(station) {
    const prefix = String(station.code || "").split("_")[0].toLowerCase();
    if (["met", "lim", "plu", "mli", "lpl"].includes(prefix)) return prefix;
    const type = String(station.type || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
    if (type.includes("meteorologica") && type.includes("limni")) return "mli";
    if (type.includes("pluvio") && type.includes("limni")) return "lpl";
    if (type.includes("meteorologica")) return "met";
    if (type.includes("pluvio")) return "plu";
    return "lim";
  }

  function getStationLetter(kind) {
    return ({ met: "M", lim: "L", plu: "P", mli: "ML", lpl: "LP" })[kind] || "E";
  }

  function createProjector(geojson) {
    const bbox = getGeojsonBbox(geojson);
    const width = 900;
    const height = 620;
    const padding = 34;
    const scale = Math.min((width - padding * 2) / (bbox.maxX - bbox.minX), (height - padding * 2) / (bbox.maxY - bbox.minY));
    const drawnWidth = (bbox.maxX - bbox.minX) * scale;
    const drawnHeight = (bbox.maxY - bbox.minY) * scale;
    const offsetX = (width - drawnWidth) / 2;
    const offsetY = (height - drawnHeight) / 2;

    return (x, y) => ({
      x: offsetX + (Number(x) - bbox.minX) * scale,
      y: offsetY + (bbox.maxY - Number(y)) * scale
    });
  }

  function projectUtm(x, y) {
    if (!geoProjector) return { x: 0, y: 0 };
    return geoProjector(x, y);
  }

  function getGeojsonBbox(geojson) {
    const bbox = { minX: Infinity, minY: Infinity, maxX: -Infinity, maxY: -Infinity };
    geojson.features.forEach((feature) => walkCoordinates(feature.geometry.coordinates, (coord) => {
      bbox.minX = Math.min(bbox.minX, coord[0]);
      bbox.maxX = Math.max(bbox.maxX, coord[0]);
      bbox.minY = Math.min(bbox.minY, coord[1]);
      bbox.maxY = Math.max(bbox.maxY, coord[1]);
    }));
    return bbox;
  }

  function walkCoordinates(coordinates, callback) {
    if (typeof coordinates[0] === "number") {
      callback(coordinates);
      return;
    }
    coordinates.forEach((child) => walkCoordinates(child, callback));
  }

  function geometryToPaths(geometry) {
    if (geometry.type === "Polygon") return [geometry.coordinates];
    if (geometry.type === "MultiPolygon") return geometry.coordinates;
    return [];
  }

  function ringToPath(ring) {
    return ring.map((coord, index) => {
      const point = projectUtm(coord[0], coord[1]);
      return `${index === 0 ? "M" : "L"}${point.x.toFixed(2)} ${point.y.toFixed(2)}`;
    }).join(" ") + " Z";
  }

  window.NotasHydrometMap = {
    initHydrometMap,
    renderStationPoints,
    setVisibleBasins
  };
})();
