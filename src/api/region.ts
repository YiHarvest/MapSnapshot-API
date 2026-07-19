/**
 * 区域数据 API 层
 * - 获取区域访问量（当前使用 Mock 数据，可替换为真实接口）
 * - 加载 GeoJSON 矢量数据文件
 */
import { getMockRegionViewCount } from '@/constants/region';

/**
 * 获取区域的访问量数据
 * @param adcodeOrName - 行政区划代码或区域名称
 * @returns 访问量数值
 */
export async function getRegionViewCount(adcodeOrName: string): Promise<number> {
  // 当前使用 Mock 数据，接入真实接口时替换此函数实现
  return getMockRegionViewCount(adcodeOrName);
}

/**
 * 从 public 目录加载 GeoJSON 文件
 * @param path - 文件路径（如 /geojson/china.json）
 * @returns 解析后的 GeoJSON 对象
 */
export async function loadGeoJson(path: string): Promise<unknown> {
  const response = await fetch(path);
  if (!response.ok) {
    throw new Error(`Failed to load geojson: ${path} (${response.status})`);
  }

  return response.json();
}
