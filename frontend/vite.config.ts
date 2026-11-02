import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// In dev the app talks to the FastAPI backend through this proxy, so no CORS setup is needed.
export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': 'http://127.0.0.1:8000', '/health': 'http://127.0.0.1:8000' } },
})
