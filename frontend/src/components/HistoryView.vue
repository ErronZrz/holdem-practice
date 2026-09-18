<script setup>
import { onActivated, ref } from 'vue'
import { api } from '../api.js'
import {
  ACTION_CN,
  HAND_CATEGORY_CN,
  STREET_CN,
  actionText as actionLabel,
  distributionText,
} from '../cards.js'
import { copyText } from '../clipboard.js'
import { referenceLimitationText, referenceScopeText, referenceText } from '../reviewText.js'
import PlayingCard from './PlayingCard.vue'

const sessions = ref([])
const selectedSession = ref(null)
const hands = ref([])
const selectedHand = ref(null)
const review = ref(null)
const copiedHandId = ref('')
const error = ref('')

function playerName(history, seat) {
  const p = history.players.find((x) => x.seat === seat)
  return p ? p.name : `座位 ${seat}`
}

function actionText(history, a) {
  const name = playerName(history, a.seat)
  if (a.action === 'small_blind' || a.action === 'big_blind') {
    return `${name} 下${ACTION_CN[a.action] || a.action} ${a.amount}`
  }
  if (a.amount) {
    return `${name} ${ACTION_CN[a.action] || a.action} ${a.amount}`
  }
  return `${name} ${ACTION_CN[a.action] || a.action}`
}

function groupActions(history) {
  const groups = []
  for (const a of history.actions) {
    const last = groups[groups.length - 1]
    if (!last || last.street !== a.street) {
      groups.push({ street: a.street, items: [a] })
    } else {
      last.items.push(a)
    }
  }
  return groups
}

async function loadSessions() {
  error.value = ''
  try {
    sessions.value = await api.listGames()
  } catch (e) {
    error.value = e.message
  }
}

async function loadHands(id) {
  error.value = ''
  try {
    hands.value = await api.listHands(id)
  } catch (e) {
    error.value = e.message
  }
}

async function selectSession(id) {
  selectedSession.value = id
  selectedHand.value = null
  review.value = null
  await loadHands(id)
}

async function selectHand(id) {
  error.value = ''
  review.value = null
  try {
    selectedHand.value = await api.getHand(id)
    review.value = await api.getReview(id)
  } catch (e) {
    error.value = e.message
  }
}

async function copyHandId(id) {
  if (!(await copyText(id))) return
  copiedHandId.value = id
  setTimeout(() => {
    if (copiedHandId.value === id) copiedHandId.value = ''
  }, 1500)
}

function netOf(history, seat) {
  return history.net?.[String(seat)] ?? 0
}

// 不限手数的对局（target_hands 为 0）只显示已打手数。
function handsText(session) {
  return session.target_hands > 0
    ? `${session.hands_played}/${session.target_hands} 手`
    : `${session.hands_played} 手`
}

function showdownHandOf(history, seat) {
  return history.showdown_hands?.[String(seat)] || null
}

function pct(x) {
  return x == null ? '—' : `${(x * 100).toFixed(0)}%`
}

function evText(x) {
  return x == null ? '—' : (x > 0 ? '+' : '') + x
}

function mistakeClass(severity) {
  return { error: 'mistake-error', warning: 'mistake-warning', info: 'mistake-info' }[severity] || ''
}

onActivated(() => {
  loadSessions()
  if (selectedSession.value) loadHands(selectedSession.value)
})
</script>

<template>
  <div class="history">
    <div class="panel">
      <h2>历史对局</h2>
      <p v-if="!sessions.length" class="muted">暂无历史对局，先去牌桌打几手吧。</p>
      <select v-else v-model="selectedSession" @change="selectSession(selectedSession)">
        <option disabled value="">选择对局…</option>
        <option v-for="s in sessions" :key="s.id" :value="s.id">
          {{ new Date(s.created_at).toLocaleString() }} · {{ s.num_players }} 人 ·
          {{ handsText(s) }} · 净 {{ s.net_chips }}
        </option>
      </select>
    </div>

    <div v-if="selectedSession" class="columns">
      <div class="panel hand-list">
        <h3>手牌列表</h3>
        <ul>
          <li
            v-for="h in hands"
            :key="h.id"
            :class="{ active: selectedHand && selectedHand.id === h.id }"
            @click="selectHand(h.id)"
          >
            <span>第 {{ h.hand_number }} 手</span>
            <span :class="h.net > 0 ? 'win' : h.net < 0 ? 'loss' : 'tie'">
              {{ h.net > 0 ? '+' : '' }}{{ h.net }}
            </span>
            <span class="muted">{{ STREET_CN[h.street] || h.street }}</span>
          </li>
        </ul>
        <p v-if="selectedSession && !hands.length" class="muted">该对局尚无已完成手牌。</p>
      </div>

      <div v-if="selectedHand" class="panel hand-detail">
        <h3>第 {{ selectedHand.hand_number }} 手详情</h3>
        <div class="detail-board">
          <PlayingCard v-for="(c, i) in selectedHand.history.board" :key="i" :code="c" />
        </div>
        <div class="detail-players">
          <div v-for="p in selectedHand.history.players" :key="p.seat" class="detail-player">
            <span>{{ p.name }}{{ p.is_human ? '（你）' : '' }}</span>
            <span class="cards-mini">
              <PlayingCard v-for="(c, i) in p.hole_cards" :key="i" :code="c" />
            </span>
            <span :class="netOf(selectedHand.history, p.seat) >= 0 ? 'win' : 'loss'">
              {{ netOf(selectedHand.history, p.seat) >= 0 ? '+' : ''
              }}{{ netOf(selectedHand.history, p.seat) }}
            </span>
            <span v-if="showdownHandOf(selectedHand.history, p.seat)" class="showdown-text">
              {{ HAND_CATEGORY_CN[showdownHandOf(selectedHand.history, p.seat).category] }}：
              <span class="cards-mini">
                <PlayingCard
                  v-for="(c, i) in showdownHandOf(selectedHand.history, p.seat).cards"
                  :key="i"
                  :code="c"
                  small
                />
              </span>
            </span>
          </div>
        </div>
        <div class="actions">
          <div v-for="g in groupActions(selectedHand.history)" :key="g.street" class="street-group">
            <div class="street-title">{{ STREET_CN[g.street] || g.street }}</div>
            <div v-for="(a, i) in g.items" :key="i" class="action-line">
              {{ actionText(selectedHand.history, a) }}
            </div>
          </div>
        </div>
        <div class="detail-result">
          结果：{{ selectedHand.history.showdown ? '摊牌' : '弃牌获胜' }}，
          赢家 {{ selectedHand.history.winners.map((w) => playerName(selectedHand.history, w)).join('、') }}
        </div>
        <div
          v-if="selectedHand.history.pot_results && selectedHand.history.pot_results.length"
          class="pot-results"
        >
          <div v-for="(pr, i) in selectedHand.history.pot_results" :key="i" class="pot-result">
            <template v-if="selectedHand.history.pot_results.length > 1">边池 {{ i + 1 }}：</template>
            <template v-else>底池：</template>
            {{ pr.amount }} 筹码 → {{ pr.winners.map((w) => playerName(selectedHand.history, w)).join('、') }}
            <span v-if="pr.winners.length > 1" class="muted">
              （{{ pr.winners.map((w) => `${playerName(selectedHand.history, w)} +${pr.shares[w]}`).join('，') }}）
            </span>
          </div>
        </div>
        <div v-if="review" class="review">
          <h4>复盘</h4>
          <p class="muted">
            {{ referenceText(review) }} ·
            共 {{ review.decisions.length }} 个决策点 · 命中 {{ review.mistake_count }} 处问题
          </p>
          <p v-if="referenceScopeText(review)" class="muted">{{ referenceScopeText(review) }}</p>
          <p v-if="referenceLimitationText(review)" class="muted">
            {{ referenceLimitationText(review) }}
          </p>
          <p class="muted hand-id-line">
            手牌 ID：<code class="hand-id">{{ review.hand_id }}</code>
            <button
              class="copy-id"
              :class="{ copied: copiedHandId === review.hand_id }"
              type="button"
              :title="copiedHandId === review.hand_id ? '已复制' : '复制手牌 ID'"
              aria-label="复制手牌 ID"
              @click="copyHandId(review.hand_id)"
            >
              <svg
                viewBox="0 0 24 24"
                width="17"
                height="17"
                fill="none"
                stroke="currentColor"
                stroke-width="1.8"
                stroke-linecap="round"
                stroke-linejoin="round"
                aria-hidden="true"
              >
                <path
                  v-if="copiedHandId === review.hand_id"
                  d="m5.5 12.5 4 4 9-9"
                  stroke-width="2.2"
                />
                <g v-else>
                  <!-- 后层：靠近前层的位置断开 -->
                  <path d="M13 5H7a2 2 0 0 0-2 2v6" />
                  <path d="M15 8V7a2 2 0 0 0-2-2" />
                  <path d="M8 15H7a2 2 0 0 1-2-2" />

                  <!-- 前层：接近正方形 -->
                  <rect x="8.7" y="8.7" width="10.3" height="10.3" rx="2" />
                </g>
              </svg>
            </button>
          </p>
          <div v-for="(d, i) in review.decisions" :key="i" class="review-decision">
            <div class="review-street">
              <strong>{{ STREET_CN[d.street] || d.street }}</strong>
              <span v-if="d.board.length" class="cards-mini">
                <PlayingCard v-for="(c, j) in d.board" :key="j" :code="c" small />
              </span>
              <span class="muted">
                底池 {{ d.pot }} · 完整欠注 {{ d.to_call }}
                <template v-if="d.is_short_all_in_call">· 实际全下 {{ d.actual_call_amount }}</template>
              </span>
            </div>
            <div class="review-row">
              <span>你：{{ actionLabel(d.action) }}</span>
              <span>参考：{{ actionLabel(d.bot_action) }}</span>
            </div>
            <div v-if="distributionText(d)" class="review-row muted">
              <span>参考分布：{{ distributionText(d) }}</span>
            </div>
            <div class="review-row muted">
              <span>胜率 {{ pct(d.equity) }}</span>
              <span v-if="d.pot_odds != null">赔率 {{ pct(d.pot_odds) }}</span>
              <span v-if="d.call_ev != null">跟注 EV {{ evText(d.call_ev) }}</span>
            </div>
            <div v-if="d.is_short_all_in_call" class="review-row muted">
              <span>短码全下尚未建立逐池资格与 EV 模型，未显示单池赔率和跟注 EV。</span>
            </div>
            <div
              v-for="(m, k) in d.mistakes"
              :key="k"
              class="mistake"
              :class="mistakeClass(m.severity)"
            >
              {{ m.message }}
            </div>
          </div>
        </div>
      </div>
    </div>

    <div v-if="error" class="error-banner">{{ error }}</div>
  </div>
</template>

<style scoped>
.history {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.columns {
  display: grid;
  grid-template-columns: 280px 1fr;
  gap: 14px;
  align-items: start;
}

h2,
h3 {
  margin-top: 0;
}

.muted {
  color: var(--muted);
}

select {
  width: 100%;
}

.hand-list ul {
  list-style: none;
  padding: 0;
  margin: 0;
}

.hand-list li {
  display: flex;
  gap: 10px;
  padding: 8px 10px;
  border-radius: 8px;
  cursor: pointer;
}

.hand-list li:hover,
.hand-list li.active {
  background: #f1f5f9;
}

.win {
  color: #16a34a;
  font-weight: 600;
}

.loss {
  color: #dc2626;
  font-weight: 600;
}

.tie {
  color: var(--muted);
}

.detail-board {
  display: flex;
  gap: 6px;
  margin-bottom: 12px;
}

.detail-player {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  padding: 6px 0;
}

.cards-mini {
  display: flex;
  gap: 3px;
}

.showdown-text {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  color: #334155;
}

.street-group {
  margin-bottom: 10px;
}

.street-title {
  font-weight: 600;
  color: var(--accent);
  margin-bottom: 4px;
}

.action-line {
  padding-left: 12px;
  color: #334155;
  font-size: 14px;
}

.detail-result {
  margin-top: 8px;
  font-weight: 600;
}

.pot-results {
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 14px;
}

.pot-result {
  color: #334155;
}

.review {
  margin-top: 16px;
  padding-top: 14px;
  border-top: 1px solid #e2e8f0;
}

.review h4 {
  margin: 0 0 6px;
}

.hand-id-line {
  margin: 0 0 8px;
  font-size: 12px;
}

.hand-id {
  user-select: all;
  cursor: text;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.copy-id {
  margin-left: 6px;
  padding: 2px;
  border: none;
  background: transparent;
  color: #64748b;
  cursor: pointer;
  vertical-align: middle;
  line-height: 0;
}

.copy-id:hover {
  color: #334155;
}

.copy-id.copied {
  color: #16a34a;
}

.review-decision {
  padding: 10px 0;
  border-bottom: 1px dashed #e2e8f0;
}

.review-street {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 4px;
}

.review-row {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  font-size: 14px;
  color: #334155;
}

.mistake {
  margin-top: 6px;
  padding: 4px 8px;
  border-radius: 6px;
  font-size: 13px;
}

.mistake-error {
  background: #fee2e2;
  color: #b91c1c;
}

.mistake-warning {
  background: #fef3c7;
  color: #b45309;
}

.mistake-info {
  background: #e0e7ff;
  color: #3730a3;
}
</style>
