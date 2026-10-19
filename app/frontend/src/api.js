// Thin client for the FastAPI backend (Contract 3 in the technical document).
//
// In production the backend serves this frontend, so API_URL is empty and all
// requests are same-origin. For local development against a separate backend,
// set VITE_API_URL (see .env.example).
const API_URL = (import.meta.env.VITE_API_URL ?? '').replace(/\/$/, '')

export const apiUrl = (path) => `${API_URL}${path}`

async function readError(response) {
  let detail = null
  try {
    detail = (await response.json()).detail
  } catch {
    // response had no JSON body
  }
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return 'Please choose a video file to analyze.'
  return `Analysis failed (HTTP ${response.status}).`
}

export async function fetchHealth(signal) {
  const response = await fetch(apiUrl('/health'), { signal })
  if (!response.ok) throw new Error(`Health check failed (HTTP ${response.status})`)
  return response.json()
}

export async function analyzeVideo(file, signal) {
  const body = new FormData()
  body.append('file', file)

  let response
  try {
    response = await fetch(apiUrl('/analyze'), { method: 'POST', body, signal })
  } catch (err) {
    if (err.name === 'AbortError') throw err
    throw new Error('Unable to reach the analysis server. Please try again.', { cause: err })
  }
  if (!response.ok) throw new Error(await readError(response))
  return response.json()
}

// "frame_{:04d}.jpg" + 7  ->  "frame_0007.jpg"
export function overlayFrameUrl(result, index) {
  const name = result.frame_pattern.replace(/\{:0(\d+)d\}/, (_, width) =>
    String(index).padStart(Number(width), '0'),
  )
  return apiUrl(`${result.overlay_frames_url}${name}`)
}
