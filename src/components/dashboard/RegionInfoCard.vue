<template>
  <!-- 当前选中区域的信息卡片 -->
  <section class="region-info-card">
    <div class="region-info-card__row">
      <span class="region-info-card__label">当前选中</span>
      <span class="region-info-card__value">{{ info.name }}</span>
    </div>
    <div class="region-info-card__row">
      <span class="region-info-card__label">浏览次数</span>
      <span class="region-info-card__value">{{ formattedVisits }}</span>
    </div>
    <div class="region-info-card__row">
      <span class="region-info-card__label">层级</span>
      <span class="region-info-card__level">{{ info.level }}</span>
    </div>
    <!-- 地图层级信息，如有则展示 -->
    <div v-if="info.mapLabel" class="region-info-card__row">
      <span class="region-info-card__label">地图层级</span>
      <span class="region-info-card__level">{{ info.mapLabel }}</span>
    </div>
    <!-- 提示信息 -->
    <p v-if="info.hint" class="region-info-card__hint">{{ info.hint }}</p>
    <!-- 返回全国按钮 -->
    <div v-if="showBackButton" class="region-info-card__footer">
      <button class="region-info-card__back-button" type="button" @click="emit('back-home')">
        返回全国
      </button>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { formatRegionViewCount } from '@/constants/region';
import type { RegionInfo } from '@/types/region';

const props = defineProps<{
  /** 区域信息数据 */
  info: RegionInfo;
  /** 是否显示返回全国按钮 */
  showBackButton?: boolean;
}>();

const emit = defineEmits<{
  /** 点击返回全国按钮 */
  (event: 'back-home'): void;
}>();

// 格式化访问量显示（千分位）
const formattedVisits = computed(() => formatRegionViewCount(props.info.visits));
</script>
