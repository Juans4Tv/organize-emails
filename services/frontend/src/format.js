export const fmtMoney = (n) =>
  Number(n ?? 0).toLocaleString('es-CO', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

export const fmtCompact = (n) =>
  Number(n ?? 0).toLocaleString('es-CO', { notation: 'compact', maximumFractionDigits: 1 })
