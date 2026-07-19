/**
 * GeoJSON 工具函数
 * - 基于射线法（Ray Casting）实现点面碰撞检测
 * - 支持 Polygon 和 MultiPolygon 几何类型
 * - 支持带孔洞的多边形
 */
import type { GeoJsonFeature, GeoJsonFeatureCollection } from '@/types/region';

/**
 * 射线法判断点是否在多边形环内
 * 沿水平方向向右发射射线，统计与环的交点数量，奇数在内、偶数在外
 * @param point - 待检测点 [lng, lat]
 * @param ring - 多边形环的坐标数组 [[lng, lat], ...]
 */
function isPointInRing(point: [number, number], ring: number[][]): boolean {
  const [x, y] = point;
  let inside = false;

  for (let index = 0, previousIndex = ring.length - 1; index < ring.length; previousIndex = index, index += 1) {
    const [xi, yi] = ring[index];
    const [xj, yj] = ring[previousIndex];
    // 判断射线与边的交点
    const intersects = yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi || Number.EPSILON) + xi;

    if (intersects) {
      inside = !inside;
    }
  }

  return inside;
}

/**
 * 判断点是否在 Polygon 中（含孔洞处理）
 * 点必须在外环内，且不在任何孔洞中
 * @param point - 待检测点
 * @param polygon - Polygon 坐标（外环 + 孔洞列表）
 */
function isPointInPolygonCoordinates(point: [number, number], polygon: unknown): boolean {
  if (!Array.isArray(polygon) || polygon.length === 0) {
    return false;
  }

  const [outerRing, ...holes] = polygon as number[][][];
  // 不在外环内，直接排除
  if (!isPointInRing(point, outerRing)) {
    return false;
  }

  // 排除落在孔洞中的情况
  return !holes.some((hole) => isPointInRing(point, hole));
}

/**
 * 判断点是否在 GeoJSON 要素内
 * 支持 Polygon 和 MultiPolygon 两种几何类型
 * @param point - 待检测点
 * @param feature - GeoJSON 要素
 */
function isPointInFeature(point: [number, number], feature: GeoJsonFeature): boolean {
  const geometry = feature.geometry;
  if (!geometry) {
    return false;
  }

  if (geometry.type === 'Polygon') {
    return isPointInPolygonCoordinates(point, geometry.coordinates);
  }

  if (geometry.type === 'MultiPolygon' && Array.isArray(geometry.coordinates)) {
    return geometry.coordinates.some((polygon) => isPointInPolygonCoordinates(point, polygon));
  }

  return false;
}

/**
 * 在 GeoJSON 要素集合中查找包含指定点的要素
 * 用于地图点击时判断用户点击了哪个区域
 * @param geoJson - 要素集合
 * @param point - 地图点击坐标 [lng, lat]
 * @param level - 可选，限定比对层级
 * @returns 匹配的要素，未找到返回 null
 */
export function getFeatureAtPoint(
  geoJson: GeoJsonFeatureCollection,
  point: [number, number],
  level?: string,
): GeoJsonFeature | null {
  for (const feature of geoJson.features ?? []) {
    if (!feature.properties?.name) {
      continue;
    }

    // 层级过滤：如果指定了 level 则只匹配该层级的要素
    if (level && feature.properties.level !== level) {
      continue;
    }

    if (isPointInFeature(point, feature)) {
      return feature;
    }
  }

  return null;
}
