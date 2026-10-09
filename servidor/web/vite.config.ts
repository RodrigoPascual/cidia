import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// En desarrollo, /api, /v1 y /salud se redirigen al gateway (por defecto, un túnel SSH local).
const gateway = process.env.CIDIA_GATEWAY ?? 'http://127.0.0.1:18080'

export default defineConfig({
  base: './',  // rutas relativas: sirve igual en /app/ y en /cidia/gw/app/
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: gateway, changeOrigin: true },
      '/v1': { target: gateway, changeOrigin: true },
      '/salud': { target: gateway, changeOrigin: true },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    chunkSizeWarningLimit: 900,
  },
})
