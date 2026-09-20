// 座位布局的纯几何回归检查：无新依赖，只用 node 直接跑几何模块。
//
//   node scripts/check-seat-layout.mjs
//
// 检查 2–9 人 × 验收视口矩阵下，座位盒是否两两不相交、留有安全间距且不越出牌桌。
// 该检查只覆盖几何模型；真实渲染另见 scripts/check-seat-layout-browser.mjs。

import {
  computeSeatLayout,
  MIN_SEAT_GAP,
  SUPPORTED_PLAYER_COUNTS,
} from '../src/seatLayout.js'
import { VIEWPORT_MATRIX, expectedFeltWidth } from './viewport-matrix.mjs'

const failures = []

console.log('| 视口 | 宽度 | 牌桌宽度 | 人数 | 牌桌高度 | 缩放 | 摊牌 | 最小间距 | 判定 |')
console.log('|---|---:|---:|---:|---:|---:|---|---:|---|')

for (const viewport of VIEWPORT_MATRIX) {
  const feltWidth = expectedFeltWidth(viewport.width)
  for (const playerCount of SUPPORTED_PLAYER_COUNTS) {
    const layout = computeSeatLayout(playerCount, feltWidth)
    const ok = layout.fits
      && layout.overlappingPairs.length === 0
      && layout.outsideSeats.length === 0
      && layout.minimumGap >= MIN_SEAT_GAP
    if (!ok) {
      failures.push(
        `${viewport.name}(${viewport.width}) ${playerCount} 人：fits=${layout.fits} `
        + `重叠=${layout.overlappingPairs.map((pair) => pair.join('-')).join(' ') || '无'} `
        + `越界=${layout.outsideSeats.join(' ') || '无'} 最小间距=${layout.minimumGap.toFixed(1)}`,
      )
    }
    console.log(
      `| ${viewport.name} | ${viewport.width} | ${feltWidth} | ${playerCount} `
      + `| ${layout.feltHeight} | ${layout.scale} `
      + `| ${layout.inlineShowdown ? '内联' : '紧凑'} `
      + `| ${layout.minimumGap.toFixed(1)} | ${ok ? '通过' : '失败'} |`,
    )
  }
}

if (failures.length) {
  console.error(`\n纯几何回归检查失败：${failures.length} 个组合不可行`)
  for (const failure of failures) console.error(`- ${failure}`)
  process.exitCode = 1
} else {
  const combos = VIEWPORT_MATRIX.length * SUPPORTED_PLAYER_COUNTS.length
  console.log(
    `\n纯几何回归检查通过：${combos} 个（视口 × 人数）组合全部不重叠、留有`
    + ` ≥${MIN_SEAT_GAP}px 间距且不越界。`,
  )
}
