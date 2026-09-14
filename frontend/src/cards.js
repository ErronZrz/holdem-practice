// 牌与牌局阶段、动作的中文展示辅助。

const RANKS = {
  2: '2', 3: '3', 4: '4', 5: '5', 6: '6', 7: '7', 8: '8', 9: '9',
  T: '10', J: 'J', Q: 'Q', K: 'K', A: 'A',
}

const SUITS = {
  c: { sym: '♣', red: false },
  d: { sym: '♦', red: true },
  h: { sym: '♥', red: true },
  s: { sym: '♠', red: false },
}

export function cardParts(code) {
  const rank = code[0]
  const suit = SUITS[code[1]]
  if (!suit) return { rank: rank, suit: '', red: false }
  return { rank: RANKS[rank] || rank, suit: suit.sym, red: suit.red }
}

export const STREET_CN = {
  preflop: '翻牌前',
  flop: '翻牌',
  turn: '转牌',
  river: '河牌',
  showdown: '摊牌',
}

export const ACTION_CN = {
  fold: '弃牌',
  check: '过牌',
  call: '跟注',
  bet: '下注',
  raise: '加注',
  small_blind: '小盲',
  big_blind: '大盲',
}

export function actionText(action) {
  const label = ACTION_CN[action.action] || action.action
  return action.amount ? `${label} ${action.amount}` : label
}

// 把复盘的参考动作分布渲染成一行文本；确定性分支（只有一项）返回空串不展示。
export function distributionText(decision) {
  const dist = decision.bot_distribution || []
  if (dist.length <= 1) return ''
  return dist
    .map((item) => `${actionText(item)} ${Math.round(item.probability * 100)}%`)
    .join(' / ')
}

export const HAND_CATEGORY_CN = {
  HIGH_CARD: '高牌',
  ONE_PAIR: '一对',
  TWO_PAIR: '两对',
  THREE_OF_A_KIND: '三条',
  STRAIGHT: '顺子',
  FLUSH: '同花',
  FULL_HOUSE: '葫芦',
  FOUR_OF_A_KIND: '四条',
  STRAIGHT_FLUSH: '同花顺',
}
