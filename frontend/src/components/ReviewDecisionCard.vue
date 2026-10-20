<script setup>
import { computed } from 'vue'
import { actionText, distributionText } from '../cards.js'
import ActionChip from './ActionChip.vue'
import PlayingCard from './PlayingCard.vue'
import StreetBadge from './StreetBadge.vue'

const props = defineProps({
  decision: { type: Object, required: true },
  coach: { type: Object, default: null },
})

const sameType = computed(() => props.decision.action.action === props.decision.bot_action.action)
const distribution = computed(() => props.decision.bot_distribution || [])
const showDistribution = computed(() => distribution.value.length > 1)
const distributionLabel = computed(() => distributionText(props.decision))

function pct(value) {
  return value == null ? '—' : `${(value * 100).toFixed(0)}%`
}

function evText(value) {
  if (value == null) return '—'
  return (value > 0 ? '+' : '') + value
}

function evTone(value) {
  if (value > 0) return 'ev-pos'
  if (value < 0) return 'ev-neg'
  return 'ev-zero'
}

function mistakeClass(severity) {
  return { error: 'mistake-error', warning: 'mistake-warning', info: 'mistake-info' }[severity] || ''
}

function shareOf(item) {
  return Math.round(item.probability * 100)
}

function segmentLabel(item) {
  return `${actionText(item)} ${shareOf(item)}%`
}
</script>

<template>
  <article class="review-decision" :class="sameType ? 'is-same' : 'is-diff'">
    <header class="rd-head">
      <div class="rd-identity">
        <StreetBadge :street="decision.street" />
        <span v-if="decision.board.length" class="cards-mini">
          <PlayingCard v-for="(c, j) in decision.board" :key="j" :code="c" small />
        </span>
      </div>
      <div class="rd-pills">
        <span class="meta-pill">
          <span class="meta-k">底池</span>
          <span class="meta-v num">{{ decision.pot }}</span>
        </span>
        <span class="meta-pill">
          <span class="meta-k">完整欠注</span>
          <span class="meta-v num">{{ decision.to_call }}</span>
        </span>
        <span v-if="decision.is_short_all_in_call" class="meta-pill meta-pill-warn">
          <span class="meta-k">短码全下</span>
          <span class="meta-v num">{{ decision.actual_call_amount }}</span>
        </span>
      </div>
    </header>

    <div class="rd-compare" :class="sameType ? 'is-same' : 'is-diff'">
      <div class="rd-side">
        <span class="rd-kicker">你的动作</span>
        <span class="rd-play">
          <ActionChip :action="decision.action.action" :amount="decision.action.amount" />
          <span class="remain">剩余 <span class="num">{{ decision.stack_after }}</span></span>
        </span>
      </div>
      <div class="rd-mark">{{ sameType ? '同类型' : '不同类型' }}</div>
      <div class="rd-side">
        <span class="rd-kicker">参考动作</span>
        <ActionChip :action="decision.bot_action.action" :amount="decision.bot_action.amount" />
      </div>
    </div>

    <div v-if="showDistribution" class="rd-dist">
      <div class="rd-dist-label">参考分布</div>
      <div class="dist-legend" role="img" :aria-label="distributionLabel">
        <ActionChip
          v-for="(item, idx) in distribution"
          :key="idx"
          :action="item.action"
          :amount="item.amount"
          :share="shareOf(item)"
          :title="segmentLabel(item)"
        />
      </div>
    </div>

    <div class="rd-metrics">
      <div class="metric">
        <span class="metric-label">胜率</span>
        <span class="metric-value num">{{ pct(decision.equity) }}</span>
      </div>
      <div v-if="decision.pot_odds != null" class="metric">
        <span class="metric-label">底池赔率</span>
        <span class="metric-value num">{{ pct(decision.pot_odds) }}</span>
      </div>
      <div v-if="decision.call_ev != null" class="metric" :class="evTone(decision.call_ev)">
        <span class="metric-label">跟注 EV</span>
        <span class="metric-value num">{{ evText(decision.call_ev) }}</span>
      </div>
    </div>

    <div
      v-for="(m, k) in decision.mistakes"
      :key="k"
      class="mistake"
      :class="mistakeClass(m.severity)"
    >
      {{ m.message }}
    </div>
    <div v-if="coach" class="coach-note">
      <div>{{ coach.explanation }}</div>
      <div class="coach-meta">{{ coach.model }} · {{ coach.cached ? '已缓存' : '新生成' }}</div>
    </div>
  </article>
</template>

<style scoped>
.review-decision {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  background: #fff;
}

.review-decision.is-diff {
  border-color: #fde68a;
}

.rd-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px 12px;
  flex-wrap: wrap;
}

.rd-identity,
.rd-pills,
.dist-legend {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}

.cards-mini {
  display: flex;
  gap: 3px;
}

.meta-pill {
  display: inline-flex;
  align-items: baseline;
  gap: 4px;
  padding: 3px 8px;
  border: 1px solid #e2e8f0;
  border-radius: 999px;
  background: #f8fafc;
  font-size: 12px;
}

.meta-k {
  color: var(--muted);
}

.meta-v {
  font-weight: 800;
  color: #0f172a;
}

.meta-pill-warn {
  background: #fff7ed;
  border-color: #fed7aa;
}

.rd-compare {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
  gap: 8px;
  align-items: stretch;
}

.rd-side {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 6px;
  min-width: 0;
  padding: 8px 10px;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  background: #f8fafc;
}

.rd-compare.is-same .rd-side {
  border-color: #bbf7d0;
  background: #f0fdf4;
}

.rd-compare.is-diff .rd-side:first-child {
  border-color: #fcd34d;
  background: #fffbeb;
}

.rd-kicker {
  font-size: 11px;
  font-weight: 700;
  color: var(--muted);
}

.rd-play {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.remain {
  font-size: 12px;
  font-weight: 700;
  color: #475569;
}

.rd-mark {
  align-self: center;
  border-radius: 999px;
  padding: 3px 6px;
  font-size: 11px;
  font-weight: 800;
  white-space: nowrap;
}

.rd-compare.is-same .rd-mark {
  color: #047857;
  background: #d1fae5;
}

.rd-compare.is-diff .rd-mark {
  color: #b45309;
  background: #fef3c7;
}

.rd-dist {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.rd-dist-label {
  font-size: 11px;
  font-weight: 700;
  color: var(--muted);
}

.rd-metrics {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(96px, 1fr));
  gap: 8px;
}

.metric {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 8px 10px;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  background: #f8fafc;
}

.metric-label {
  font-size: 11px;
  font-weight: 700;
  color: var(--muted);
}

.metric-value {
  font-size: 16px;
  font-weight: 800;
  color: #0f172a;
}

.metric.ev-pos {
  background: #f0fdf4;
  border-color: #bbf7d0;
}

.metric.ev-pos .metric-value {
  color: #15803d;
}

.metric.ev-neg {
  background: #fef2f2;
  border-color: #fecaca;
}

.metric.ev-neg .metric-value {
  color: #b91c1c;
}

.metric.ev-zero .metric-value {
  color: #475569;
}

.mistake {
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

.coach-note {
  padding: 6px 8px;
  border-radius: 6px;
  background: #f8fafc;
  font-size: 13px;
  color: #1e293b;
  line-height: 1.5;
  white-space: pre-wrap;
}

.coach-meta {
  color: var(--muted);
}

@media (max-width: 560px) {
  .rd-compare {
    grid-template-columns: 1fr;
  }

  .rd-mark {
    justify-self: start;
  }
}
</style>
