import { useEffect, useRef, useState } from 'react'
import { overlayFrameUrl } from '../api'

/**
 * Plays back the server-rendered overlay frames (echo frame + predicted LV
 * mask) on a canvas. The current frame is owned by the parent so the volume
 * curve can show a matching cursor.
 */
export default function OverlayPlayer({ result, frame, onFrameChange }) {
  const canvasRef = useRef(null)
  const imagesRef = useRef([])
  const [loaded, setLoaded] = useState(0)
  const [playing, setPlaying] = useState(false)

  const total = result.n_frames

  // Preload every overlay frame once per analysis.
  useEffect(() => {
    let cancelled = false
    let done = 0
    const images = Array.from({ length: total }, (_, i) => {
      const img = new Image()
      img.onload = img.onerror = () => {
        done += 1
        if (!cancelled) setLoaded(done)
      }
      img.src = overlayFrameUrl(result, i)
      return img
    })
    imagesRef.current = images
    return () => {
      cancelled = true
    }
  }, [result, total])

  // Paint the current frame.
  useEffect(() => {
    const canvas = canvasRef.current
    const img = imagesRef.current[frame]
    if (!canvas || !img || !img.complete || !img.naturalWidth) return
    if (canvas.width !== img.naturalWidth) {
      canvas.width = img.naturalWidth
      canvas.height = img.naturalHeight
    }
    canvas.getContext('2d').drawImage(img, 0, 0)
  }, [frame, loaded])

  // Advance frames at the video's own frame rate while playing.
  const ready = loaded >= total
  useEffect(() => {
    if (!playing || !ready) return undefined
    const interval = window.setInterval(
      () => onFrameChange((current) => (current + 1) % total),
      1000 / (result.fps || 30),
    )
    return () => window.clearInterval(interval)
  }, [playing, ready, total, result.fps, onFrameChange])

  const marker =
    frame === result.ed_frame ? 'ED' : frame === result.es_frame ? 'ES' : null

  return (
    <div className="player">
      <div className="player-stage">
        <canvas
          ref={canvasRef}
          className="player-canvas"
          role="img"
          aria-label="Echocardiogram frame with the predicted left ventricle outlined"
        />
        {!ready && (
          <div className="player-loading">
            Loading frames {loaded}/{total}
          </div>
        )}
        {marker && <span className={`player-marker marker-${marker}`}>{marker}</span>}
        <span className="player-legend">
          <i /> Predicted left ventricle
        </span>
      </div>

      <div className="player-controls">
        <button
          type="button"
          className="player-button"
          onClick={() => setPlaying((p) => !p)}
          disabled={!ready}
        >
          {playing ? 'Pause' : 'Play'}
        </button>
        <input
          className="player-slider"
          type="range"
          min={0}
          max={total - 1}
          value={frame}
          onChange={(e) => {
            setPlaying(false)
            onFrameChange(Number(e.target.value))
          }}
          aria-label="Frame"
        />
        <span className="player-frame">
          {frame + 1} / {total}
        </span>
      </div>

      <div className="player-jumps">
        <button
          type="button"
          className="link-button"
          onClick={() => {
            setPlaying(false)
            onFrameChange(result.ed_frame)
          }}
        >
          Go to end-diastole (ED)
        </button>
        <button
          type="button"
          className="link-button"
          onClick={() => {
            setPlaying(false)
            onFrameChange(result.es_frame)
          }}
        >
          Go to end-systole (ES)
        </button>
      </div>
    </div>
  )
}
