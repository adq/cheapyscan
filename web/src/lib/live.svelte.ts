// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Andrew de Quincey
//
// One WebSocket to the host, shared by every page. It holds the latest rig
// status and the recent log, and reconnects on its own if the host restarts.

import type { Angles, ScanSnapshot, Status } from './api'

export interface LogLine {
  time: number
  level: 'info' | 'warning' | 'error'
  message: string
}

export interface PhotoEvent {
  project: string
  scan_index: number
  step: number
  execution_step: number
  files: string[]
}

class Live {
  status = $state<Status | null>(null)
  online = $state(false)
  log = $state<LogLine[]>([])
  lastPhoto = $state<PhotoEvent | null>(null)
  // Bumped on every photo, so pages showing a scan's files can reload them.
  photoCount = $state(0)
  private ws: WebSocket | null = null
  private retry = 500

  start() {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${proto}://${location.host}/api/ws`)
    this.ws = ws
    ws.onopen = () => {
      this.online = true
      this.retry = 500
    }
    ws.onclose = () => {
      this.online = false
      setTimeout(() => this.start(), this.retry)
      this.retry = Math.min(this.retry * 2, 5000)
    }
    ws.onmessage = (m) => this.handle(JSON.parse(m.data))
  }

  private handle(ev: { type: string; [k: string]: unknown }) {
    switch (ev.type) {
      case 'status':
        this.status = ev.status as Status
        break
      case 'position':
        if (this.status) {
          this.status.angles = ev.angles as Angles
          this.status.moving = ev.moving as boolean
        }
        break
      case 'scan':
        if (this.status) this.status.scan = ev.scan as ScanSnapshot
        break
      case 'photo':
        this.lastPhoto = ev as unknown as PhotoEvent
        this.photoCount++
        break
      case 'log':
        this.note(ev.level as LogLine['level'], ev.message as string)
        break
    }
  }

  note(level: LogLine['level'], message: string) {
    this.log = [{ time: Date.now(), level, message }, ...this.log].slice(0, 200)
  }

  setStatus(s: Status) {
    this.status = s
  }
}

export const live = new Live()

// Run an API call, put any error in the log, and return undefined on failure.
export async function attempt<T>(fn: () => Promise<T>, done?: string): Promise<T | undefined> {
  try {
    const r = await fn()
    if (done) live.note('info', done)
    return r
  } catch (e) {
    live.note('error', e instanceof Error ? e.message : String(e))
    return undefined
  }
}
