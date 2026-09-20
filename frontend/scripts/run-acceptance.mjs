// 一键跑完座位布局验收：起后端（一次性数据库）与前端开发服务器，跑浏览器实测，然后收尾。
//
//   node scripts/run-acceptance.mjs
//
// 后端一律使用一次性数据库（默认 backend/data/acceptance-tmp.db，可用 ACCEPTANCE_DB_PATH 覆盖），
// 因此真实手牌库不会被写入。脚本结束时会关闭两个服务器进程组。

import { execFileSync, spawn } from 'node:child_process'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const repoRoot = path.resolve(here, '..', '..')
const backendDir = path.join(repoRoot, 'backend')
const frontendDir = path.join(repoRoot, 'frontend')
const dbPath = process.env.ACCEPTANCE_DB_PATH
  || path.join(backendDir, 'data', 'acceptance-tmp.db')

const BACKEND_URL = 'http://localhost:8000/health'
const FRONTEND_URL = 'http://localhost:5173/'

function startProcess(label, command, args, cwd, env) {
  const logs = []
  const child = spawn(command, args, {
    cwd,
    env: { ...process.env, ...env },
    stdio: ['ignore', 'pipe', 'pipe'],
    // 独立进程组：便于一次结束整棵子进程树（uv 会再起 python，npm 会再起 vite）。
    detached: true,
  })
  const collect = (chunk) => {
    logs.push(chunk.toString())
    if (logs.length > 200) logs.shift()
  }
  child.stdout.on('data', collect)
  child.stderr.on('data', collect)
  return { label, child, logs }
}

async function waitFor(url, timeoutMs, service) {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url)
      if (response.ok) return
    } catch {
      // 尚未就绪，继续等待。
    }
    if (service.child.exitCode !== null) {
      throw new Error(`${service.label} 提前退出：\n${service.logs.join('')}`)
    }
    await new Promise((resolve) => setTimeout(resolve, 500))
  }
  throw new Error(`等待 ${url} 超时：\n${service.logs.join('')}`)
}

function stopProcess(service) {
  try {
    process.kill(-service.child.pid, 'SIGTERM')
  } catch {
    try {
      service.child.kill('SIGTERM')
    } catch {
      // 进程可能已经结束。
    }
  }
}

const backend = startProcess(
  '后端',
  'uv',
  ['run', 'uvicorn', 'app.main:app', '--port', '8000'],
  backendDir,
  { HOLDEM_DB_PATH: dbPath },
)
const frontend = startProcess('前端', 'npm', ['run', 'dev'], frontendDir, {})

let exitCode = 0
try {
  await waitFor(BACKEND_URL, 60000, backend)
  await waitFor(FRONTEND_URL, 60000, frontend)
  console.log(`后端：${BACKEND_URL}（一次性数据库 ${dbPath}）`)
  console.log(`前端：${FRONTEND_URL}`)
  execFileSync('node', [path.join(here, 'check-seat-layout-browser.mjs')], { stdio: 'inherit' })
} catch (error) {
  exitCode = 1
  console.error(error instanceof Error ? error.message : String(error))
  console.error(`后端日志：\n${backend.logs.join('')}`)
  console.error(`前端日志：\n${frontend.logs.join('')}`)
} finally {
  stopProcess(backend)
  stopProcess(frontend)
}

process.exitCode = exitCode
