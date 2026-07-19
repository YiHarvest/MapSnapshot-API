/** 区域层级枚举：全国 / 省级 / 市级 / 区县级 */
export type RegionLevel = 'country' | 'province' | 'city' | 'district';

/** 区域层级中文标签 */
export type RegionLevelLabel = '全国' | '省级' | '市级' | '区县级';

/** 地图展示级别：全国 / 省份展开 / 直辖市展开 / 城市展开 */
export type MapLevel = 'country' | 'provinceExpanded' | 'municipalityExpanded' | 'cityExpanded';

/** 比例尺标签，根据缩放级别动态变化 */
export type ScaleLabel =
  | '500km'
  | '500 km'
  | '300 km'
  | '200 km'
  | '100km'
  | '100 km'
  | '50 km'
  | '30km'
  | '30 km'
  | '20 km'
  | '10 km';

/** 区域信息展示数据 */
export interface RegionInfo {
  /** 区域名称 */
  name: string;
  /** 浏览次数（格式化后的字符串） */
  visits: string;
  /** 区域层级中文标签 */
  level: RegionLevelLabel;
  /** 提示文字 */
  hint?: string;
  /** 行政区划代码 */
  adcode?: string;
  /** 地图层级标签 */
  mapLabel?: string;
}

/** 用户选中的区域信息 */
export interface RegionSelection {
  /** 区域名称 */
  name: string;
  /** 行政区划代码 */
  adcode?: string;
  /** 区域层级 */
  level: RegionLevel;
}

/** 区域访问记录 */
export interface RegionVisitRecord {
  /** 行政区划代码 */
  code: string;
  /** 区域名称 */
  name: string;
  /** 访问次数 */
  visits: number;
  /** 区域层级 */
  level: RegionLevel;
}

/** GeoJSON 要素 */
export interface GeoJsonFeature {
  type?: string;
  properties?: {
    name?: string;
    adcode?: string | number;
    level?: string;
    center?: [number, number];
    centroid?: [number, number];
    parent?: { adcode?: number };
    acroutes?: Array<number | string>;
  };
  geometry?: {
    type?: string;
    coordinates?: unknown;
  };
}

/** GeoJSON FeatureCollection 类型 */
export interface GeoJsonFeatureCollection {
  type: 'FeatureCollection';
  features: GeoJsonFeature[];
}

/** 地图状态 */
export interface MapState {
  /** 当前地图展示级别 */
  level: MapLevel;
  /** 地图标识名称 */
  mapName: string;
  /** 当前比例尺标签 */
  scaleLabel: ScaleLabel;
  /** 地图层级标签 */
  mapLabel: string;
  /** GeoJSON 文件路径 */
  geoJsonPath?: string;
}

/** 省份下钻地图配置 */
export interface ProvinceMapConfig {
  /** 省份名称 */
  name: string;
  /** 行政区划代码 */
  adcode: string;
  /** 是否为直辖市（北京/天津/上海/重庆） */
  isMunicipality: boolean;
  /** 该省份 GeoJSON 文件路径 */
  geoJsonPath: string;
  /** 省份视图比例尺标签 */
  scaleLabel: ScaleLabel;
  /** 地图层级标签 */
  mapLabel: string;
}
