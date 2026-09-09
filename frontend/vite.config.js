import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: {
      '/games': 'http://localhost:8000',
      '/hands': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
    },
  },
})
