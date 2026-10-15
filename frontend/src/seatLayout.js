// 座位布局的纯几何：只做数学、不碰 DOM，便于组件、回归检查与浏览器验收脚本共用同一套口径。
// 关键约定：座位盒宽高固定且内容行高确定，因此「模型盒」与「渲染盒」一一对应，可直接用包围盒判定重叠。
// 牌桌正中央的公共牌与底池也占一块固定区域，座位必须躲开它，不能只躲开彼此。

export const MIN_PLAYERS = 2
export const MAX_PLAYERS = 9
export const SUPPORTED_PLAYER_COUNTS = [2, 3, 4, 5, 6, 7, 8, 9]

// 座位整体缩放档：由大到小依次尝试，取第一个可行档，尽量保住可读性。
// 末几档只在窄屏上使用：中央公共牌区宽度固定，座位必须再缩小才能从两侧躲开它。
export const SEAT_SCALES = [1, 0.9, 0.8, 0.72, 0.65, 0.58, 0.52, 0.46, 0.4]
// 人数不超过该值时，优先在座位上展示五张摊牌；几何放不下才改成紧凑行，明细改到控制面板。
export const INLINE_SHOWDOWN_MAX_PLAYERS = MAX_PLAYERS

// 牌桌高度由确定性搜索决定：步长与上下界固定，保证同一输入得到同一结果。
export const FELT_MIN_HEIGHT = 420
export const FELT_MAX_HEIGHT = 900
export const FELT_HEIGHT_STEP = 8
export const FELT_HORIZONTAL_PADDING = 10
// 相邻座位盒至少保留的间距：避免落在「刚好相切」的边界上，给亚像素与字体差异留余量。
export const MIN_SEAT_GAP = 6

// 座位内容行高（px）：每一行始终渲染，内容可为空，因此盒高与座位状态无关。
export const SEAT_ROW_HEIGHTS = {
  markers: 18,
  cards: 54,
  name: 22,
  stack: 20,
  status: 22,
  showdownInline: 62,
  showdownCompact: 22,
}
export const SEAT_ROW_GAP = 4
// 未缩放的基础盒宽度：内联摊牌时最宽的一行是五张 small 牌。
export const SEAT_BASE_WIDTH = { inline: 132, compact: 110 }

// 中央公共牌区：五张牌面横排，下面一行底池文字。翻牌前也按这个满尺寸占位，
// 这样发到河牌时座位不会突然压上去。数字与牌面组件的牌面尺寸一致。
export const BOARD_CARD_WIDTH = 38
export const BOARD_CARD_HEIGHT = 54
export const BOARD_CARD_GAP = 6
export const BOARD_CARD_COUNT = 5
export const BOARD_CENTER_GAP = 8
export const BOARD_POT_HEIGHT = 22
export const BOARD_CENTER_WIDTH =
  BOARD_CARD_WIDTH * BOARD_CARD_COUNT + BOARD_CARD_GAP * (BOARD_CARD_COUNT - 1)
export const BOARD_CENTER_HEIGHT = BOARD_CARD_HEIGHT + BOARD_CENTER_GAP + BOARD_POT_HEIGHT

const SEAT_ROW_COUNT = 6

export function usesInlineShowdown(playerCount) {
  return playerCount <= INLINE_SHOWDOWN_MAX_PLAYERS
}

function baseHeight(inlineShowdown) {
  const rows = SEAT_ROW_HEIGHTS
  const showdown = inlineShowdown ? rows.showdownInline : rows.showdownCompact
  return rows.markers + rows.cards + rows.name + rows.stack + rows.status + showdown
    + SEAT_ROW_GAP * (SEAT_ROW_COUNT - 1)
}

// 未缩放的座位盒；inlineShowdown 仅在人数允许时生效。
export function seatBaseBox(playerCount, inlineShowdown) {
  const inline = inlineShowdown && usesInlineShowdown(playerCount)
  return {
    inline,
    width: inline ? SEAT_BASE_WIDTH.inline : SEAT_BASE_WIDTH.compact,
    height: baseHeight(inline),
  }
}

// 缩放后的座位盒：重叠判定用这个尺寸，CSS 用基础盒 + scale 还原它。
export function seatScaledBox(playerCount, scale, inlineShowdown) {
  const base = seatBaseBox(playerCount, inlineShowdown)
  return { width: base.width * scale, height: base.height * scale, base }
}

// 座位中心：以牌桌中心为心的椭圆，半径按可用空间推导，保证盒子不越界。
export function seatCenters(playerCount, width, height, box) {
  const rx = Math.max(0, (width - box.width) / 2 - FELT_HORIZONTAL_PADDING)
  const ry = Math.max(0, (height - box.height) / 2 - FELT_HORIZONTAL_PADDING)
  const centers = []
  for (let seat = 0; seat < playerCount; seat += 1) {
    const angle = Math.PI / 2 + (seat * (2 * Math.PI)) / playerCount
    centers.push({
      seat,
      x: width / 2 + rx * Math.cos(angle),
      y: height / 2 + ry * Math.sin(angle),
    })
  }
  return centers
}

export function seatRects(centers, box) {
  return centers.map((center) => ({
    seat: center.seat,
    left: center.x - box.width / 2,
    top: center.y - box.height / 2,
    right: center.x + box.width / 2,
    bottom: center.y + box.height / 2,
  }))
}

export function overlappingSeatPairs(rects) {
  const pairs = []
  for (let i = 0; i < rects.length; i += 1) {
    for (let j = i + 1; j < rects.length; j += 1) {
      const a = rects[i]
      const b = rects[j]
      if (a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom) {
        pairs.push([a.seat, b.seat])
      }
    }
  }
  return pairs
}

// 两个轴对齐矩形之间的最小间距：相切或相交时为 0，否则为欧氏距离。
export function rectGap(a, b) {
  const dx = Math.max(0, Math.max(a.left - b.right, b.left - a.right))
  const dy = Math.max(0, Math.max(a.top - b.bottom, b.top - a.bottom))
  return Math.hypot(dx, dy)
}

// 全部座位对里最小的那个间距，用于判定是否留出安全余量。
export function minimumSeatGap(rects) {
  let smallest = Number.POSITIVE_INFINITY
  for (let i = 0; i < rects.length; i += 1) {
    for (let j = i + 1; j < rects.length; j += 1) {
      smallest = Math.min(smallest, rectGap(rects[i], rects[j]))
    }
  }
  return rects.length < 2 ? Number.POSITIVE_INFINITY : smallest
}

// 公共牌区在牌桌内容盒里居中。宽高不随人数或街道变化。
export function boardCenterRect(width, height) {
  const left = (width - BOARD_CENTER_WIDTH) / 2
  const top = (height - BOARD_CENTER_HEIGHT) / 2
  return {
    left,
    top,
    right: left + BOARD_CENTER_WIDTH,
    bottom: top + BOARD_CENTER_HEIGHT,
    width: BOARD_CENTER_WIDTH,
    height: BOARD_CENTER_HEIGHT,
  }
}

// 座位盒到中央公共牌区的最小间距。相交或相切时为 0。
export function minimumBoardGap(rects, board) {
  if (!rects.length || !board) return Number.POSITIVE_INFINITY
  let smallest = Number.POSITIVE_INFINITY
  for (const rect of rects) {
    smallest = Math.min(smallest, rectGap(rect, board))
  }
  return smallest
}

export function seatsOutside(rects, width, height) {
  const tolerance = 0.5
  return rects
    .filter(
      (rect) =>
        rect.left < -tolerance
        || rect.top < -tolerance
        || rect.right > width + tolerance
        || rect.bottom > height + tolerance,
    )
    .map((rect) => rect.seat)
}

// 给定缩放档与摊牌形态，搜索最小的、留有安全间距且不越界的牌桌高度；无解返回 null。
// 安全间距同时约束座位彼此、以及每个座位与中央公共牌区。
export function minimumFeltHeight(playerCount, width, scale, inlineShowdown) {
  const box = seatScaledBox(playerCount, scale, inlineShowdown)
  for (let height = FELT_MIN_HEIGHT; height <= FELT_MAX_HEIGHT; height += FELT_HEIGHT_STEP) {
    const rects = seatRects(seatCenters(playerCount, width, height, box), box)
    const board = boardCenterRect(width, height)
    const clear = minimumSeatGap(rects) >= MIN_SEAT_GAP
      && minimumBoardGap(rects, board) >= MIN_SEAT_GAP
      && !seatsOutside(rects, width, height).length
    if (clear) return height
  }
  return null
}

function assemble(playerCount, width, scale, inlineShowdown, feltHeight, fits) {
  const box = seatScaledBox(playerCount, scale, inlineShowdown)
  const centers = seatCenters(playerCount, width, feltHeight, box)
  const rects = seatRects(centers, box)
  const boardCenter = boardCenterRect(width, feltHeight)
  return {
    playerCount,
    containerWidth: width,
    fits,
    scale,
    inlineShowdown: box.base.inline,
    baseBox: { width: box.base.width, height: box.base.height },
    box: { width: box.width, height: box.height },
    feltHeight,
    // 座位用基础盒定位（CSS 再以中心为原点整体缩放），因此 left/top 与缩放无关。
    seats: centers.map((center) => ({
      seat: center.seat,
      left: center.x - box.base.width / 2,
      top: center.y - box.base.height / 2,
      centerX: center.x,
      centerY: center.y,
    })),
    overlappingPairs: overlappingSeatPairs(rects),
    outsideSeats: seatsOutside(rects, width, feltHeight),
    minimumGap: minimumSeatGap(rects),
    boardCenter,
    boardGap: minimumBoardGap(rects, boardCenter),
  }
}

// 计算整套布局：先在全部缩放档里找能放下五张摊牌的方案，再退到紧凑行。
// 这样人数变多时仍尽量把摊牌牌面留在座位上。全部不可行时返回 fits=false 的尽力布局。
export function computeSeatLayout(playerCount, containerWidth) {
  const width = Math.max(0, Math.round(containerWidth))
  const unsupported = !SUPPORTED_PLAYER_COUNTS.includes(playerCount) || width <= 0
  if (unsupported) {
    return {
      playerCount,
      containerWidth: width,
      fits: false,
      scale: 1,
      inlineShowdown: false,
      baseBox: { width: SEAT_BASE_WIDTH.compact, height: baseHeight(false) },
      box: { width: SEAT_BASE_WIDTH.compact, height: baseHeight(false) },
      feltHeight: FELT_MIN_HEIGHT,
      seats: [],
      overlappingPairs: [],
      outsideSeats: [],
      minimumGap: 0,
      boardCenter: boardCenterRect(width, FELT_MIN_HEIGHT),
      boardGap: 0,
    }
  }
  for (const inlineShowdown of [true, false]) {
    if (inlineShowdown && !usesInlineShowdown(playerCount)) continue
    for (const scale of SEAT_SCALES) {
      const feltHeight = minimumFeltHeight(playerCount, width, scale, inlineShowdown)
      if (feltHeight === null) continue
      return assemble(playerCount, width, scale, inlineShowdown, feltHeight, true)
    }
  }
  const fallbackScale = SEAT_SCALES[SEAT_SCALES.length - 1]
  return assemble(playerCount, width, fallbackScale, false, FELT_MAX_HEIGHT, false)
}
