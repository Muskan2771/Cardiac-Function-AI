import { useEffect, useRef, useState } from 'react'
import './App.css'
import { analyzeVideo, fetchHealth } from './api'
import Results from './components/Results'

const ACCEPTED = ['.avi', '.mp4', '.mov', '.m4v', '.mkv', '.webm']
const MAX_MB = 50

const hasAcceptedExtension = (name) =>
  ACCEPTED.some((ext) => name.toLowerCase().endsWith(ext))

const formatFileSize = (bytes) => (bytes ? `${(bytes / (1024 * 1024)).toFixed(2)} MB` : '')

function App() {
  const fileInputRef = useRef(null)
  const abortRef = useRef(null)

  const [video, setVideo] = useState(null)
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [dragActive, setDragActive] = useState(false)
  const [health, setHealth] = useState(null)

  useEffect(() => {
    const controller = new AbortController()
    fetchHealth(controller.signal)
      .then(setHealth)
      .catch((err) => {
        if (err.name !== 'AbortError') setHealth({ model_loaded: false, unreachable: true })
      })
    return () => controller.abort()
  }, [])

  const selectVideo = (file) => {
    if (!file) return
    if (!hasAcceptedExtension(file.name)) {
      setError('Please choose an echocardiogram video (.avi or .mp4).')
      return
    }
    if (file.size > MAX_MB * 1024 * 1024) {
      setError(`That file is larger than ${MAX_MB} MB.`)
      return
    }
    setVideo(file)
    setResult(null)
    setError('')
  }

  const handleAnalyze = async () => {
    if (!video) {
      setError('Please select an echocardiogram video first.')
      return
    }
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller

    setLoading(true)
    setError('')
    setResult(null)
    try {
      setResult(await analyzeVideo(video, controller.signal))
    } catch (err) {
      if (err.name !== 'AbortError') setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const removeVideo = () => {
    abortRef.current?.abort()
    setVideo(null)
    setResult(null)
    setError('')
    setLoading(false)
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  const demoModel = health?.model_loaded && health.model && !health.model.real_data
  const serviceDown = health && !health.model_loaded

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand">
          <div className="brand-name">Cardiac Function AI</div>
          <div className="brand-divider" />
          <div className="brand-subtitle">Echocardiogram Analysis</div>
        </div>
        <div className="prototype-label">
          <span className="status-dot" />
          Research Prototype
        </div>
      </header>

      {serviceDown && (
        <div className="banner banner-error" role="alert">
          {health.unreachable
            ? 'The analysis server cannot be reached right now.'
            : 'The segmentation model is not loaded on this server, so analysis is unavailable.'}
        </div>
      )}
      {demoModel && (
        <div className="banner banner-warning" role="status">
          <strong>Demo model.</strong> It was trained on {health.model.trained_on}, not on real
          echocardiograms. Results are for demonstration only.
        </div>
      )}

      <main className="main-content">
        <section className="hero">
          <div className="hero-grid" />
          <div className="hero-content">
            <div className="eyebrow">
              <span className="eyebrow-line" />
              CARDIAC FUNCTION ASSESSMENT
              <span className="eyebrow-line" />
            </div>
            <h1>
              Automated cardiac function
              <span> assessment from echocardiography.</span>
            </h1>
            <p>
              Upload an apical four-chamber echocardiogram. The system outlines the left
              ventricle on every frame and estimates the ejection fraction.
            </p>
          </div>
        </section>

        <section className="workspace">
          <div className="analysis-panel">
            <div className="panel-top">
              <div>
                <span className="panel-index">01</span>
                <div>
                  <h2>Upload echocardiogram</h2>
                  <p>Provide an echo video (.avi or .mp4, up to {MAX_MB} MB).</p>
                </div>
              </div>
              <span className="panel-status">{loading ? 'ANALYZING' : 'READY'}</span>
            </div>

            <input
              ref={fileInputRef}
              className="hidden-input"
              type="file"
              accept={ACCEPTED.join(',')}
              onChange={(event) => selectVideo(event.target.files?.[0])}
            />

            {!video ? (
              <div
                className={`drop-zone ${dragActive ? 'drag-active' : ''}`}
                role="button"
                tabIndex={0}
                onDragOver={(event) => {
                  event.preventDefault()
                  setDragActive(true)
                }}
                onDragLeave={() => setDragActive(false)}
                onDrop={(event) => {
                  event.preventDefault()
                  setDragActive(false)
                  selectVideo(event.dataTransfer.files?.[0])
                }}
                onClick={() => fileInputRef.current?.click()}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault()
                    fileInputRef.current?.click()
                  }
                }}
              >
                <div className="scan-decoration">
                  <span />
                  <span />
                  <span />
                </div>
                <div className="upload-symbol">↑</div>
                <h3>Drop echocardiogram video</h3>
                <p>
                  Drag and drop your file here or
                  <strong> browse</strong>
                </p>
                <span className="file-hint">.avi · .mp4 · .mov</span>
              </div>
            ) : (
              <div className="selected-file">
                <div className="file-visual">
                  <div className="play-symbol">▶</div>
                  <span className="file-type">VIDEO</span>
                </div>
                <div className="file-details">
                  <span className="file-label">SELECTED STUDY</span>
                  <strong>{video.name}</strong>
                  <span>{formatFileSize(video.size)}</span>
                </div>
                <button type="button" className="remove-button" onClick={removeVideo}>
                  Remove
                </button>
              </div>
            )}

            {error && (
              <div className="error-message" role="alert">
                <span>!</span>
                {error}
              </div>
            )}

            <button
              type="button"
              className="analyze-button"
              onClick={handleAnalyze}
              disabled={!video || loading || serviceDown}
            >
              {loading ? (
                <>
                  <span className="spinner" />
                  Processing echocardiogram
                  <span className="loading-dots">...</span>
                </>
              ) : (
                <>
                  Analyze echocardiogram
                  <span className="button-arrow">↗</span>
                </>
              )}
            </button>
          </div>

          {result && <Results key={result.request_id} result={result} />}
        </section>
      </main>

      <footer className="footer">
        <span>Cardiac Function AI Assistant</span>
        <span>Screening aid, not a diagnosis · Research prototype</span>
      </footer>
    </div>
  )
}

export default App
