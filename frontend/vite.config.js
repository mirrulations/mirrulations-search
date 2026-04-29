import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react-swc'

export default defineConfig({
    plugins: [react()],
    build: {
        target: 'es2022',
        reportCompressedSize: false,
        sourcemap: false,
        cssCodeSplit: false,
    },
    server: {
        proxy: {
            '/search': 'http://127.0.0.1:80',
            '/agencies': 'http://127.0.0.1:80'

        }
    }
})