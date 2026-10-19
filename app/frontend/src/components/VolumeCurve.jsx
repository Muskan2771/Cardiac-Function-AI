const W = 320
const H = 120
const PAD = { top: 22, right: 10, bottom: 18, left: 10 }

/** Per-frame left-ventricle volume with ED / ES markers and a playback cursor. */
export default function VolumeCurve({ curve, edFrame, esFrame, cursor }) {
  const max = Math.max(...curve)
  const min = Math.min(...curve)
  const span = max - min || 1
  const innerW = W - PAD.left - PAD.right
  const innerH = H - PAD.top - PAD.bottom

  const x = (i) => PAD.left + (curve.length > 1 ? (i / (curve.length - 1)) * innerW : innerW / 2)
  const y = (v) => PAD.top + (1 - (v - min) / span) * innerH

  const points = curve.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ')

  return (
    <figure className="curve">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Left ventricle volume across the video">
        <line x1={PAD.left} x2={W - PAD.right} y1={H - PAD.bottom} y2={H - PAD.bottom} className="curve-axis" />
        <line x1={x(cursor)} x2={x(cursor)} y1={PAD.top - 4} y2={H - PAD.bottom} className="curve-cursor" />
        <polyline points={points} className="curve-line" fill="none" />
        <circle cx={x(edFrame)} cy={y(curve[edFrame])} r="4" className="curve-ed" />
        <circle cx={x(esFrame)} cy={y(curve[esFrame])} r="4" className="curve-es" />
        <text x={x(edFrame)} y={y(curve[edFrame]) - 7} textAnchor="middle" className="curve-label">
          ED
        </text>
        <text x={x(esFrame)} y={y(curve[esFrame]) + 14} textAnchor="middle" className="curve-label">
          ES
        </text>
        <text x={W / 2} y={H - 4} textAnchor="middle" className="curve-label">
          frame
        </text>
      </svg>
      <figcaption>Left ventricle volume per frame (relative units)</figcaption>
    </figure>
  )
}
