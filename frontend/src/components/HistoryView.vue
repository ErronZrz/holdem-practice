<script setup>
import { onActivated, ref } from 'vue'
import { api } from '../api.js'
import { groupHandActions, HAND_CATEGORY_CN, STREET_CN } from '../cards.js'
import { copyText } from '../clipboard.js'
import { referenceLimitationText, referenceScopeText, referenceText } from '../reviewText.js'
import HandActionTimeline from './HandActionTimeline.vue'
import PlayingCard from './PlayingCard.vue'
import ReviewDecisionCard from './ReviewDecisionCard.vue'
import ReviewFrame from './ReviewFrame.vue'

const sessions = ref([])
const selectedSession = ref(null)
const hands = ref([])
const selectedHand = ref(null)
const review = ref(null)
const coach = ref(null)
const coachLoading = ref(false)
const coachError = ref('')
const copiedHandId = ref('')
const error = ref('')

function playerName(history, seat) {
  const p = history.players.find((x) => x.seat === seat)
  return p ? p.name : `座位 ${seat}`
}

function groupActions(history) {
  return groupHandActions(history.actions, history.players)
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

let coachEpoch = 0

function resetCoach() {
  coachEpoch += 1
  coach.value = null
  coachLoading.value = false
  coachError.value = ''
}

function coachFor(index) {
  const items = coach.value?.decisions
  if (!items) return null
  return items.find((item) => item.action_index === index) || null
}

async function selectSession(id) {
  selectedSession.value = id
  selectedHand.value = null
  review.value = null
  resetCoach()
  await loadHands(id)
}

async function selectHand(id) {
  error.value = ''
  if (!selectedHand.value || selectedHand.value.id !== id) resetCoach()
  review.value = null
  try {
    selectedHand.value = await api.getHand(id)
    review.value = await api.getReview(id)
    if (review.value?.hand_id === id) await loadCachedCoach(id)
  } catch (e) {
    error.value = e.message
  }
}

async function loadCachedCoach(handId) {
  const ticket = ++coachEpoch
  try {
    const data = await api.getExplanation(handId)
    if (ticket !== coachEpoch || review.value?.hand_id !== handId) return
    if (data.decisions?.length) coach.value = data
  } catch {
    // 只读缓存失败时仍可手动生成解读。
  }
}

function applyCoachDecision(updated) {
  coachEpoch += 1
  if (!coach.value || coach.value.hand_id !== review.value?.hand_id) return
  const items = coach.value.decisions.slice()
  const index = items.findIndex((item) => item.action_index === updated.action_index)
  if (index === -1) items.push(updated)
  else items[index] = updated
  coach.value = { ...coach.value, decisions: items }
}

async function loadCoach() {
  const handId = review.value?.hand_id
  if (!handId || coachLoading.value) return
  const ticket = ++coachEpoch
  coachLoading.value = true
  coachError.value = ''
  try {
    const data = await api.explainHand(handId)
    if (ticket !== coachEpoch || review.value?.hand_id !== handId) return
    coach.value = data
  } catch (e) {
    if (ticket !== coachEpoch || review.value?.hand_id !== handId) return
    coachError.value = e.message || '教练解读暂时不可用'
  } finally {
    if (review.value?.hand_id === handId) coachLoading.value = false
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
          <HandActionTimeline :groups="groupActions(selectedHand.history)" />
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
          <ReviewFrame>
            <template #head>
              <div class="review-title-row">
                <h3>本手复盘</h3>
                <div class="review-counts">
                  <span class="count-pill">{{ review.decisions.length }} 个决策点</span>
                  <span class="issue-pill" :class="{ clear: review.mistake_count === 0 }">
                    {{ review.mistake_count }} 处问题
                  </span>
                </div>
              </div>
              <div class="review-tools">
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
                <div class="coach-bar">
                  <button type="button" :disabled="coachLoading" @click="loadCoach">
                    {{ coachLoading ? '教练正在思考…' : 'AI 教练解读' }}
                  </button>
                  <span v-if="coachError" class="coach-error">{{ coachError }}</span>
                </div>
              </div>
            </template>
            <p v-if="coach && !coach.decisions.length" class="muted">本手没有可解读的决策点。</p>
            <ReviewDecisionCard
              v-for="(d, i) in review.decisions"
              :key="`${review.hand_id}-${i}`"
              :decision="d"
              :coach="coachFor(i)"
              :hand-id="review.hand_id"
              @asked="applyCoachDecision"
            />
            <template #notes>
              <p>{{ referenceText(review) }}</p>
              <p v-if="referenceScopeText(review)">{{ referenceScopeText(review) }}</p>
              <p v-if="referenceLimitationText(review)">{{ referenceLimitationText(review) }}</p>
            </template>
          </ReviewFrame>
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

.actions {
  margin-top: 8px;
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

.hand-id-line {
  margin: 0;
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

.coach-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.coach-error {
  color: #b91c1c;
  font-size: 13px;
}
</style>
