import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// base: './' makes the built files use relative paths, which works on GitHub Pages
// (together with HashRouter in main.jsx, so refreshing a page never gives a 404).
export default defineConfig({
  plugins: [react()],
  base: './',
})
