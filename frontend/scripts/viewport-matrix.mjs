// 产品验收用的固定视口矩阵：宽度决定牌桌可用宽度，因此判定只看宽度。
// 高度只用于渲染（页面允许纵向滚动），不参与重叠判定。

export const APP_SHELL_MAX_WIDTH = 960
export const APP_SHELL_PADDING = 16

export const VIEWPORT_MATRIX = [
  { name: 'desktop-wide', width: 1440, height: 900 },
  { name: 'desktop', width: 1280, height: 800 },
  { name: 'laptop', width: 1024, height: 768 },
  { name: 'narrow-laptop', width: 900, height: 900 },
  { name: 'tablet', width: 768, height: 1024 },
  { name: 'small-tablet', width: 600, height: 900 },
  { name: 'large-phone', width: 480, height: 900 },
  { name: 'phone', width: 390, height: 844 },
]

// 设置区为居中定宽容器，牌桌宽度即其内容宽度。
export function expectedFeltWidth(viewportWidth) {
  return Math.min(viewportWidth, APP_SHELL_MAX_WIDTH) - APP_SHELL_PADDING * 2
}
