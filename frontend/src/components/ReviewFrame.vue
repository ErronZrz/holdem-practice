<script setup>
import { useSlots } from 'vue'

const slots = useSlots()
</script>

<template>
  <section class="review-frame">
    <header class="review-head">
      <slot name="head" />
    </header>
    <div class="review-body">
      <slot />
    </div>
    <footer v-if="slots.notes" class="review-notes">
      <div class="review-notes-kicker">说明</div>
      <slot name="notes" />
    </footer>
  </section>
</template>

<style scoped>
.review-frame {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.review-head {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding-bottom: 10px;
  border-bottom: 1px solid #e2e8f0;
}

.review-body {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.review-notes {
  padding: 10px 12px;
  border-radius: 10px;
  background: #f8fafc;
  border: 1px dashed #e2e8f0;
}

.review-notes-kicker {
  margin-bottom: 4px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.06em;
  color: #94a3b8;
}

.review-frame :deep(.review-title-row) {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
}

.review-frame :deep(.review-title-row h3) {
  margin: 0;
  font-size: 1.17em;
  font-weight: 700;
}

.review-frame :deep(.review-counts) {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.review-frame :deep(.count-pill),
.review-frame :deep(.issue-pill) {
  border-radius: 999px;
  padding: 3px 8px;
  font-size: 12px;
  font-weight: 700;
  line-height: 1.4;
}

.review-frame :deep(.count-pill) {
  background: #eef2ff;
  color: #3730a3;
}

.review-frame :deep(.issue-pill) {
  background: #fee2e2;
  color: #b91c1c;
}

.review-frame :deep(.issue-pill.clear) {
  background: #ecfdf5;
  color: #047857;
}

.review-frame :deep(.review-tools) {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px 12px;
}

.review-frame :deep(.hand-id-line) {
  margin: 0;
}

.review-frame :deep(.coach-bar) {
  margin: 0;
}

.review-frame :deep(.coach-bar button) {
  border-color: #bfdbfe;
  background: #eff6ff;
  color: #1d4ed8;
  font-weight: 600;
}

.review-frame :deep(.coach-bar button:hover:not(:disabled)) {
  background: #dbeafe;
}

.review-notes :deep(p) {
  margin: 0 0 4px;
  font-size: 12px;
  line-height: 1.55;
  color: var(--muted);
}

.review-notes :deep(p:last-child) {
  margin-bottom: 0;
}
</style>
