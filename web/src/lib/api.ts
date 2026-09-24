// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Andrew de Quincey
//
// Types and calls for the host API (host/cheapyscan/api). The shapes mirror
// the pydantic models in host/cheapyscan/config.py and the dicts returned by
// host/cheapyscan/rig.py.

export type AxisName = 'rotor' | 'turntable'

export interface Angles {
  theta: number
  phi: number
}

export interface ScanSnapshot {
  project: string
  scan_index: number
  state: 'running' | 'paused' | 'cancelling' | 'completed' | 'cancelled' | 'failed'
  phase: 'starting' | 'moving' | 'settling' | 'capturing' | 'returning' | 'stopped'
  current_step: number
  total_steps: number
  eta_s: number | null
  last_photo: string | null
  error: string | null
}

export interface Status {
  connected: boolean
  simulate: boolean
  port: string | null
  referenced: boolean
  moving: boolean
  angles: Angles | null
  hold: Record<AxisName, boolean> | null
  camera: { backend: string; connected: boolean }
  scan: ScanSnapshot | null
}

export interface AxisSettings {
  firmware_axis: 'X' | 'Y'
  steps_per_rev: number
  invert: boolean
  min_angle: number
  max_angle: number
  rate: number
  reference_angle: number
}

export interface ScanSettings {
  points: number
  min_theta: number
  max_theta: number
  min_phi: number
  max_phi: number
  optimize_path: boolean
  settle_ms: number
}

export interface Settings {
  serial_port: string | null
  rotor: AxisSettings
  turntable: AxisSettings
  camera: { backend: string; options: Record<string, unknown> }
  projects_dir: string
  end_position: Angles
  scan_defaults: ScanSettings
}

export interface PathEntry {
  execution_step: number
  original_step: number
  theta: number
  phi: number
  cartesian: { x: number; y: number; z: number }
}

export interface PathPreview {
  points: PathEntry[]
  move_time_s: number
  settle_time_s: number
}

export interface ScanRecord {
  index: number
  project: string
  settings: ScanSettings
  status: string
  current_step: number
  total_steps: number
  created: number
  updated?: number
  finished?: number
  duration_s: number
  error?: string | null
  photo_count: number
  camera_backend?: string
}

export interface ProjectSummary {
  name: string
  description: string
  created: number
  scan_count: number
  photo_count: number
  has_thumbnail: boolean
}

export interface ProjectDetail extends ProjectSummary {
  scans: ScanRecord[]
}

export interface ScanDetail extends ScanRecord {
  photos: string[]
}

export interface SerialPort {
  device: string
  description: string
  likely: boolean
}

export interface CameraBackend {
  description: string
  default_options: Record<string, unknown>
}

export class ApiError extends Error {}

async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`/api${path}`, {
    method,
    headers: body === undefined ? {} : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`
    try {
      const j = await res.json()
      if (typeof j.detail === 'string') detail = j.detail
      else if (Array.isArray(j.detail))
        detail = j.detail.map((d: { loc: string[]; msg: string }) => `${d.loc.slice(1).join('.')}: ${d.msg}`).join('; ')
    } catch {
      // not JSON; keep the status text
    }
    throw new ApiError(detail)
  }
  return (await res.json()) as T
}

const enc = encodeURIComponent

export const api = {
  status: () => call<Status>('GET', '/status'),
  config: () => call<Settings>('GET', '/config'),
  saveConfig: (s: Settings) => call<Settings>('PUT', '/config', s),
  serialPorts: () => call<SerialPort[]>('GET', '/serial-ports'),
  connect: () => call<Status>('POST', '/device/connect'),
  disconnect: () => call<Status>('POST', '/device/disconnect'),

  move: (a: Partial<Angles>) => call<Status>('POST', '/motors/move', a),
  jog: (axis: AxisName, degrees: number) => call<Status>('POST', '/motors/jog', { axis, degrees }),
  reference: () => call<Status>('POST', '/motors/reference'),
  hold: (axis: AxisName, on: boolean) => call<Status>('POST', '/motors/hold', { axis, on }),
  abort: () => call<Status>('POST', '/motors/abort'),

  cameraBackends: () => call<Record<string, CameraBackend>>('GET', '/camera/backends'),
  cameraInfo: () => call<Record<string, unknown>>('GET', '/camera/info'),
  testCapture: () => call<{ files: string[] }>('POST', '/camera/test-capture'),
  testPhotoUrl: (f: string) => `/api/camera/test-photos/${enc(f)}`,

  previewPath: (s: ScanSettings) => call<PathPreview>('POST', '/path/preview', s),

  projects: () => call<ProjectSummary[]>('GET', '/projects'),
  createProject: (name: string, description = '') =>
    call<ProjectSummary>('POST', '/projects', { name, description }),
  project: (name: string) => call<ProjectDetail>('GET', `/projects/${enc(name)}`),
  deleteProject: (name: string) => call<{ ok: boolean }>('DELETE', `/projects/${enc(name)}`),
  projectThumbUrl: (name: string, bust = 0) => `/api/projects/${enc(name)}/thumbnail?v=${bust}`,
  zipUrl: (name: string, photosOnly = false) =>
    `/api/projects/${enc(name)}/zip${photosOnly ? '?photos_only=true' : ''}`,

  startScan: (project: string, s: ScanSettings) =>
    call<ScanSnapshot>('POST', `/projects/${enc(project)}/scans`, s),
  scan: (project: string, index: number) => call<ScanDetail>('GET', `/projects/${enc(project)}/scans/${index}`),
  deleteScan: (project: string, index: number) =>
    call<{ ok: boolean }>('DELETE', `/projects/${enc(project)}/scans/${index}`),
  scanPath: (project: string, index: number) =>
    call<PathEntry[]>('GET', `/projects/${enc(project)}/scans/${index}/path`),
  pause: (project: string, index: number) =>
    call<ScanSnapshot>('POST', `/projects/${enc(project)}/scans/${index}/pause`),
  resume: (project: string, index: number) =>
    call<ScanSnapshot>('POST', `/projects/${enc(project)}/scans/${index}/resume`),
  cancel: (project: string, index: number) =>
    call<ScanSnapshot>('POST', `/projects/${enc(project)}/scans/${index}/cancel`),
  photoUrl: (project: string, index: number, file: string, size?: 256 | 512) =>
    `/api/projects/${enc(project)}/scans/${index}/photos/${enc(file)}${size ? `?size=${size}` : ''}`,
}

export function isPreviewable(file: string): boolean {
  return /\.(jpe?g|png|tiff?)$/i.test(file)
}

export function formatDuration(s: number | null | undefined): string {
  if (s == null || !isFinite(s)) return '–'
  s = Math.round(s)
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = s % 60
  if (h) return `${h} h ${m} min`
  if (m) return `${m} min ${sec} s`
  return `${sec} s`
}
