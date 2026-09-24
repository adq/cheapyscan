<!--
SPDX-License-Identifier: MIT
Copyright (c) 2026 Andrew de Quincey

Set up and run a scan. Before a scan the 3D view shows the planned path. During
one it fills in as photos are taken, with the latest photo alongside.
-->
<script lang="ts">
  import { onMount } from 'svelte'
  import {
    api,
    formatDuration,
    isPreviewable,
    type PathEntry,
    type ProjectSummary,
    type ScanSettings,
  } from '../lib/api'
  import { attempt, live } from '../lib/live.svelte'
  import PathView from '../lib/PathView.svelte'
  import { href } from '../lib/route.svelte'

  let st = $derived(live.status)
  let scan = $derived(st?.scan ?? null)
  let active = $derived(!!scan && ['running', 'paused', 'cancelling'].includes(scan.state))

  let settings = $state<ScanSettings | null>(null)
  let projects = $state<ProjectSummary[]>([])
  let project = $state('')
  let newName = $state('')
  let creating = $state(false)
  let starting = $state(false)
  let dismissed = $state(false)

  let preview = $state<{ points: PathEntry[]; move_time_s: number; settle_time_s: number } | null>(null)
  let previewError = $state<string | null>(null)
  let scanPath = $state<PathEntry[]>([])
  let scanPathKey = ''

  let showingScan = $derived(!!scan && (active || !dismissed))

  onMount(async () => {
    const cfg = await attempt(() => api.config())
    if (cfg) settings = { ...cfg.scan_defaults }
    await loadProjects()
  })

  async function loadProjects() {
    projects = (await attempt(() => api.projects())) ?? []
    if (!project && projects.length) project = projects[projects.length - 1].name
  }

  async function createProject() {
    const name = newName.trim()
    if (!name) return
    const p = await attempt(() => api.createProject(name), `Created project ${name}.`)
    if (p) {
      newName = ''
      creating = false
      await loadProjects()
      project = p.name
    }
  }

  // Re-plan the path shortly after the settings stop changing.
  let timer: ReturnType<typeof setTimeout> | undefined
  $effect(() => {
    if (!settings) return
    const s = $state.snapshot(settings)
    void st?.referenced
    clearTimeout(timer)
    timer = setTimeout(async () => {
      try {
        preview = await api.previewPath(s)
        previewError = null
      } catch (e) {
        previewError = e instanceof Error ? e.message : String(e)
      }
    }, 250)
  })

  // Load the running scan's path once per scan.
  $effect(() => {
    if (!scan) return
    const key = `${scan.project}/${scan.scan_index}`
    if (key === scanPathKey) return
    scanPathKey = key
    api.scanPath(scan.project, scan.scan_index).then((p) => (scanPath = p), () => (scanPath = []))
  })

  async function start() {
    if (!settings || !project) return
    starting = true
    const r = await attempt(() => api.startScan(project, $state.snapshot(settings!)), 'Scan started.')
    if (r) dismissed = false
    starting = false
  }

  const control = (fn: typeof api.pause) => scan && attempt(() => fn(scan.project, scan.scan_index))

  let lastPhotoUrl = $derived.by(() => {
    const p = live.lastPhoto
    if (!p || !scan || p.project !== scan.project || p.scan_index !== scan.scan_index) return null
    const f = p.files.find(isPreviewable)
    return f ? api.photoUrl(p.project, p.scan_index, f, 512) : null
  })

  let pct = $derived(scan && scan.total_steps ? (100 * scan.current_step) / scan.total_steps : 0)

  const phaseText: Record<string, string> = {
    starting: 'Starting',
    moving: 'Moving',
    settling: 'Waiting for the object to settle',
    capturing: 'Taking photo',
    returning: 'Returning to the end position',
    stopped: 'Stopped',
  }
  const stateText: Record<string, string> = {
    running: 'Running',
    paused: 'Paused',
    cancelling: 'Cancelling after this photo',
    completed: 'Completed',
    cancelled: 'Cancelled',
    failed: 'Failed',
  }
</script>

<div class="layout">
  <div class="side">
    {#if showingScan && scan}
      <section class="card">
        <h2>{scan.project}, scan {scan.scan_index}</h2>
        <div class="state">
          <span class="pill {scan.state === 'failed' ? 'bad' : scan.state === 'completed' ? 'good' : 'warn'}">
            {stateText[scan.state]}
          </span>
          {#if active}<span class="muted">{phaseText[scan.phase]}</span>{/if}
        </div>
        <div class="bar"><div style:width="{pct}%"></div></div>
        <div class="stats">
          <div><span class="label">Photos</span><span class="num">{scan.current_step} / {scan.total_steps}</span></div>
          <div><span class="label">Time left</span><span class="num">{active ? formatDuration(scan.eta_s) : '–'}</span></div>
        </div>
        {#if scan.error}<p class="notice">{scan.error}</p>{/if}
        <div class="row">
          {#if scan.state === 'running'}
            <button onclick={() => control(api.pause)}>Pause</button>
          {:else if scan.state === 'paused'}
            <button class="primary" onclick={() => control(api.resume)}>Resume</button>
          {/if}
          {#if scan.state === 'running' || scan.state === 'paused'}
            <button onclick={() => control(api.cancel)}>Cancel</button>
          {/if}
          {#if !active}
            {#if scan.state !== 'completed'}
              <button class="primary" onclick={() => control(api.resume)}>Resume from photo {scan.current_step + 1}</button>
            {/if}
            <a class="button" href={href('projects', scan.project, scan.scan_index)}>Open photos</a>
            <button onclick={() => (dismissed = true)}>New scan</button>
          {/if}
        </div>
      </section>
    {:else}
      <section class="card">
        <h2>Project</h2>
        {#if creating || !projects.length}
          <div class="row">
            <input placeholder="New project name" bind:value={newName} onkeydown={(e) => e.key === 'Enter' && createProject()} />
            <button onclick={createProject} disabled={!newName.trim()}>Create</button>
            {#if projects.length}<button onclick={() => (creating = false)}>Back</button>{/if}
          </div>
        {:else}
          <div class="row">
            <select bind:value={project} style="flex:1">
              {#each projects as p}<option value={p.name}>{p.name} ({p.scan_count} scans)</option>{/each}
            </select>
            <button onclick={() => (creating = true)}>New</button>
          </div>
        {/if}
      </section>

      {#if settings}
        <section class="card">
          <h2>Scan settings</h2>
          <div class="grid2">
            <label class="field" style="grid-column: span 2">
              Photos <input type="number" min="1" max="999" bind:value={settings.points} />
            </label>
            <label class="field">Rotor from (°) <input type="number" step="1" bind:value={settings.min_theta} /></label>
            <label class="field">Rotor to (°) <input type="number" step="1" bind:value={settings.max_theta} /></label>
            <label class="field">Turntable from (°) <input type="number" step="1" bind:value={settings.min_phi} /></label>
            <label class="field">Turntable to (°) <input type="number" step="1" bind:value={settings.max_phi} /></label>
            <label class="field" style="grid-column: span 2">
              Pause before each photo (ms) <input type="number" min="0" step="100" bind:value={settings.settle_ms} />
            </label>
            <label class="check" style="grid-column: span 2">
              <input type="checkbox" bind:checked={settings.optimize_path} /> Reorder for the shortest moves
            </label>
          </div>
          <p class="hint muted">
            The rotor angle is the tilt of the object: 90° is level, lower angles look down on it from above.
          </p>
          {#if previewError}
            <p class="notice">{previewError}</p>
          {:else if preview}
            <p class="muted">
              Motor time about {formatDuration(preview.move_time_s + preview.settle_time_s)}, plus the camera's time for
              {preview.points.length} photos.
            </p>
          {/if}
          {#if !st?.connected}
            <p class="notice">Connect the board on the Control page first.</p>
          {:else if !st.referenced}
            <p class="notice">Set the reference position on the Control page first.</p>
          {/if}
          <button
            class="primary start"
            onclick={start}
            disabled={starting || !project || !st?.connected || !st.referenced || !!previewError}
          >
            Start scan
          </button>
        </section>
      {/if}
    {/if}
  </div>

  <section class="card view">
    <div class="viewhead">
      <h2>{showingScan ? 'Progress' : 'Planned path'}</h2>
      <span class="legend muted">
        <i class="done"></i> photographed <i class="next"></i> next <i class="pending"></i> to do <i class="pose"></i> rig now <i class="zero"></i> turntable 0°
      </span>
    </div>
    <div class="pv">
      <PathView
        points={showingScan ? scanPath : (preview?.points ?? [])}
        completed={showingScan && scan ? scan.current_step : -1}
        current={st?.angles ?? null}
      />
    </div>
  </section>

  {#if showingScan}
    <section class="card photo">
      <h2>Latest photo</h2>
      {#if lastPhotoUrl}
        <img src={lastPhotoUrl} alt="Latest capture" />
      {:else}
        <p class="muted">No photo yet.</p>
      {/if}
    </section>
  {/if}
</div>

<style>
  .layout {
    display: grid;
    grid-template-columns: minmax(300px, 380px) 1fr;
    grid-template-areas:
      'side view'
      'side photo';
    gap: 16px;
    align-items: start;
  }
  .side {
    grid-area: side;
    display: grid;
    gap: 16px;
  }
  .view {
    grid-area: view;
  }
  .photo {
    grid-area: photo;
  }
  .pv {
    height: min(60vh, 560px);
  }
  .viewhead {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    flex-wrap: wrap;
    gap: 8px;
  }
  .legend {
    font-size: 0.8rem;
    display: flex;
    gap: 6px;
    align-items: center;
    flex-wrap: wrap;
  }
  .legend i {
    width: 9px;
    height: 9px;
    border-radius: 50%;
    display: inline-block;
    margin-left: 6px;
  }
  .legend .done {
    background: var(--good);
  }
  .legend .next {
    background: var(--accent);
  }
  .legend .pending {
    background: var(--text-faint);
  }
  .legend .pose {
    background: var(--danger);
  }
  .legend .zero {
    background: var(--accent);
    border-radius: 1px;
    height: 5px;
  }
  .state {
    display: flex;
    gap: 10px;
    align-items: center;
    margin-bottom: 12px;
  }
  .bar {
    height: 8px;
    background: var(--surface-2);
    border-radius: 4px;
    overflow: hidden;
    margin-bottom: 12px;
  }
  .bar > div {
    height: 100%;
    background: var(--accent);
    transition: width 0.3s;
  }
  .stats {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
    margin-bottom: 12px;
  }
  .stats > div {
    display: grid;
  }
  .stats .num {
    font-size: 1.3rem;
    font-weight: 600;
  }
  .label {
    font-size: 0.8rem;
    color: var(--text-muted);
  }
  .hint {
    font-size: 0.85rem;
  }
  .start {
    width: 100%;
    justify-content: center;
    padding: 9px;
    margin-top: 4px;
  }
  .photo img {
    max-width: 100%;
    border-radius: 6px;
    display: block;
  }
  .notice {
    margin: 10px 0;
  }
  @media (max-width: 860px) {
    .layout {
      grid-template-columns: 1fr;
      grid-template-areas: 'side' 'view' 'photo';
    }
    .pv {
      height: 360px;
    }
  }
</style>
