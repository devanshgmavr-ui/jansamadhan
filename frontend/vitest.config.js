import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// Unit + component tests (jsdom). No network, no backend: API calls are
// mocked per test. Run with: npm test
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    include: ['src/**/*.test.{js,jsx}'],
  },
})
