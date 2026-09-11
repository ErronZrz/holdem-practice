<script setup>
import { computed, onActivated, onDeactivated, onUnmounted, reactive, ref, watch } from 'vue'
import { api } from '../api.js'
import { actionText, HAND_CATEGORY_CN, STREET_CN } from '../cards.js'
import { copyText } from '../clipboard.js'
import PlayingCard from './PlayingCard.vue'

const emit = defineEmits(['navigate'])

const game = ref(null)
const sessionId = ref(null)
const error = ref('')
const busy = ref(false)
const pendingAction = ref(null)
const betAmount = ref(0)
const showReview = ref(true)
const review = ref(null)
const copiedHandId = ref('')

const form = reactive({
  num_players: 2,
  target_hands: 50,
  bot_strategy: 'heuristic',
  small_blind: 5,
  big_blind: 10,
  starting_stack: 1000,
  seed: null,
})

const players = computed(() => (game.value ? game.value.players : []))
const legal = computed(() => game.value?.legal_actions)

const streetLabel = computed(() => STREET_CN[game.value?.street] || game.value?.street || '')

const handActionGroups = computed(() => {
  if (!game.value) return []
  const groups = []
  for (const a of game.value.hand_actions) {
    const last = groups[groups.length - 1]
    if (!last || last.street !== a.street) {
      groups.push({ street: a.street, items: [a] })
    } else {
      last.items.push(a)
    }
  }
  return groups
})

function playerNameOf(seat) {
  const p = game.value?.players.find((x) => x.seat === seat)
  return p ? p.name : `座位 ${seat}`
}

function showdownHand(seat) {
  return game.value?.showdown_hands?.[seat] || null
}

function netOf(seat) {
  return game.value?.last_net?.[seat] ?? 0
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

function resultText() {
  if (!game.value?.hand_over) return ''
  const humanNet = netOf(game.value.human_seat)
  const won = game.value.winners.includes(game.value.human_seat)
  if (game.value.session_finished) {
    return `本局已结束，共 ${game.value.target_hands} 手`
  }
  if (won) return `你赢得本手，净 +${humanNet}`
  return `本手净 ${humanNet >= 0 ? '+' : ''}${humanNet}`
}

// 座位环绕牌桌的椭圆定位：座位 0（真人）固定在底部，其余顺时针分布。
function seatStyle(seat) {
  const n = game.value.players.length
  const angle = Math.PI / 2 + seat * ((2 * Math.PI) / n)
  const x = 50 + 40 * Math.cos(angle)
  const y = 50 + 34 * Math.sin(angle)
  return { left: `${x}%`, top: `${y}%` }
}

// ------------------------------------------------------------------ 轮询推进 Bot

let pollTimer = null
let polling = false

function maybePoll() {
  const g = game.value
  if (g && !g.hand_over && !g.is_human_turn) {
    startPolling()
  } else {
    stopPolling()
  }
}

function startPolling() {
  if (pollTimer) return
  pollTimer = setInterval(pollOnce, 400)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

async function pollOnce() {
  if (polling || !sessionId.value) return
  polling = true
  try {
    game.value = await api.getGame(sessionId.value)
    maybePoll()
  } catch (e) {
    error.value = e.message
    stopPolling()
  } finally {
    polling = false
  }
}

// ------------------------------------------------------------------ 动作与流程

async function createGame() {
  if (busy.value) return
  error.value = ''
  busy.value = true
  try {
    game.value = await api.createGame({ ...form })
    sessionId.value = game.value.session_id
    maybePoll()
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}

async function act(action, amount) {
  if (!sessionId.value || busy.value) return
  error.value = ''
  busy.value = true
  try {
    game.value = await api.submitAction(sessionId.value, { action, amount })
    maybePoll()
  } catch (e) {
    error.value = e.message
    stopPolling()
  } finally {
    busy.value = false
  }
}

async function nextHand() {
  if (busy.value) return
  error.value = ''
  busy.value = true
  try {
    game.value = await api.nextHand(sessionId.value)
    maybePoll()
  } catch (e) {
    error.value = e.message
    stopPolling()
  } finally {
    busy.value = false
  }
}

function startNewGame() {
  stopPolling()
  game.value = null
  sessionId.value = null
  pendingAction.value = null
  error.value = ''
}

function exitGame() {
  if (window.confirm('确定退出当前对局吗？已结束的手牌会保留在历史中，进行中的这一手将丢弃。')) {
    startNewGame()
  }
}

function openBet() {
  pendingAction.value = 'bet'
  betAmount.value = legal.value.min_bet
}

function openRaise() {
  pendingAction.value = 'raise'
  betAmount.value = legal.value.min_raise_to
}

function cancelAmount() {
  pendingAction.value = null
}

function setMin() {
  betAmount.value = pendingAction.value === 'bet' ? legal.value.min_bet : legal.value.min_raise_to
}

function setMax() {
  betAmount.value = pendingAction.value === 'bet' ? legal.value.max_bet : legal.value.max_raise_to
}

function setPot() {
  const lo = pendingAction.value === 'bet' ? legal.value.min_bet : legal.value.min_raise_to
  const hi = pendingAction.value === 'bet' ? legal.value.max_bet : legal.value.max_raise_to
  betAmount.value = Math.min(hi, Math.max(lo, game.value.pot))
}

async function confirmAmount() {
  const action = pendingAction.value
  pendingAction.value = null
  await act(action, betAmount.value)
}

const amountMin = computed(() =>
  pendingAction.value === 'bet' ? legal.value?.min_bet : legal.value?.min_raise_to,
)
const amountMax = computed(() =>
  pendingAction.value === 'bet' ? legal.value?.max_bet : legal.value?.max_raise_to,
)

function markerLabel(p) {
  if (p.is_button) return '庄'
  if (p.is_small_blind) return '小盲'
  if (p.is_big_blind) return '大盲'
  return ''
}

async function loadReview() {
  const handId = game.value?.last_hand_id
  review.value = null
  if (!handId) return
  try {
    const data = await api.getReview(handId)
    // 仅在仍是同一手且手已结束时写入，避免「下一手」后旧请求回填脏数据。
    if (game.value?.last_hand_id === handId && game.value?.hand_over) {
      review.value = data
    }
  } catch {
    review.value = null
  }
}

async function copyHandId(id) {
  if (!(await copyText(id))) return
  copiedHandId.value = id
  setTimeout(() => {
    if (copiedHandId.value === id) copiedHandId.value = ''
  }, 1500)
}

watch(
  () => [game.value?.hand_over, game.value?.last_hand_id, showReview.value],
  ([over, handId, show]) => {
    if (over && show && handId) loadReview()
    else review.value = null
  },
)

onActivated(maybePoll)
onDeactivated(stopPolling)
onUnmounted(stopPolling)
</script>

<template>
  <div class="game-table">
    <div v-if="!game" class="panel create-form">
      <h2>开始新对局</h2>
      <div class="form-grid">
        <label>
          玩家人数
          <div class="player-count">
            <button
              type="button"
              :class="{ active: form.num_players === 2 }"
              @click="form.num_players = 2"
            >
              2 人
            </button>
            <button
              type="button"
              :class="{ active: form.num_players === 5 }"
              @click="form.num_players = 5"
            >
              5 人
            </button>
            <input v-model.number="form.num_players" type="number" min="2" max="10" />
          </div>
        </label>
        <label>
          目标手数
          <input v-model.number="form.target_hands" type="number" min="1" max="10000" />
        </label>
        <label>
          Bot 策略
          <select v-model="form.bot_strategy">
            <option value="heuristic">启发式（推荐）</option>
            <option value="random">随机</option>
          </select>
        </label>
        <label>
          小盲
          <input v-model.number="form.small_blind" type="number" min="1" />
        </label>
        <label>
          大盲
          <input v-model.number="form.big_blind" type="number" min="1" />
        </label>
        <label>
          初始筹码
          <input v-model.number="form.starting_stack" type="number" min="1" />
        </label>
      </div>
      <p class="hint">真人固定坐 0 号位，其余座位由 Bot 驱动；可选 2 人单挑或 5 人桌。</p>
      <button class="primary" :disabled="busy" @click="createGame">开始对局</button>
    </div>

    <template v-else>
      <div class="table-meta">
        <span>第 {{ game.hand_number }} / {{ game.target_hands }} 手</span>
        <span>{{ game.players.length }} 人桌 · 盲注 {{ game.small_blind }} / {{ game.big_blind }} · {{ streetLabel }}</span>
        <label class="review-toggle">
          <input v-model="showReview" type="checkbox" />
          每手复盘
        </label>
        <button class="quit" @click="exitGame">退出对局</button>
      </div>

      <div class="felt">
        <div class="board-center">
          <div class="board">
            <PlayingCard v-for="(c, i) in game.board" :key="i" :code="c" />
            <span v-if="!game.board.length" class="board-empty">发牌中…</span>
          </div>
          <div class="pot">底池 {{ game.pot }}</div>
        </div>

        <div
          v-for="p in players"
          :key="p.seat"
          class="seat"
          :class="{ 'is-active': game.current_seat === p.seat && !game.hand_over }"
          :style="seatStyle(p.seat)"
        >
          <div class="markers">
            <span v-if="markerLabel(p)" class="marker">{{ markerLabel(p) }}</span>
          </div>
          <div class="cards">
            <PlayingCard v-for="(c, i) in p.hole_cards" :key="i" :code="c" />
            <template v-if="!p.cards_revealed">
              <PlayingCard hidden /><PlayingCard hidden />
            </template>
          </div>
          <div class="name">{{ p.name }}{{ p.is_human ? '（你）' : '' }}</div>
          <div class="stack">筹码 {{ p.stack }}</div>
          <div v-if="p.folded" class="status">已弃牌</div>
          <div v-else-if="p.all_in" class="status">全下</div>
          <div v-if="p.street_bet" class="bet-chip">+{{ p.street_bet }}</div>
          <div v-if="showdownHand(p.seat)" class="showdown-hand">
            <span class="cat">{{ HAND_CATEGORY_CN[showdownHand(p.seat).category] }}</span>
            <div class="cards-small">
              <PlayingCard
                v-for="(c, i) in showdownHand(p.seat).cards"
                :key="i"
                :code="c"
                small
              />
            </div>
          </div>
        </div>
      </div>

      <div class="panel hand-actions">
        <h3>本手动作</h3>
        <div v-if="!handActionGroups.length" class="muted">暂无动作</div>
        <div v-for="g in handActionGroups" :key="g.street" class="ha-street">
          <div class="ha-street-title">{{ STREET_CN[g.street] || g.street }}</div>
          <div v-for="(a, i) in g.items" :key="i" class="ha-line">
            {{ playerNameOf(a.seat) }} {{ actionText(a) }}
          </div>
        </div>
      </div>

      <div v-if="game.hand_over && showReview" class="panel review-panel">
        <h3>本手复盘</h3>
        <p v-if="!review" class="muted">复盘生成中…</p>
        <template v-else>
          <p class="muted">共 {{ review.decisions.length }} 个决策点 · 命中 {{ review.mistake_count }} 处问题</p>
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
              <span class="muted">底池 {{ d.pot }} · 面对下注 {{ d.to_call }}</span>
            </div>
            <div class="review-row">
              <span>你：{{ actionText(d.action) }}</span>
              <span>参考：{{ actionText(d.bot_action) }}</span>
            </div>
            <div class="review-row muted">
              <span>胜率 {{ pct(d.equity) }}</span>
              <span v-if="d.pot_odds != null">赔率 {{ pct(d.pot_odds) }}</span>
              <span v-if="d.call_ev != null">跟注 EV {{ evText(d.call_ev) }}</span>
            </div>
            <div v-for="(m, k) in d.mistakes" :key="k" class="mistake" :class="mistakeClass(m.severity)">
              {{ m.message }}
            </div>
          </div>
        </template>
      </div>

      <div class="controls panel">
        <div v-if="busy" class="thinking">处理中…</div>

        <template v-else-if="game.is_human_turn && !game.hand_over">
          <template v-if="!pendingAction">
            <button v-if="legal.can_fold" class="danger" @click="act('fold')">弃牌</button>
            <button v-if="legal.can_check" @click="act('check')">过牌</button>
            <button v-if="legal.can_call" @click="act('call')">
              跟注 {{ legal.call_amount }}
            </button>
            <button v-if="legal.can_bet" class="primary" @click="openBet">下注</button>
            <button v-if="legal.can_raise" class="primary" @click="openRaise">加注</button>
          </template>
          <template v-else>
            <div class="amount-panel">
              <span class="amount-label">{{ pendingAction === 'bet' ? '下注' : '加注' }}额</span>
              <input
                v-model.number="betAmount"
                type="number"
                :min="amountMin"
                :max="amountMax"
              />
              <span class="range">{{ amountMin }} ~ {{ amountMax }}</span>
              <button @click="setMin">最小</button>
              <button @click="setPot">底池</button>
              <button @click="setMax">全下</button>
              <button class="primary" @click="confirmAmount">确认</button>
              <button @click="cancelAmount">取消</button>
            </div>
          </template>
        </template>

        <template v-else-if="game.hand_over">
          <div class="result">{{ resultText() }}</div>
          <div v-if="game.pot_results && game.pot_results.length" class="pot-results">
            <div v-for="(pr, i) in game.pot_results" :key="i" class="pot-result">
              <template v-if="game.pot_results.length > 1">边池 {{ i + 1 }}：</template>
              <template v-else>底池：</template>
              {{ pr.amount }} 筹码 → {{ pr.winners.map((w) => playerNameOf(w)).join('、') }}
              <span v-if="pr.winners.length > 1" class="muted">
                （{{ pr.winners.map((w) => `${playerNameOf(w)} +${pr.shares[w]}`).join('，') }}）
              </span>
            </div>
          </div>
          <button v-if="!game.session_finished" class="primary" @click="nextHand">下一手</button>
          <template v-else>
            <button class="primary" @click="startNewGame">再开一局</button>
            <button @click="emit('navigate', 'stats')">查看统计</button>
            <button @click="emit('navigate', 'history')">查看历史</button>
          </template>
        </template>

        <div v-else class="thinking">Bot 思考中…</div>
      </div>
    </template>

    <div v-if="error" class="error-banner">{{ error }}</div>
  </div>
</template>

<style scoped>
.game-table {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.create-form h2 {
  margin-top: 0;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  margin-bottom: 12px;
}

.form-grid label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 13px;
  color: var(--muted);
}

.player-count {
  display: flex;
  align-items: center;
  gap: 6px;
}

.player-count button {
  padding: 6px 10px;
  font-size: 13px;
}

.player-count button.active {
  background: var(--ink);
  color: #fff;
  border-color: var(--ink);
}

.player-count input {
  width: 64px;
}

.hint {
  font-size: 13px;
  color: var(--muted);
  margin: 0 0 12px;
}

.table-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  color: var(--muted);
  font-size: 14px;
}

.table-meta span:first-child {
  margin-right: auto;
}

.quit {
  color: var(--danger);
  border-color: #fecaca;
}

.felt {
  position: relative;
  background: radial-gradient(circle at 50% 40%, var(--felt), var(--felt-dark));
  border-radius: 16px;
  min-height: 460px;
  color: #e8f5ec;
}

.board-center {
  position: absolute;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -50%);
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

.board {
  display: flex;
  gap: 6px;
  min-height: 54px;
  align-items: center;
}

.board-empty {
  font-size: 13px;
  opacity: 0.8;
}

.pot {
  font-size: 15px;
  font-weight: 600;
}

.seat {
  position: absolute;
  transform: translate(-50%, -50%);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  min-width: 110px;
}

.seat.is-active .name {
  color: #fde68a;
}

.seat .cards {
  display: flex;
  gap: 4px;
  min-height: 54px;
}

.name {
  font-weight: 600;
}

.stack {
  font-size: 13px;
  opacity: 0.9;
}

.status {
  font-size: 12px;
  color: #fde68a;
}

.bet-chip {
  font-size: 12px;
  background: rgba(0, 0, 0, 0.25);
  border-radius: 999px;
  padding: 2px 8px;
}

.showdown-hand {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  font-size: 12px;
  background: rgba(0, 0, 0, 0.2);
  border-radius: 8px;
  padding: 4px 8px;
}

.showdown-hand .cat {
  font-weight: 700;
  color: #fde68a;
}

.showdown-hand .cards-small {
  display: flex;
  gap: 3px;
}

.markers {
  min-height: 18px;
}

.marker {
  font-size: 11px;
  background: var(--gold);
  color: #fff;
  border-radius: 999px;
  padding: 1px 7px;
}

.hand-actions h3 {
  margin-top: 0;
}

.muted {
  color: var(--muted);
}

.ha-street {
  margin-bottom: 8px;
}

.ha-street-title {
  font-weight: 600;
  color: var(--accent);
  margin-bottom: 3px;
}

.ha-line {
  padding-left: 12px;
  color: #334155;
  font-size: 14px;
}

.controls {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
  justify-content: center;
}

.controls button {
  min-width: 72px;
}

.amount-panel {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.amount-label {
  font-weight: 600;
}

.amount-panel input {
  width: 100px;
}

.range {
  color: var(--muted);
  font-size: 13px;
}

.result {
  font-weight: 600;
  font-size: 16px;
}

.pot-results {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 14px;
}

.pot-result {
  color: #334155;
}

.thinking {
  color: var(--muted);
}

.review-toggle {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 13px;
  color: var(--muted);
  cursor: pointer;
  user-select: none;
}

.review-panel h3 {
  margin-top: 0;
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

.cards-mini {
  display: flex;
  gap: 3px;
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
