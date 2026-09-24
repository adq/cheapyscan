// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Andrew de Quincey

import { svelte } from '@sveltejs/vite-plugin-svelte'
import { defineConfig } from 'vite'

// `npm run dev` serves the UI with hot reload and passes /api through to a
// host started separately with `uv run cheapyscan serve --no-browser`.
export default defineConfig({
  plugins: [svelte()],
  server: {
    proxy: {
      '/api': { target: 'http://127.0.0.1:8080', ws: true },
    },
  },
  build: {
    chunkSizeWarningLimit: 900,
  },
})
