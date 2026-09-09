<script setup>
import { ref } from 'vue'
import GameTable from './components/GameTable.vue'
import HistoryView from './components/HistoryView.vue'
import StatsView from './components/StatsView.vue'

const view = ref('table')

const tabs = [
  { id: 'table', label: '牌桌' },
  { id: 'history', label: '历史' },
  { id: 'stats', label: '统计' },
]
</script>

<template>
  <div class="app-shell">
    <nav class="app-nav">
      <span class="brand">德州扑克练习平台</span>
      <button
        v-for="t in tabs"
        :key="t.id"
        :class="{ active: view === t.id }"
        @click="view = t.id"
      >
        {{ t.label }}
      </button>
    </nav>

    <!-- 用 KeepAlive 保持牌桌组件状态，切换 tab 不丢失进行中的对局。 -->
    <KeepAlive>
      <GameTable v-if="view === 'table'" @navigate="view = $event" />
      <HistoryView v-else-if="view === 'history'" />
      <StatsView v-else />
    </KeepAlive>
  </div>
</template>
