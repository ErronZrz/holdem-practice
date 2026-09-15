<script setup>
import { onActivated, ref } from 'vue'
import { api } from '../api.js'

const sessions = ref([])
const selectedSession = ref(null)
const stats = ref(null)
const error = ref('')

async function loadSessions() {
  error.value = ''
  try {
    sessions.value = await api.listGames()
  } catch (e) {
    error.value = e.message
  }
}

async function selectSession(id) {
  selectedSession.value = id
  error.value = ''
  try {
    stats.value = await api.getStats(id)
  } catch (e) {
    error.value = e.message
  }
}

function bb(value, bigBlind) {
  const n = value / bigBlind
  return Number.isInteger(n) ? n : n.toFixed(1)
}

// 不限手数的对局（target_hands 为 0）不展示目标手数。
function handsText(session) {
  return session.target_hands > 0
    ? `${session.hands_played}/${session.target_hands} 手`
    : `${session.hands_played} 手`
}

function handsValue(stats) {
  return stats.target_hands > 0
    ? `${stats.hands_played} / ${stats.target_hands}`
    : `${stats.hands_played}`
}

onActivated(() => {
  loadSessions()
  if (selectedSession.value) selectSession(selectedSession.value)
})
</script>

<template>
  <div class="stats">
    <div class="panel">
      <h2>结算统计</h2>
      <p v-if="!sessions.length" class="muted">暂无对局。</p>
      <select v-else v-model="selectedSession" @change="selectSession(selectedSession)">
        <option disabled value="">选择对局…</option>
        <option v-for="s in sessions" :key="s.id" :value="s.id">
          {{ new Date(s.created_at).toLocaleString() }} · {{ s.num_players }} 人 ·
          {{ handsText(s) }}
        </option>
      </select>
    </div>

    <div v-if="stats" class="panel">
      <div class="cards">
        <div class="stat-card">
          <div class="stat-label">已打手数</div>
          <div class="stat-value">{{ handsValue(stats) }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">累计净盈亏</div>
          <div class="stat-value" :class="stats.net_chips >= 0 ? 'win' : 'loss'">
            {{ stats.net_chips >= 0 ? '+' : '' }}{{ stats.net_chips }}
          </div>
          <div class="stat-sub">≈ {{ bb(stats.net_chips, stats.big_blind) }} BB</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">胜 / 负 / 平</div>
          <div class="stat-value">{{ stats.wins }} / {{ stats.losses }} / {{ stats.ties }}</div>
        </div>
      </div>
      <div class="meta">
        状态：{{ stats.status === 'finished' ? '已结束' : '进行中' }} ·
        大盲 {{ stats.big_blind }} 筹码
      </div>
    </div>

    <div v-if="error" class="error-banner">{{ error }}</div>
  </div>
</template>

<style scoped>
.stats {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

h2 {
  margin-top: 0;
}

.muted {
  color: var(--muted);
}

select {
  width: 100%;
}

.cards {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}

.stat-card {
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 16px;
  text-align: center;
}

.stat-label {
  color: var(--muted);
  font-size: 13px;
  margin-bottom: 8px;
}

.stat-value {
  font-size: 24px;
  font-weight: 700;
}

.stat-sub {
  color: var(--muted);
  font-size: 13px;
  margin-top: 4px;
}

.win {
  color: #16a34a;
}

.loss {
  color: #dc2626;
}

.meta {
  margin-top: 12px;
  color: var(--muted);
  font-size: 14px;
}
</style>
