import { useEffect, useState } from 'react'

function parseTyped(text) {
  let s = String(text).replace(/[$\s]/g, '')
  if (!s) return ''
  const hasDot = s.includes('.')
  const hasComma = s.includes(',')
  if (hasDot && hasComma) {
    s = s.lastIndexOf(',') > s.lastIndexOf('.')
      ? s.replace(/\./g, '').replace(',', '.')
      : s.replace(/,/g, '')
  } else if (hasComma) {
    const [head, tail] = s.split(',')
    if (!/^\d*$/.test(head) || !/^\d*$/.test(tail)) return null
    s = tail.length === 3 ? head + tail : `${head}.${tail.slice(0, 2)}`
  } else {
    const parts = s.split('.')
    if (parts.some((p, i) => i > 0 && !/^\d*$/.test(p)) || !/^-?\d*(\.\d*)?$/.test(s)) {
      if (/^\d+(\.\d*)?$/.test(s)) {
        s = parts.length > 2 || (parts.length === 2 && parts[1].length === 3)
          ? parts.join('')
          : s
      } else {
        return null
      }
    }
  }
  const n = Number(s)
  return Number.isFinite(n) ? String(n) : null
}

export default function MoneyInput({ value, onChange, ...rest }) {
  const format = (v) =>
    v === '' || v == null
      ? ''
      : Number(v).toLocaleString('es-CO', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

  const [text, setText] = useState(() => format(value))

  useEffect(() => { setText(format(value)) }, [value])

  return (
    <input
      {...rest}
      inputMode="decimal"
      value={text}
      onChange={(e) => {
        const raw = parseTyped(e.target.value)
        setText(raw === null ? text : raw === '' ? '' : format(raw))
        if (raw !== null) onChange(raw)
      }}
      onFocus={(e) => e.target.select()}
    />
  )
}
