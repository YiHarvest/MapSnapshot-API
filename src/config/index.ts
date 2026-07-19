/** 前端全局配置：集中管理所有硬编码常量，便于维护和调整 */

// ============================================================
// 地图默认参数
// ============================================================

/** 地图默认中心点坐标（中国大致中心） */
export const DEFAULT_CENTER: [number, number] = [104.195397, 35.86166];

/** 全国视图默认缩放级别 */
export const DEFAULT_ZOOM = 4;

/** 地图缩放范围 [最小, 最大] */
export const DEFAULT_ZOOMS: [number, number] = [3, 18];

/** 下钻阈值：缩放超过此级别后自动展开省/市数据 */
export const DRILL_ZOOM_THRESHOLD = 6;

// ============================================================
// 高德地图加载参数
// ============================================================

/** 高德地图 JSAPI 版本 */
export const AMAP_VERSION = '2.0';

/** 高德地图插件列表 */
export const AMAP_PLUGINS: string[] = ['AMap.ToolBar', 'AMap.Scale'];

/** 高德地图样式 URL */
export const AMAP_STYLE = 'amap://styles/normal';

// ============================================================
// 区域多边形样式
// ============================================================

/** 多边形描边颜色 */
export const POLYGON_STROKE_COLOR = '#1E90FF';

/** 多边形填充颜色 */
export const POLYGON_FILL_COLOR = '#3BA7FF';

/** 默认状态样式 */
export const POLYGON_BASE_STYLE = {
  strokeColor: '#1E90FF',
  strokeOpacity: 0.45,
  strokeWeight: 1,
  fillColor: '#3BA7FF',
  fillOpacity: 0.04,
  zIndex: 20,
} as const;

/** 悬停状态样式 */
export const POLYGON_HOVER_STYLE = {
  strokeColor: '#1E90FF',
  strokeOpacity: 0.9,
  strokeWeight: 1.8,
  fillColor: '#3BA7FF',
  fillOpacity: 0.16,
  zIndex: 30,
} as const;

/** 选中状态样式 */
export const POLYGON_SELECTED_STYLE = {
  strokeColor: '#1E90FF',
  strokeOpacity: 0.92,
  strokeWeight: 2,
  fillColor: '#3BA7FF',
  fillOpacity: 0.2,
  zIndex: 40,
} as const;

// ============================================================
// 地图控件位置
// ============================================================

/** 工具条位置（右下角） */
export const TOOLBAR_POSITION = 'RB';

/** 比例尺位置（左下角） */
export const SCALE_POSITION = 'LB';

// ============================================================
// 地图交互选项
// ============================================================

export const MAP_OPTIONS = {
  viewMode: '2D' as const,
  dragEnable: true,
  zoomEnable: true,
  doubleClickZoom: true,
  touchZoom: true,
  keyboardEnable: true,
  resizeEnable: true,
  mapStyle: 'amap://styles/normal',
} as const;

// ============================================================
// GeoJSON 路径常量
// ============================================================

/** 全国 GeoJSON 路径 */
export const CHINA_GEOJSON_PATH = '/geojson/china.json';

/** 省份 GeoJSON 目录前缀 */
export const PROVINCE_GEOJSON_PREFIX = '/geojson/province';

// ============================================================
// 缩放比例尺标签映射
// ============================================================

/** 地图缩放级别对应的比例尺标签 */
export const ZOOM_SCALE_LABELS: Record<number, string> = {
  13: '10 km',
  11: '20 km',
  9: '30 km',
  8: '50 km',
  7: '100 km',
  6: '200 km',
  5: '300 km',
  0: '500 km',
};

// ============================================================
// 提示文案
// ============================================================

/** 高德 Key 缺失提示 */
export const MSG_MISSING_AMAP_KEY = '缺少 VITE_AMAP_KEY，请在 .env 中配置高德 Web端(JS API) Key';

/** 地图加载失败前缀 */
export const MSG_MAP_LOAD_FAILED = '高德地图加载失败';

/** 区域数据未配置提示 */
export const MSG_REGION_NOT_CONFIGURED = '该地区数据暂未配置';

/** 全国默认区域名称 */
export const DEFAULT_REGION_NAME = '全国';
