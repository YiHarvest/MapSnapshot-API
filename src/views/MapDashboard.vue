<template>
  <div class="dashboard-page">
    <main class="dashboard-body">
      <section class="map-stage">
        <!-- 地图组件：监听区域点击和加载错误事件 -->
        <AmapDashboardMap
          class="map-stage__chart"
          @region-click="handleRegionClick"
          @load-error="handleMapLoadError"
        />

        <!-- 右上角悬浮：区域信息卡片 -->
        <div class="map-stage__overlay map-stage__info">
          <RegionInfoCard :info="currentRegion" :show-back-button="false" />
        </div>

        <!-- 地图加载错误提示 -->
        <p v-if="statusMessage" class="map-stage__status">{{ statusMessage }}</p>
      </section>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import AmapDashboardMap from '@/components/map/AmapDashboardMap.vue';
import RegionInfoCard from '@/components/dashboard/RegionInfoCard.vue';
import {
  DEFAULT_REGION_INFO,
  formatRegionViewCount,
  getMockRegionViewCount,
  REGION_LEVEL_LABELS,
} from '@/constants/region';
import { getRegionViewCount } from '@/api/region';
import { MSG_REGION_NOT_CONFIGURED } from '@/config';
import type { RegionInfo, RegionSelection } from '@/types/region';

/** 当前选中区域的展示信息 */
const currentRegion = ref<RegionInfo>({ ...DEFAULT_REGION_INFO });
/** 状态提示消息 */
const statusMessage = ref('');

/**
 * 将区域层级枚举转换为中文标签
 * @param level - 区域层级
 */
function getLevelLabel(level: RegionSelection['level']) {
  if (level === 'city') {
    return REGION_LEVEL_LABELS.city;
  }

  if (level === 'district') {
    return REGION_LEVEL_LABELS.district;
  }

  return REGION_LEVEL_LABELS.province;
}

/**
 * 处理地图区域点击事件
 * 获取该区域的访问量数据并更新信息卡片
 */
async function handleRegionClick(region: RegionSelection) {
  statusMessage.value = '';

  // 省级直接用 Mock 数据快速展示；市级/区级异步获取
  const visits =
    region.level === 'province'
      ? getMockRegionViewCount(region.name)
      : await getRegionViewCount(region.adcode ?? region.name);

  currentRegion.value = {
    name: region.name,
    visits: formatRegionViewCount(visits),
    level: getLevelLabel(region.level),
    adcode: region.adcode,
  };
}

/**
 * 处理地图加载错误
 * GeoJSON 加载失败时给出友好提示
 */
function handleMapLoadError(message: string) {
  statusMessage.value = message.includes('Failed to load geojson') ? MSG_REGION_NOT_CONFIGURED : message;
}
</script>
