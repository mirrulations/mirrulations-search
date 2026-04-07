import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
    plugins: [react()],
    build: {
        // Skips gzip-size step; which should save more time on small/CI/EC2 stuff
        reportCompressedSize: false,
        sourcemap: false,
    },
    server: {
        proxy: {
            '/search': 'http://127.0.0.1:80',
            '/agencies': 'http://127.0.0.1:80'

        }
    }
})