import json
import subprocess
from pathlib import Path

SHARE_COMMON_JS = (
    Path(__file__).resolve().parents[2] / "server" / "static" / "js" / "share-common.js"
)


def test_share_common_provides_geojson_and_geometry_helpers() -> None:
    script = """
const fs = require("node:fs");
const vm = require("node:vm");

let fetchCount = 0;
let frameCount = 0;
const browserFetch = async (path) => {
  fetchCount += 1;
  return {
    ok: true,
    json: async () => ({ path }),
  };
};
const context = {
  console,
  window: {
    AMap: {
      Pixel: class {
        constructor(x, y) {
          this.x = x;
          this.y = y;
        }
      },
    },
    PointerEvent: class {},
    clearTimeout,
    fetch: browserFetch,
    requestAnimationFrame: (callback) => {
      frameCount += 1;
      callback();
    },
    setTimeout,
  },
};
vm.runInNewContext(fs.readFileSync(process.argv[1], "utf8"), context);

(async () => {
  const helpers = context.window.MapSnapshotShare;
  const polygon = {
    type: "Polygon",
    coordinates: [[[0, 1], [4, 1], [4, 5], [0, 5]]],
  };
  const feature = {
    geometry: polygon,
    properties: { adcode: "110000" },
  };
  const geojson = { features: [feature] };

  await helpers.loadGeoJson("/province.json");
  await helpers.loadGeoJson("/province.json");
  await helpers.waitForMapFrame();

  const listeners = {};
  const container = {
    addEventListener: (type, callback) => {
      listeners[type] = callback;
    },
  };
  let tapCount = 0;
  helpers.bindTouchTap(container, () => {
    tapCount += 1;
  });
  listeners.pointerdown({
    clientX: 10,
    clientY: 20,
    isPrimary: true,
    pointerId: 7,
    pointerType: "touch",
  });
  listeners.pointerup({
    clientX: 11,
    clientY: 21,
    pointerId: 7,
  });

  const lngLat = helpers.getDomEventLngLat(
    {
      containerToLngLat: (pixel) => [pixel.x, pixel.y],
      getContainer: () => ({
        getBoundingClientRect: () => ({ left: 10, top: 20 }),
      }),
    },
    { clientX: 15, clientY: 25 }
  );

  process.stdout.write(JSON.stringify({
    center: helpers.getFeatureCenterFromGeometry(feature),
    collectedPaths: helpers.collectFeatureRings(
      geojson,
      () => true
    ),
    containsPoint: helpers.featureContainsPoint(feature, [2, 3]),
    displayName: helpers.getFeatureDisplayName(
      { name: "", adname: "北京市" },
      "110000"
    ),
    found: helpers.findFeatureByAdcode(geojson, "110000") === feature,
    foundAtPoint: helpers.findFeatureAtPoint(
      geojson,
      [2, 3],
      ""
    ) === feature,
    frameCount,
    lngLatFromEvent: lngLat,
    lngLat: helpers.getLngLatPair({
      getLng: () => 116.4,
      getLat: () => 39.9,
    }),
    parts: helpers.normalizePolygonParts(polygon),
    paths: helpers.normalizePolygonPaths(polygon),
    tapCount,
    fetchCount,
  }));
})();
"""
    result = subprocess.run(
        ["node", "-e", script, str(SHARE_COMMON_JS)],
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(result.stdout) == {
        "center": [2, 3],
        "collectedPaths": [[[0, 1], [4, 1], [4, 5], [0, 5]]],
        "containsPoint": True,
        "displayName": "北京市",
        "found": True,
        "foundAtPoint": True,
        "frameCount": 2,
        "lngLatFromEvent": [5, 5],
        "lngLat": [116.4, 39.9],
        "parts": [[[[0, 1], [4, 1], [4, 5], [0, 5]]]],
        "paths": [[[0, 1], [4, 1], [4, 5], [0, 5]]],
        "tapCount": 1,
        "fetchCount": 1,
    }
