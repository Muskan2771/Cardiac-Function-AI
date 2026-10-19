import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // `npm run dev` proxies API calls to a local backend (uvicorn on :8000),
    // so no VITE_API_URL or CORS setup is needed during development.
    proxy: {
      '/analyze': 'http://127.0.0.1:8000',
      '/health': 'http://127.0.0.1:8000',
      '/static': 'http://127.0.0.1:8000',
    },
  },
})
