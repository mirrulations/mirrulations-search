import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react-swc'

export default defineConfig({
    plugins: [react()],
    build: {
        // Fewer downlevel transforms than default; modern browsers / internal app
        target: 'es2022',
        // Skips gzip-size step — saves time on small EC2
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