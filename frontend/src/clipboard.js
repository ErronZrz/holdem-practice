/** 复制文本到剪贴板：优先 Clipboard API，非安全上下文回退到临时输入框。 */
export async function copyText(text) {
  if (!text) return false
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    return fallbackCopy(text)
  }
}

function fallbackCopy(text) {
  const el = document.createElement('textarea')
  el.value = text
  el.setAttribute('readonly', '')
  el.style.position = 'fixed'
  el.style.top = '-1000px'
  el.style.opacity = '0'
  document.body.appendChild(el)
  el.select()
  let ok = false
  try {
    ok = document.execCommand('copy')
  } catch {
    ok = false
  }
  document.body.removeChild(el)
  return ok
}
