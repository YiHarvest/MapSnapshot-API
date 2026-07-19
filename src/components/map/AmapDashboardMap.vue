<template>
  <!-- 高德地图容器 -->
  <div ref="mapRef" class="amap-dashboard-map"></div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue';
import AMapLoader from '@amap/amap-jsapi-loader';
import { loadGeoJson } from '@/api/region';
import { getProvinceMapByAdcode, getProvinceMapByName } from '@/constants/region';
import { getFeatureAtPoint } from '@/utils/geojson';
import {
  CHINA_GEOJSON_PATH,
  DEFAULT_CENTER,
  DEFAULT_ZOOM,
  DEFAULT_ZOOMS,
  DRILL_ZOOM_THRESHOLD,
  AMAP_VERSION,
  AMAP_PLUGINS,
  AMAP_STYLE,
  MAP_OPTIONS,
  POLYGON_BASE_STYLE,
  POLYGON_HOVER_STYLE,
  POLYGON_SELECTED_STYLE,
  TOOLBAR_POSITION,
  SCALE_POSITION,
  ZOOM_SCALE_LABELS,
  MSG_MISSING_AMAP_KEY,
  MSG_MAP_LOAD_FAILED,
} from '@/config';
import type { GeoJsonFeature, GeoJsonFeatureCollection, RegionSelection } from '@/types/region';

/** 高德地图命名空间（动态加载，类型宽松） */
type AMapNamespace = any;
/** 区域多边形实例（AMap.Polygon + 自定义属性） */
type RegionPolygon = any & {
  __regionName?: string;
  __regionAdcode?: string;
  __regionLevel?: RegionSelection['level'];
};

// ============================================================
// 全局状态变量
// ============================================================

/** 地图容器 DOM 引用 */
const mapRef = ref<HTMLDivElement | null>(null);
/** 高德地图命名空间引用 */
let amap: AMapNamespace | null = null;
/** 地图实例 */
let map: any | null = null;
/** 当前渲染的多边形数组 */
let polygons: RegionPolygon[] = [];
/** 全国 GeoJSON 数据缓存 */
let chinaGeoJson: GeoJsonFeatureCollection | null = null;
/** 当前覆盖层标识（'country' 或省份 adcode） */
let currentOverlayKey = '';
/** 当前选中的区域名称 */
let selectedRegionName = '';

// ============================================================
// 事件定义
// ============================================================

const emit = defineEmits<{
  /** 用户点击区域 */
  (event: 'region-click', region: RegionSelection): void;
  /** 地图或数据加载出错 */
  (event: 'load-error', message: string): void;
}>();

// ============================================================
// 工具函数
// ============================================================

/**
 * 将 GeoJSON level 字段转换为区域层级
 * 未知层级默认为省级
 */
function toRegionLevel(level?: string): RegionSelection['level'] {
  if (level === 'city' || level === 'district') {
    return level;
  }

  return 'province';
}

// ============================================================
// 多边形样式
// ============================================================

/** 多边形的默认样式 */
function getBaseStyle(): Record<string, unknown> {
  return { ...POLYGON_BASE_STYLE };
}

/** 鼠标悬停时的高亮样式 */
function getHoverStyle(): Record<string, unknown> {
  return { ...POLYGON_HOVER_STYLE };
}

/** 选中区域的强调样式 */
function getSelectedStyle(): Record<string, unknown> {
  return { ...POLYGON_SELECTED_STYLE };
}

// ============================================================
// 区域样式管理
// ============================================================

/**
 * 对指定区域名称的所有多边形应用样式
 * @param regionName - 区域名称
 * @param style - 要应用的样式对象
 */
function applyPolygonStyle(regionName: string, style: Record<string, unknown>) {
  for (const polygon of polygons) {
    if (polygon.__regionName === regionName) {
      polygon.setOptions(style);
    }
  }
}

/**
 * 重置区域样式：选中区域保持选中样式，其他恢复默认
 * @param regionName - 区域名称
 */
function resetRegionStyle(regionName: string) {
  applyPolygonStyle(regionName, regionName === selectedRegionName ? getSelectedStyle() : getBaseStyle());
}

/**
 * 选中指定区域：取消之前的选中状态，高亮当前区域
 * @param regionName - 要选中的区域名称
 */
function selectRegion(regionName: string) {
  if (selectedRegionName) {
    applyPolygonStyle(selectedRegionName, getBaseStyle());
  }

  selectedRegionName = regionName;
  applyPolygonStyle(regionName, getSelectedStyle());
}

// ============================================================
// GeoJSON 坐标处理
// ============================================================

/**
 * 规范化 Polygon 坐标数组
 * 过滤掉非法坐标，返回合法的环数组
 */
function normalizePolygonCoordinates(coordinates: unknown): Array<Array<[number, number]>> {
  if (!Array.isArray(coordinates)) {
    return [];
  }

  return coordinates
    .filter((ring): ring is Array<[number, number]> => Array.isArray(ring))
    .map((ring) => ring.filter((point): point is [number, number] => Array.isArray(point) && point.length >= 2));
}

/**
 * 从 GeoJSON 要素中提取多边形坐标
 * 支持 Polygon 和 MultiPolygon 两种类型
 */
function getFeaturePolygons(feature: GeoJsonFeature): Array<Array<Array<[number, number]>>> {
  const geometry = feature.geometry;
  if (!geometry) {
    return [];
  }

  if (geometry.type === 'Polygon') {
    const polygon = normalizePolygonCoordinates(geometry.coordinates);
    return polygon.length ? [polygon] : [];
  }

  if (geometry.type === 'MultiPolygon' && Array.isArray(geometry.coordinates)) {
    return geometry.coordinates
      .map((polygon) => normalizePolygonCoordinates(polygon))
      .filter((polygon) => polygon.length > 0);
  }

  return [];
}

// ============================================================
// 多边形事件绑定
// ============================================================

/**
 * 为多边形绑定交互事件（悬停、点击）
 * @param polygon - 多边形实例
 */
function bindPolygonEvents(polygon: RegionPolygon) {
  // 鼠标悬停 → 高亮
  polygon.on('mouseover', () => {
    if (polygon.__regionName && polygon.__regionName !== selectedRegionName) {
      applyPolygonStyle(polygon.__regionName, getHoverStyle());
    }
  });

  // 鼠标移出 → 恢复样式
  polygon.on('mouseout', () => {
    if (polygon.__regionName) {
      resetRegionStyle(polygon.__regionName);
    }
  });

  // 点击 → 选中并通知父组件
  polygon.on('click', () => {
    if (!polygon.__regionName) {
      return;
    }

    selectRegion(polygon.__regionName);
    emit('region-click', {
      name: polygon.__regionName,
      adcode: polygon.__regionAdcode,
      level: polygon.__regionLevel ?? 'province',
    });
  });
}

// ============================================================
// 区域多边形渲染
// ============================================================

/**
 * 根据 GeoJSON 数据在地图上渲染行政区划多边形
 * @param geoJson - 要素集合
 * @param forcedLevel - 可选，强制指定层级（忽略 GeoJSON 中的 level 字段）
 */
function renderAdministrativePolygons(geoJson: GeoJsonFeatureCollection, forcedLevel?: RegionSelection['level']) {
  if (!amap || !map) {
    return;
  }

  // 清除旧的多边形
  map.remove(polygons);
  polygons = [];

  for (const feature of geoJson.features ?? []) {
    const name = feature.properties?.name;
    if (!name) {
      continue;
    }

    const adcode = feature.properties?.adcode ? String(feature.properties.adcode) : undefined;
    const level = forcedLevel ?? toRegionLevel(feature.properties?.level);
    const featurePolygons = getFeaturePolygons(feature);

    // 为每个要素创建多边形（MultiPolygon 可能产生多个）
    for (const path of featurePolygons) {
      const polygon = new amap.Polygon({
        ...getBaseStyle(),
        path,
      }) as RegionPolygon;

      // 附加区域属性到多边形实例
      polygon.__regionName = name;
      polygon.__regionAdcode = adcode;
      polygon.__regionLevel = level;
      bindPolygonEvents(polygon);
      polygons.push(polygon);
    }
  }

  map.add(polygons);
}

// ============================================================
// 下钻覆盖层管理
// ============================================================

/**
 * 获取当前地图视口的中心点坐标
 */
function getMapCenterPoint(): [number, number] {
  const center = map?.getCenter();
  if (!center) {
    return DEFAULT_CENTER;
  }

  return [center.lng, center.lat];
}

/**
 * 根据地图缩放级别和视口位置自动切换展示层级
 * - 缩放 < 6：显示全国省份
 * - 缩放 >= 6：显示当前视口所在省份的市/区县数据
 */
async function updateAdministrativeOverlay() {
  if (!map || !chinaGeoJson) {
    return;
  }

  const zoom = map.getZoom();

  // 缩放级别低于阈值 → 展示全国省份视图
  if (zoom < DRILL_ZOOM_THRESHOLD) {
    if (currentOverlayKey !== 'country') {
      currentOverlayKey = 'country';
      selectedRegionName = '';
      renderAdministrativePolygons(chinaGeoJson, 'province');
    }
    return;
  }

  // 缩放级别达到阈值 → 判断当前视口中心落在哪个省份
  const provinceFeature = getFeatureAtPoint(chinaGeoJson, getMapCenterPoint(), 'province');
  if (!provinceFeature?.properties?.name) {
    return;
  }

  // 根据省份名称或 adcode 查找下钻配置
  const province =
    getProvinceMapByName(provinceFeature.properties.name) ??
    (provinceFeature.properties.adcode ? getProvinceMapByAdcode(String(provinceFeature.properties.adcode)) : null);

  // 省份未配置或已加载 → 跳过
  if (!province || currentOverlayKey === province.adcode) {
    return;
  }

  // 加载省份 GeoJSON 并渲染市/区县多边形
  currentOverlayKey = province.adcode;
  selectedRegionName = '';
  renderAdministrativePolygons(
    (await loadGeoJson(province.geoJsonPath)) as GeoJsonFeatureCollection,
    // 直辖市 → 直接展示区县；普通省份 → 展示市
    province.isMunicipality ? 'district' : 'city',
  );
}

// ============================================================
// 地图初始化
// ============================================================

/**
 * 初始化高德地图实例
 * 1. 读取环境变量中的 Key 和安全密钥
 * 2. 动态加载高德 JSAPI
 * 3. 创建地图实例并加载全国 GeoJSON
 */
async function initMap() {
  const key = import.meta.env.VITE_AMAP_KEY as string | undefined;
  const securityCode = import.meta.env.VITE_AMAP_SECURITY_CODE as string | undefined;

  if (!key) {
    emit('load-error', MSG_MISSING_AMAP_KEY);
    return;
  }

  // 配置高德安全密钥（JSAPI 2.0 新版要求）
  if (securityCode) {
    (window as unknown as { _AMapSecurityConfig?: { securityJsCode: string } })._AMapSecurityConfig = {
      securityJsCode: securityCode,
    };
  }

  try {
    // 动态加载高德 JSAPI
    amap = await AMapLoader.load({
      key,
      version: AMAP_VERSION,
      plugins: AMAP_PLUGINS,
    });

    if (!mapRef.value) {
      return;
    }

    // 创建地图实例
    map = new amap.Map(mapRef.value, {
      center: DEFAULT_CENTER,
      zoom: DEFAULT_ZOOM,
      zooms: DEFAULT_ZOOMS,
      ...MAP_OPTIONS,
    });

    // 添加缩放和比例尺控件
    map.addControl(new amap.ToolBar({ position: TOOLBAR_POSITION }));
    map.addControl(new amap.Scale({ position: SCALE_POSITION }));

    // 缩放/移动结束后自动更新下钻覆盖层
    map.on('zoomend', () => {
      void updateAdministrativeOverlay();
    });
    map.on('moveend', () => {
      void updateAdministrativeOverlay();
    });

    // 加载全国 GeoJSON 并渲染省份多边形
    chinaGeoJson = (await loadGeoJson(CHINA_GEOJSON_PATH)) as GeoJsonFeatureCollection;
    currentOverlayKey = 'country';
    renderAdministrativePolygons(chinaGeoJson, 'province');
  } catch (error) {
    const message = error instanceof Error ? error.message : MSG_MAP_LOAD_FAILED;
    emit('load-error', message);
  }
}

// ============================================================
// 生命周期
// ============================================================

onMounted(() => {
  void initMap();
});

onBeforeUnmount(() => {
  if (map) {
    // 清理所有多边形
    map.remove(polygons);
    polygons = [];
    // 销毁地图实例
    map.destroy();
    map = null;
  }
});
</script>
