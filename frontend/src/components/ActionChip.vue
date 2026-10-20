<script setup>
import { computed } from 'vue'
import { ACTION_CN } from '../cards.js'

const props = defineProps({
  action: { type: String, required: true },
  amount: { type: Number, default: 0 },
  share: { type: Number, default: null },
})

const label = computed(() => ACTION_CN[props.action] || props.action)
</script>

<template>
  <span class="action-chip" :class="'tone-' + action">
    <span>{{ label }}</span>
    <span v-if="amount || share != null" class="action-chip-meta num">
      <template v-if="amount">{{ amount }}</template>
      <template v-if="amount && share != null"> · </template>
      <template v-if="share != null">{{ share }}%</template>
    </span>
  </span>
</template>

<style scoped>
.action-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border-radius: 999px;
  padding: 3px 8px 3px 9px;
  font-size: 12px;
  font-weight: 700;
  line-height: 1.3;
  white-space: nowrap;
}

.action-chip.tone-fold {
  font-weight: 600;
}

.action-chip.tone-small_blind,
.action-chip.tone-big_blind {
  box-shadow: inset 0 0 0 1px #e2e8f0;
}

.action-chip-meta {
  padding: 0 6px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.78);
  font-weight: 800;
}
</style>
