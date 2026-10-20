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
  fold: 'Fold',
  check: 'Check',
  call: 'Call',
  bet: 'Bet',
  raise: 'Raise',
  small_blind: 'SB',
  big_blind: 'BB',
}

export function actionText(action) {
  const label = ACTION_CN[action.action] || action.action
  return action.amount ? `${label} ${action.amount}` : label
}

// 按连续街道把动作收成组，并带上座位名称与是否真人，供时间线分色展示。
export function groupHandActions(actions, players) {
  const bySeat = new Map()
  for (const player of players || []) bySeat.set(player.seat, player)
  const groups = []
  for (const action of actions || []) {
    const player = bySeat.get(action.seat)
    const item = {
      seat: action.seat,
      street: action.street,
      action: action.action,
      amount: action.amount,
      name: player && player.name ? player.name : `座位 ${action.seat}`,
      isHuman: Boolean(player && player.is_human),
    }
    const last = groups[groups.length - 1]
    if (!last || last.street !== action.street) groups.push({ street: action.street, items: [item] })
    else last.items.push(item)
  }
  return groups
}

// 参考分布的一行摘要；只有一项时返回空串，色条展示时留给读屏。
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
