import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/query': 'http://localhost:8006',
      '/health': 'http://localhost:8006',
      '/graph': 'http://localhost:8006',
      '/audit': 'http://localhost:8006',
    }
  }
})
