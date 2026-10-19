import { useState } from 'react'
import OverlayPlayer from './OverlayPlayer'
import VolumeCurve from './VolumeCurve'

// Wording follows Section 6.4 of the technical document.
const RISK = {
  Normal: {
    tone: 'normal',
    headline: 'Normal',
    note: 'Ejection fraction is in the normal range (55% or above).',
  },
  'Mildly Reduced': {
    tone: 'mild',
    headline: 'Mildly Reduced — Recommend Clinical Review',
    note: 'Ejection fraction is between 41% and 54%.',
  },
  Reduced: {
    tone: 'reduced',
    headline: 'Reduced — Possible Early HFrEF Signal',
    note: 'Ejection fraction is 40% or below.',
  },
}

const fmt = (n) => Number(n).toLocaleString(undefined, { maximumFractionDigits: 1 })

export default function Results({ result }) {
  const [frame, setFrame] = useState(result.ed_frame)
  const risk = RISK[result.risk_flag] ?? RISK.Reduced

  return (
    <section className="results-panel" aria-live="polite">
      <div className="results-top">
        <div>
          <span className="panel-index">02</span>
          <div>
            <span className="results-eyebrow">ANALYSIS COMPLETE</span>
            <h2>Cardiac function results</h2>
          </div>
        </div>
        <div className="completed-badge">
          <span>✓</span>
          {result.video}
        </div>
      </div>

      {result.warnings.length > 0 && (
        <ul className="warning-list">
          {result.warnings.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      )}

      <div className="results-grid">
        <OverlayPlayer result={result} frame={frame} onFrameChange={setFrame} />

        <div className={`ef-card tone-${risk.tone}`}>
          <span className="metric-label">EJECTION FRACTION</span>
          <div className="ef-value">
            {result.ef_percent}
            <span>%</span>
          </div>
          <div className={`risk-badge tone-${risk.tone}`}>{risk.headline}</div>
          <p>{risk.note}</p>
          <VolumeCurve
            curve={result.volume_curve}
            edFrame={result.ed_frame}
            esFrame={result.es_frame}
            cursor={frame}
          />
        </div>
      </div>

      <div className="metrics-section">
        <div className="metric-card">
          <span className="metric-label">EDV</span>
          <strong>
            {fmt(result.edv)}
            <small>a.u.</small>
          </strong>
          <span className="metric-description">End-diastolic volume</span>
        </div>
        <div className="metric-card">
          <span className="metric-label">ESV</span>
          <strong>
            {fmt(result.esv)}
            <small>a.u.</small>
          </strong>
          <span className="metric-description">End-systolic volume</span>
        </div>
        <div className="metric-card">
          <span className="metric-label">ED FRAME</span>
          <strong>{result.ed_frame + 1}</strong>
          <span className="metric-description">End-diastolic frame</span>
        </div>
        <div className="metric-card">
          <span className="metric-label">ES FRAME</span>
          <strong>{result.es_frame + 1}</strong>
          <span className="metric-description">End-systolic frame</span>
        </div>
      </div>

      <div className="risk-section">
        <div className="risk-marker">!</div>
        <div className="risk-content">
          <div>
            <span className="metric-label">SCREENING AID — NOT A DIAGNOSIS</span>
            <strong>{result.disclaimer}</strong>
          </div>
          <p>
            Volumes are in relative units (a.u., pixel³) rather than millilitres. Ejection
            fraction is a ratio, so it does not depend on the unit.
          </p>
        </div>
      </div>
    </section>
  )
}
