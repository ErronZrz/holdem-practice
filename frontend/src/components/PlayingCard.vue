<script setup>
import { computed } from 'vue'
import { cardParts } from '../cards.js'

const props = defineProps({
  code: { type: String, default: '' },
  hidden: { type: Boolean, default: false },
  small: { type: Boolean, default: false },
})

const parts = computed(() => (props.hidden ? null : cardParts(props.code)))
</script>

<template>
  <span v-if="hidden" class="pc pc-back" aria-label="底牌">♠</span>
  <span v-else class="pc" :class="{ red: parts.red, small: props.small }" aria-label="牌">
    <span class="pc-rank">{{ parts.rank }}</span>
    <span class="pc-suit">{{ parts.suit }}</span>
  </span>
</template>

<style scoped>
.pc {
  display: inline-flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  width: 38px;
  height: 54px;
  border-radius: 6px;
  background: #fff;
  border: 1px solid #cbd5e1;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.2);
  color: #0f172a;
  line-height: 1;
  font-weight: 700;
}

.pc.red {
  color: #dc2626;
}

.pc-rank {
  font-size: 16px;
}

.pc-suit {
  font-size: 16px;
}

.pc.small {
  width: 24px;
  height: 34px;
  border-radius: 4px;
}

.pc.small .pc-rank {
  font-size: 11px;
}

.pc.small .pc-suit {
  font-size: 11px;
}

.pc-back {
  background: repeating-linear-gradient(
    45deg,
    #1d4ed8,
    #1d4ed8 6px,
    #2563eb 6px,
    #2563eb 12px
  );
  color: #fff;
  border-color: #1e40af;
  font-size: 20px;
}
</style>
