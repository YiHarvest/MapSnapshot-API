/**
 * 区域常量与配置
 * - 区域层级中英文标签映射
 * - 34 个省级行政区下钻配置
 * - 区域访问量 Mock 数据
 * - 工具函数（查找省份配置、格式化数字等）
 */
import { CHINA_GEOJSON_PATH, PROVINCE_GEOJSON_PREFIX } from '@/config';
import type { MapState, ProvinceMapConfig, RegionInfo } from '@/types/region';

/** 区域层级中英文标签映射 */
export const REGION_LEVEL_LABELS = {
  country: '全国',
  province: '省级',
  city: '市级',
  district: '区县级',
} as const;

/** 默认区域信息（全国视图初始状态） */
export const DEFAULT_REGION_INFO: RegionInfo = {
  name: '全国',
  visits: '-',
  level: REGION_LEVEL_LABELS.country,
};

/** 全国视图地图状态 */
export const COUNTRY_MAP_STATE: MapState = {
  level: 'country',
  mapName: 'china',
  geoJsonPath: CHINA_GEOJSON_PATH,
  scaleLabel: '500 km',
  mapLabel: '全国地图',
};

/** 34 个省级行政区基础配置：[名称, 行政区划代码, 是否直辖市] */
const PROVINCE_BASE_CONFIGS = [
  ['北京市', '110000', true],
  ['天津市', '120000', true],
  ['河北省', '130000', false],
  ['山西省', '140000', false],
  ['内蒙古自治区', '150000', false],
  ['辽宁省', '210000', false],
  ['吉林省', '220000', false],
  ['黑龙江省', '230000', false],
  ['上海市', '310000', true],
  ['江苏省', '320000', false],
  ['浙江省', '330000', false],
  ['安徽省', '340000', false],
  ['福建省', '350000', false],
  ['江西省', '360000', false],
  ['山东省', '370000', false],
  ['河南省', '410000', false],
  ['湖北省', '420000', false],
  ['湖南省', '430000', false],
  ['广东省', '440000', false],
  ['广西壮族自治区', '450000', false],
  ['海南省', '460000', false],
  ['重庆市', '500000', true],
  ['四川省', '510000', false],
  ['贵州省', '520000', false],
  ['云南省', '530000', false],
  ['西藏自治区', '540000', false],
  ['陕西省', '610000', false],
  ['甘肃省', '620000', false],
  ['青海省', '630000', false],
  ['宁夏回族自治区', '640000', false],
  ['新疆维吾尔自治区', '650000', false],
  ['台湾省', '710000', false],
  ['香港', '810000', false],
  ['澳门', '820000', false],
] as const;

/** 从基础配置生成完整的省份下钻配置列表 */
export const PROVINCE_MAP_CONFIGS: ProvinceMapConfig[] = PROVINCE_BASE_CONFIGS.map(
  ([name, adcode, isMunicipality]) => ({
    name,
    adcode,
    // GeoJSON 路径：/geojson/province/{adcode}.json
    geoJsonPath: `${PROVINCE_GEOJSON_PREFIX}/${adcode}.json`,
    scaleLabel: '100 km',
    // 直辖市直接展开到区县，普通省份展开到市级
    mapLabel: isMunicipality ? '区县展开地图' : '市级展开地图',
    isMunicipality,
  }),
);

/** 按省份名称索引的快速查找表 */
export const PROVINCE_MAPS_BY_NAME = Object.fromEntries(
  PROVINCE_MAP_CONFIGS.map((item) => [item.name, item]),
) as Record<string, ProvinceMapConfig>;

/** 按行政区划代码索引的快速查找表 */
export const PROVINCE_MAPS_BY_ADCODE = Object.fromEntries(
  PROVINCE_MAP_CONFIGS.map((item) => [item.adcode, item]),
) as Record<string, ProvinceMapConfig>;

/** 区域访问量 Mock 数据（省份 + 部分城市/区县） */
export const PROVINCE_VIEW_COUNTS: Record<string, number> = {
  '北京市': 18240,
  '天津市': 10420,
  '河北省': 23890,
  '山西省': 15930,
  '内蒙古自治区': 14650,
  '辽宁省': 25110,
  '吉林省': 14320,
  '黑龙江省': 17680,
  '上海市': 31680,
  '江苏省': 42860,
  '浙江省': 39670,
  '安徽省': 20540,
  '福建省': 22180,
  '江西省': 17850,
  '山东省': 40220,
  '河南省': 35890,
  '湖北省': 28940,
  '湖南省': 26470,
  '广东省': 53420,
  '广西壮族自治区': 19380,
  '海南省': 11260,
  '重庆市': 28640,
  '四川省': 32410,
  '贵州省': 15120,
  '云南省': 16870,
  '西藏自治区': 8640,
  '陕西省': 21450,
  '甘肃省': 12980,
  '青海省': 7580,
  '宁夏回族自治区': 9320,
  '新疆维吾尔自治区': 18790,
  '香港': 6230,
  '澳门': 4180,
  '香港特别行政区': 6230,
  '澳门特别行政区': 4180,
  '台湾省': 12960,
  '杭州市': 18630,
  '宁波市': 16120,
  '温州市': 14980,
  '苏州市': 20460,
  '南京市': 17650,
  '广州市': 23180,
  '深圳市': 24670,
  '东城区': 9120,
  '西城区': 8640,
};

/**
 * 按省份名称查找下钻配置
 * @param name - 省份名称
 * @returns 匹配的配置，未找到返回 null
 */
export function getProvinceMapByName(name: string): ProvinceMapConfig | null {
  return PROVINCE_MAPS_BY_NAME[name] ?? null;
}

/**
 * 按行政区划代码查找下钻配置
 * @param adcode - 行政区划代码
 * @returns 匹配的配置，未找到返回 null
 */
export function getProvinceMapByAdcode(adcode: string): ProvinceMapConfig | null {
  return PROVINCE_MAPS_BY_ADCODE[adcode] ?? null;
}

/**
 * 获取区域 Mock 访问量
 * 优先从预设数据中查找，未找到时基于名称哈希生成稳定数值
 * @param name - 区域名称
 * @returns 访问量数值
 */
export function getMockRegionViewCount(name: string): number {
  const fixed = PROVINCE_VIEW_COUNTS[name];
  if (typeof fixed === 'number') {
    return fixed;
  }

  // 无预设数据时，基于名称字符串哈希生成 8000 ~ 50000 的稳定伪随机数
  let hash = 0;
  for (let index = 0; index < name.length; index += 1) {
    hash = (hash * 31 + name.charCodeAt(index)) >>> 0;
  }

  return 8000 + (hash % 42000);
}

/**
 * 构建省份下钻提示文案
 * @param name - 省份名称
 */
export function buildProvinceHint(name: string): string {
  return `在${name}附近滚轮放大可查看市级数据`;
}

/**
 * 构建下钻提示文案
 * @param isMunicipality - 是否为直辖市
 */
export function buildDrillHint(isMunicipality: boolean): string {
  return isMunicipality ? '点击区县查看浏览次数' : '点击城市查看浏览次数';
}

/**
 * 格式化访问量数字为千分位展示
 * @param value - 原始数值或字符串
 * @returns 格式化后的字符串（如 "18,240"），无效值返回 "-"
 */
export function formatRegionViewCount(value: number | string): string {
  if (value === '-' || value === '') {
    return '-';
  }

  const numeric = typeof value === 'number' ? value : Number(value);
  if (Number.isNaN(numeric)) {
    return String(value);
  }

  return new Intl.NumberFormat('en-US').format(numeric);
}
