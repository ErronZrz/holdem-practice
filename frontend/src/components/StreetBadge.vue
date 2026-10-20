<script setup>
import { STREET_CN } from '../cards.js'

defineProps({
  street: { type: String, required: true },
})
</script>

<template>
  <span class="street-badge" :class="'street-' + street">{{ STREET_CN[street] || street }}</span>
</template>

<style scoped>
.street-badge {
  display: inline-flex;
  align-items: center;
  height: 22px;
  padding: 0 8px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.02em;
  color: var(--street, #334155);
  background: color-mix(in srgb, var(--street, #64748b) 14%, white);
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--street, #64748b) 30%, white);
}
</style>
