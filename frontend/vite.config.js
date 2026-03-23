import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/query': 'https://specified-yolanda-streamlen-ecab5888.koyeb.app',
      '/health': 'https://specified-yolanda-streamlen-ecab5888.koyeb.app',
      '/graph': 'https://specified-yolanda-streamlen-ecab5888.koyeb.app',
      '/audit': 'https://specified-yolanda-streamlen-ecab5888.koyeb.app',
    }
  }
})
