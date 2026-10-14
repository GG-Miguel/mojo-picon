import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// In development the API runs apart (uvicorn on :8080); in production it serves this build.
const api = process.env.VITE_API_PROXY ?? 'http://127.0.0.1:8080'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: Object.fromEntries(['/chat', '/day', '/me', '/health'].map((path) => [path, api])),
  },
})
