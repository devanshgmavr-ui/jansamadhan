import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// Portal unit + component tests (jsdom). Backend calls are mocked per
// test; run with: npm test
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    include: ['src/**/*.test.{js,jsx}'],
  },
})
