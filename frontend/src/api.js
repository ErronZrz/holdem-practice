// 后端 API 客户端。开发时经 Vite 代理转发到本地后端，生产可由 VITE_API_BASE 覆盖。

const BASE = import.meta.env.VITE_API_BASE || ''

async function request(path, options = {}) {
  const res = await fetch(BASE + path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = body.detail || detail
    } catch {
      // 忽略非 JSON 响应
    }
    throw new Error(detail)
  }
  return res.json()
}

export const api = {
  createGame(payload) {
    return request('/games', { method: 'POST', body: JSON.stringify(payload) })
  },
  getGame(id) {
    return request(`/games/${id}`)
  },
  submitAction(id, action) {
    return request(`/games/${id}/actions`, {
      method: 'POST',
      body: JSON.stringify(action),
    })
  },
  nextHand(id) {
    return request(`/games/${id}/next-hand`, { method: 'POST' })
  },
  listGames() {
    return request('/games')
  },
  listHands(id) {
    return request(`/games/${id}/hands`)
  },
  getHand(id) {
    return request(`/hands/${id}`)
  },
  getReview(id) {
    return request(`/hands/${id}/review`)
  },
  getStats(id) {
    return request(`/games/${id}/stats`)
  },
}
