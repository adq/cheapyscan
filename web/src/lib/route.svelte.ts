// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Andrew de Quincey
//
// Hash routes: #/scan, #/control, #/settings, #/projects,
// #/projects/<name> and #/projects/<name>/<scan index>.

class Route {
  page = $state('scan')
  args = $state<string[]>([])

  constructor() {
    const read = () => {
      const parts = location.hash.replace(/^#\/?/, '').split('/').filter(Boolean).map(decodeURIComponent)
      this.page = parts[0] || 'scan'
      this.args = parts.slice(1)
    }
    window.addEventListener('hashchange', read)
    read()
  }
}

export const route = new Route()

export function href(...parts: (string | number)[]): string {
  return '#/' + parts.map((p) => encodeURIComponent(String(p))).join('/')
}
