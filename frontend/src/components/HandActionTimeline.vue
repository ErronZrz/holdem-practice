<script setup>
import ActionChip from './ActionChip.vue'
import StreetBadge from './StreetBadge.vue'

defineProps({
  groups: { type: Array, required: true },
})
</script>

<template>
  <div class="timeline">
    <section
      v-for="(g, gi) in groups"
      :key="gi"
      class="ha-street"
      :class="'street-' + g.street"
    >
      <div class="ha-rail" aria-hidden="true" />
      <div class="ha-body">
        <StreetBadge :street="g.street" />
        <ul class="ha-list">
          <li
            v-for="(item, i) in g.items"
            :key="i"
            class="ha-item"
            :class="{ human: item.isHuman }"
          >
            <span class="ha-name">{{ item.name }}</span>
            <ActionChip :action="item.action" :amount="item.amount" />
          </li>
        </ul>
      </div>
    </section>
  </div>
</template>

<style scoped>
.timeline {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.ha-street {
  display: grid;
  grid-template-columns: 4px minmax(0, 1fr);
  gap: 10px;
}

.ha-rail {
  border-radius: 999px;
  background: var(--street, #94a3b8);
}

.ha-body {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 8px;
  min-width: 0;
}

.ha-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin: 0;
  padding: 0;
  list-style: none;
  width: 100%;
}

.ha-item {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  max-width: 100%;
  padding: 4px 6px 4px 10px;
  border-radius: 999px;
  background: #f8fafc;
  border: 1px solid #e8eef5;
}

.ha-item.human {
  background: #eff6ff;
  border-color: #bfdbfe;
}

.ha-name {
  font-size: 13px;
  font-weight: 600;
  color: #0f172a;
}
</style>
