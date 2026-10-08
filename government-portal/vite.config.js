import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Separate government review interface. The backend target comes from the
// environment; the fallback preserves local development against the default
// local API port. VITE_* values ship in the bundle: never put secrets here.
export default defineConfig({
  plugins: [react()],
  server: { port: 5174 },
  preview: { port: 5174 },
})
