// 复盘参考口径文案：把后端声明的参考/评估版本身份转成面向用户的说明。

// 参考标识与覆盖范围的中文名；未登记的取值原样展示，避免静默猜测。
const REFERENCE_CN = {
  'heuristic-conservative': '启发式-保守',
}

const COVERAGE_CN = {
  'vs-random': 'vs 随机近似',
}

export function referenceText(review) {
  if (!review) return ''
  const name = REFERENCE_CN[review.reference_strategy] || review.reference_strategy
  const coverage = COVERAGE_CN[review.reference_coverage] || review.reference_coverage
  return `参考：${name} v${review.reference_version}（${coverage} · 评估口径 v${review.evaluation_version}）`
}
