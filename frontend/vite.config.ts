import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// dev: Vite на 5173 проксирует API-пути на бэкенд (в проде — same-origin
// статика из frontend/dist, которую монтирует FastAPI)
const API = 'http://127.0.0.1:8001'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/sessions': API,
      '/runs': API,
      '/health': API,
    },
  },
})
