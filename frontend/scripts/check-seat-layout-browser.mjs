// 2–9 人 × 验收视口的浏览器实测：读取真实渲染的座位包围盒，断言两两不相交且都在牌桌内。
//
// 前置：后端与前端开发服务器已在运行，且后端使用一次性数据库（不要写真实库）：
//   cd backend && HOLDEM_DB_PATH=<临时库> uv run uvicorn app.main:app --port 8000
//   cd frontend && npm run dev
//
// 运行：
//   node scripts/check-seat-layout-browser.mjs
//
// 依赖 agent-browser CLI（可用 AGENT_BROWSER_BIN 指定可执行文件）。
// 只读：只为渲染创建对局，不写回、不移动任何仓库工件。

import { execFileSync } from 'node:child_process'

import {
  computeSeatLayout,
  minimumSeatGap,
  overlappingSeatPairs,
  SUPPORTED_PLAYER_COUNTS,
} from '../src/seatLayout.js'
import { VIEWPORT_MATRIX, expectedFeltWidth } from './viewport-matrix.mjs'

const BASE_URL = process.env.ACCEPTANCE_BASE_URL || 'http://localhost:5173'
const API_URL = process.env.ACCEPTANCE_API_URL || 'http://localhost:8000'
const BROWSER_BIN = process.env.AGENT_BROWSER_BIN || 'agent-browser'
const GAME_SEED = 20260920
// 实测允许的模型误差：亚像素取整与边框取整都在 1px 内。
const TOLERANCE = 1

function browser(...args) {
  return execFileSync(BROWSER_BIN, args, { encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 })
}

async function createGame(playerCount) {
  const response = await fetch(`${API_URL}/games`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ num_players: playerCount, seed: GAME_SEED }),
  })
  if (!response.ok) {
    throw new Error(`创建对局失败：${response.status} ${await response.text()}`)
  }
  const data = await response.json()
  if (data.players.length !== playerCount) {
    throw new Error(`后端返回座位数 ${data.players.length} ≠ 请求的 ${playerCount}`)
  }
  return data.session_id
}

// 让牌桌直接渲染指定人数的对局：写入本地配置后重新加载页面。
function seedLocalStorage(playerCount, sessionId) {
  const config = JSON.stringify({
    num_players: playerCount,
    big_blind: 10,
    starting_stack: 1000,
  })
  browser(
    'eval',
    `(() => {
      localStorage.setItem('holdem.table.config', ${JSON.stringify(config)});
      localStorage.setItem('holdem.table.session', ${JSON.stringify(sessionId)});
      return 'seeded';
    })()`,
  )
  browser('reload')
  browser('wait', '.seat')
}

const MEASURE_SCRIPT = `(async () => {
  await new Promise((resolve) => setTimeout(resolve, 250));
  const felt = document.querySelector('.felt');
  if (!felt) return JSON.stringify({ error: 'no-felt' });
  const feltRect = felt.getBoundingClientRect();
  const seats = Array.from(document.querySelectorAll('.seat')).map((el) => {
    const rect = el.getBoundingClientRect();
    return {
      seat: Number(el.dataset.seat),
      left: rect.left,
      top: rect.top,
      right: rect.right,
      bottom: rect.bottom,
      width: rect.width,
      height: rect.height,
    };
  });
  return JSON.stringify({
    seats,
    felt: {
      left: feltRect.left,
      top: feltRect.top,
      right: feltRect.right,
      bottom: feltRect.bottom,
      width: feltRect.width,
      height: feltRect.height,
    },
    viewport: { width: window.innerWidth, height: window.innerHeight },
  });
})()`

// CLI 可能把结果当作字符串回显（引号被转义），因此先按原样解析，失败再去掉转义。
function parseEvalOutput(raw) {
  const text = String(raw).trim()
  const start = text.indexOf('{')
  const end = text.lastIndexOf('}')
  if (start < 0 || end <= start) throw new Error(`无法解析测量输出：${text.slice(0, 200)}`)
  const body = text.slice(start, end + 1)
  try {
    return JSON.parse(body)
  } catch {
    return JSON.parse(body.replaceAll('\\"', '"'))
  }
}

function measure() {
  return parseEvalOutput(browser('eval', MEASURE_SCRIPT))
}

function insideFelt(rect, felt) {
  return (
    rect.left >= felt.left - TOLERANCE
    && rect.top >= felt.top - TOLERANCE
    && rect.right <= felt.right + TOLERANCE
    && rect.bottom <= felt.bottom + TOLERANCE
  )
}

const failures = []
const rows = []

async function main() {
  browser('open', BASE_URL)
  for (const playerCount of SUPPORTED_PLAYER_COUNTS) {
    const sessionId = await createGame(playerCount)
    seedLocalStorage(playerCount, sessionId)
    for (const viewport of VIEWPORT_MATRIX) {
      browser('set', 'viewport', String(viewport.width), String(viewport.height))
      const measurement = measure()
      const feltWidth = Math.round(measurement.felt.width)
      const layout = computeSeatLayout(playerCount, feltWidth)
      const expectedWidth = expectedFeltWidth(viewport.width)

      const problems = []
      if (measurement.seats.length !== playerCount) {
        problems.push(`座位数 ${measurement.seats.length} ≠ ${playerCount}`)
      }
      if (Math.abs(feltWidth - expectedWidth) > TOLERANCE) {
        problems.push(`牌桌宽度 ${feltWidth} ≠ 预期 ${expectedWidth}`)
      }
      const pairs = overlappingSeatPairs(measurement.seats)
      if (pairs.length) {
        problems.push(`重叠 ${pairs.map((pair) => pair.join('-')).join(' ')}`)
      }
      const outside = measurement.seats.filter((seat) => !insideFelt(seat, measurement.felt))
      if (outside.length) {
        problems.push(`越界座位 ${outside.map((seat) => seat.seat).join(' ')}`)
      }
      const maxHeight = Math.max(...measurement.seats.map((seat) => seat.height), 0)
      if (maxHeight > layout.box.height + TOLERANCE) {
        problems.push(`实测盒高 ${maxHeight.toFixed(1)} > 模型 ${layout.box.height.toFixed(1)}`)
      }
      const gap = minimumSeatGap(measurement.seats)

      if (problems.length) {
        failures.push(`${playerCount} 人 / ${viewport.name}(${viewport.width})：${problems.join('；')}`)
      }
      rows.push({
        playerCount,
        viewportName: viewport.name,
        viewportWidth: viewport.width,
        feltWidth,
        height: measurement.felt.height,
        seatCount: measurement.seats.length,
        gap,
        maxHeight,
        modelHeight: layout.box.height,
        ok: problems.length === 0,
      })
    }
  }
}

try {
  await main()
} finally {
  browser('close')
}

console.log('| 人数 | 视口 | 视口宽 | 牌桌宽 | 牌桌高 | 座位数 | 最小间距 | 实测盒高 | 模型盒高 | 判定 |')
console.log('|---:|---|---:|---:|---:|---:|---:|---:|---:|---|')
for (const row of rows) {
  console.log(
    `| ${row.playerCount} | ${row.viewportName} | ${row.viewportWidth} | ${row.feltWidth} `
    + `| ${row.height.toFixed(0)} | ${row.seatCount} | ${row.gap.toFixed(1)} `
    + `| ${row.maxHeight.toFixed(1)} | ${row.modelHeight.toFixed(1)} | ${row.ok ? '通过' : '失败'} |`,
  )
}

if (failures.length) {
  console.error(`\n浏览器实测失败：${failures.length} 个组合未通过`)
  for (const failure of failures) console.error(`- ${failure}`)
  process.exitCode = 1
} else {
  console.log(
    `\n浏览器实测通过：${rows.length} 个（人数 × 视口）组合全部座位数正确、两两不相交、`
    + `都在牌桌内且实测盒高不超过模型盒高。`,
  )
}
