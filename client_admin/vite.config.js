import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 生产构建 base=/admin/，与 FastAPI 的 StaticFiles 挂载点一致；
// dev 模式 Vite 提供 /admin/* 页面并把 /admin/api 代理到后端 3000 端口。
export default defineConfig({
  base: '/admin/',
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/admin/api': 'http://127.0.0.1:3000',
      '/videos': 'http://127.0.0.1:3000',
      '/posters': 'http://127.0.0.1:3000',
    },
  },
  build: {
    outDir: 'dist',
    chunkSizeWarningLimit: 1500,
  },
})
