// SPEC 11.2. Vercel runs `cd web && npm run build` and publishes web/dist.
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: 'dist',
  },
});
