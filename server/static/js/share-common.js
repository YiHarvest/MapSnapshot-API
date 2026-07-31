(function initializeMapSnapshotShare(global) {
  "use strict";

  const loadedGeoJson = new Map();

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function loadMapPlugins(timeoutMs) {
    return new Promise((resolve, reject) => {
      let settled = false;
      const timeout = global.setTimeout(() => {
        if (settled) {
          return;
        }
        settled = true;
        if (global.AMap.Scale) {
          console.warn("AMap plugin callback timeout, using detected plugins");
          resolve();
          return;
        }
        reject(new Error("AMap plugin load timeout"));
      }, timeoutMs);

      global.AMap.plugin(["AMap.Scale"], () => {
        if (settled) {
          return;
        }
        settled = true;
        global.clearTimeout(timeout);
        if (!global.AMap.Scale) {
          reject(new Error("AMap.Scale plugin load failed"));
          return;
        }
        resolve();
      });
    });
  }

  async function loadGeoJson(path) {
    if (!path) {
      return null;
    }
    if (loadedGeoJson.has(path)) {
      return loadedGeoJson.get(path);
    }
    const response = await global.fetch(path);
    if (!response.ok) {
      loadedGeoJson.set(path, null);
      return null;
    }
    const geojson = await response.json();
    loadedGeoJson.set(path, geojson);
    return geojson;
  }

  async function loadGeoJsonEntries(paths) {
    const uniquePaths = Array.from(new Set(paths.filter(Boolean)));
    const entries = await Promise.all(
      uniquePaths.map(async (path) => [path, await loadGeoJson(path)])
    );
    return new Map(entries);
  }

  function normalizePolygonPaths(geometry) {
    if (!geometry || !Array.isArray(geometry.coordinates)) {
      return [];
    }
    if (geometry.type === "Polygon") {
      return geometry.coordinates;
    }
    if (geometry.type === "MultiPolygon") {
      return geometry.coordinates.flat();
    }
    return [];
  }

  function normalizePolygonParts(geometry) {
    if (!geometry || !Array.isArray(geometry.coordinates)) {
      return [];
    }
    if (geometry.type === "Polygon") {
      return [geometry.coordinates];
    }
    if (geometry.type === "MultiPolygon") {
      return geometry.coordinates;
    }
    return [];
  }

  function findFeatureByAdcode(geojson, adcode) {
    if (!geojson || !Array.isArray(geojson.features) || !adcode) {
      return null;
    }
    const normalizedAdcode = String(adcode);
    return (
      geojson.features.find((feature) => {
        const properties = feature.properties || {};
        return String(properties.adcode || "") === normalizedAdcode;
      }) || null
    );
  }

  function getFeatureCenterFromGeometry(feature) {
    if (!feature || !feature.geometry) {
      return null;
    }
    const rings = normalizePolygonPaths(feature.geometry);
    if (!rings.length) {
      return null;
    }
    let minLng = Number.POSITIVE_INFINITY;
    let minLat = Number.POSITIVE_INFINITY;
    let maxLng = Number.NEGATIVE_INFINITY;
    let maxLat = Number.NEGATIVE_INFINITY;
    for (const ring of rings) {
      for (const point of ring) {
        const lng = Number(point?.[0]);
        const lat = Number(point?.[1]);
        if (!Number.isFinite(lng) || !Number.isFinite(lat)) {
          continue;
        }
        minLng = Math.min(minLng, lng);
        minLat = Math.min(minLat, lat);
        maxLng = Math.max(maxLng, lng);
        maxLat = Math.max(maxLat, lat);
      }
    }
    if (!Number.isFinite(minLng) || !Number.isFinite(minLat)) {
      return null;
    }
    return [(minLng + maxLng) / 2, (minLat + maxLat) / 2];
  }

  function collectFeatureRings(geojson, shouldCollect) {
    if (!geojson || !Array.isArray(geojson.features)) {
      return [];
    }
    return geojson.features.flatMap((feature) => {
      if (!feature || typeof feature !== "object") {
        return [];
      }
      const properties = feature.properties || {};
      return shouldCollect(feature, properties)
        ? normalizePolygonPaths(feature.geometry)
        : [];
    });
  }

  function pointInRing(point, ring) {
    if (!Array.isArray(ring) || ring.length < 3) {
      return false;
    }

    const [lng, lat] = point;
    let inside = false;
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      const xi = Number(ring[i][0]);
      const yi = Number(ring[i][1]);
      const xj = Number(ring[j][0]);
      const yj = Number(ring[j][1]);
      if (![xi, yi, xj, yj].every(Number.isFinite)) {
        continue;
      }
      const intersects =
        yi > lat !== yj > lat &&
        lng < ((xj - xi) * (lat - yi)) / (yj - yi) + xi;
      if (intersects) {
        inside = !inside;
      }
    }
    return inside;
  }

  function featureContainsPoint(feature, point) {
    return normalizePolygonParts(feature.geometry).some((rings) => {
      if (
        !Array.isArray(rings) ||
        !rings.length ||
        !pointInRing(point, rings[0])
      ) {
        return false;
      }
      return !rings.slice(1).some((hole) => pointInRing(point, hole));
    });
  }

  function findFeatureAtPoint(geojson, point, level) {
    if (!geojson || !Array.isArray(geojson.features) || !point) {
      return null;
    }
    return (
      geojson.features.find((feature) => {
        const properties = feature.properties || {};
        const adcode = String(properties.adcode || "");
        return (
          adcode &&
          adcode !== "100000" &&
          (!level || String(properties.level || "") === level) &&
          featureContainsPoint(feature, point)
        );
      }) || null
    );
  }

  function getFeatureDisplayName(properties, fallbackAdcode) {
    return String(
      properties.name ||
        properties.adname ||
        properties.fullname ||
        properties.cityname ||
        fallbackAdcode ||
        ""
    ).trim();
  }

  function getLngLatPair(lnglat) {
    if (!lnglat) {
      return null;
    }
    const lng = Number(
      typeof lnglat.getLng === "function"
        ? lnglat.getLng()
        : lnglat.lng ?? lnglat[0]
    );
    const lat = Number(
      typeof lnglat.getLat === "function"
        ? lnglat.getLat()
        : lnglat.lat ?? lnglat[1]
    );
    return Number.isFinite(lng) && Number.isFinite(lat) ? [lng, lat] : null;
  }

  function getDomEventLngLat(map, event) {
    const container =
      map && typeof map.getContainer === "function" ? map.getContainer() : null;
    if (
      !container ||
      !event ||
      typeof map.containerToLngLat !== "function"
    ) {
      return null;
    }
    const rect = container.getBoundingClientRect();
    const x = Number(event.clientX) - rect.left;
    const y = Number(event.clientY) - rect.top;
    if (!Number.isFinite(x) || !Number.isFinite(y)) {
      return null;
    }
    return map.containerToLngLat(new global.AMap.Pixel(x, y));
  }

  function bindTouchTap(container, onTap) {
    if (!container || typeof global.PointerEvent === "undefined") {
      return;
    }
    let candidate = null;
    container.addEventListener(
      "pointerdown",
      (event) => {
        if (
          !event ||
          event.pointerType === "mouse" ||
          event.isPrimary === false
        ) {
          return;
        }
        candidate = {
          id: event.pointerId,
          x: Number(event.clientX),
          y: Number(event.clientY),
          time: Date.now(),
        };
      },
      { passive: true }
    );
    container.addEventListener(
      "pointercancel",
      () => {
        candidate = null;
      },
      { passive: true }
    );
    container.addEventListener(
      "pointerup",
      (event) => {
        if (!candidate || !event || event.pointerId !== candidate.id) {
          candidate = null;
          return;
        }
        const dx = Number(event.clientX) - candidate.x;
        const dy = Number(event.clientY) - candidate.y;
        const elapsed = Date.now() - candidate.time;
        candidate = null;
        if (Math.hypot(dx, dy) <= 12 && elapsed <= 800) {
          onTap(event);
        }
      },
      { passive: true }
    );
  }

  function waitForMapFrame() {
    return new Promise((resolve) => {
      global.requestAnimationFrame(() => {
        global.requestAnimationFrame(resolve);
      });
    });
  }

  global.MapSnapshotShare = Object.freeze({
    bindTouchTap,
    collectFeatureRings,
    escapeHtml,
    featureContainsPoint,
    findFeatureByAdcode,
    findFeatureAtPoint,
    getFeatureDisplayName,
    getFeatureCenterFromGeometry,
    getDomEventLngLat,
    getLngLatPair,
    loadGeoJson,
    loadGeoJsonEntries,
    loadMapPlugins,
    normalizePolygonParts,
    normalizePolygonPaths,
    pointInRing,
    waitForMapFrame,
  });
})(window);
