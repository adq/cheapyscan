<!--
SPDX-License-Identifier: MIT
Copyright (c) 2026 Andrew de Quincey

Everything the firmware does not know: axis mapping and calibration, camera
backend, folders and scan defaults. Saved to the host's settings file.
-->
<script lang="ts">
  import { onMount } from 'svelte'
  import { api, type CameraBackend, type SerialPort, type Settings } from '../lib/api'
  import { attempt } from '../lib/live.svelte'

  let cfg = $state<Settings | null>(null)
  let saved = $state('')
  let ports = $state<SerialPort[]>([])
  let backends = $state<Record<string, CameraBackend>>({})
  let saving = $state(false)

  let dirty = $derived(!!cfg && JSON.stringify(cfg) !== saved)

  onMount(async () => {
    const c = await attempt(() => api.config())
    if (c) {
      cfg = c
      saved = JSON.stringify(c)
    }
    ports = (await attempt(() => api.serialPorts())) ?? []
    backends = (await attempt(() => api.cameraBackends())) ?? {}
  })

  async function refreshPorts() {
    ports = (await attempt(() => api.serialPorts())) ?? []
  }

  async function save() {
    if (!cfg) return
    saving = true
    const c = await attempt(() => api.saveConfig($state.snapshot(cfg!)), 'Settings saved.')
    if (c) {
      cfg = c
      saved = JSON.stringify(c)
    }
    saving = false
  }

  function revert() {
    cfg = JSON.parse(saved)
  }

  // Options shown for the chosen backend: its defaults, overridden by saved values.
  let optionKeys = $derived(cfg ? Object.keys(backends[cfg.camera.backend]?.default_options ?? {}) : [])

  function optValue(key: string) {
    const d = backends[cfg!.camera.backend]?.default_options[key]
    return cfg!.camera.options[key] ?? d
  }

  function setOpt(key: string, value: unknown) {
    cfg!.camera.options = { ...cfg!.camera.options, [key]: value }
  }

  const degPerSec = (a: { rate: number; steps_per_rev: number }) => ((a.rate * 360) / a.steps_per_rev).toFixed(1)
</script>

{#if cfg}
  <div class="head">
    <h1>Settings</h1>
    <div class="row">
      <button onclick={revert} disabled={!dirty || saving}>Undo changes</button>
      <button class="primary" onclick={save} disabled={!dirty || saving}>Save</button>
    </div>
  </div>

  <div class="layout">
    <section class="card">
      <h2>Board</h2>
      <label class="field">
        Serial port
        <div class="row">
          <select
            style="flex:1"
            value={cfg.serial_port ?? ''}
            onchange={(e) => (cfg!.serial_port = (e.target as HTMLSelectElement).value || null)}
          >
            <option value="">Find automatically</option>
            {#each ports as p}<option value={p.device}>{p.device} ({p.description})</option>{/each}
            {#if cfg.serial_port && !ports.some((p) => p.device === cfg!.serial_port)}
              <option value={cfg.serial_port}>{cfg.serial_port} (not present)</option>
            {/if}
          </select>
          <button onclick={refreshPorts}>Refresh</button>
        </div>
      </label>
      <p class="muted small">A new port takes effect on the next Connect.</p>
    </section>

    {#each ['rotor', 'turntable'] as const as axis}
      {@const a = cfg[axis]}
      <section class="card">
        <h2>{axis === 'rotor' ? 'Rotor (tilt)' : 'Turntable'}</h2>
        <div class="grid2">
          <label class="field">
            Firmware axis
            <select bind:value={a.firmware_axis}>
              <option value="X">X</option>
              <option value="Y">Y</option>
            </select>
          </label>
          <label class="field">Steps per revolution <input type="number" step="any" bind:value={a.steps_per_rev} /></label>
          <label class="field">Speed (steps/s) <input type="number" min="10" max="4000" bind:value={a.rate} /></label>
          <label class="field">Reference angle (°) <input type="number" step="any" bind:value={a.reference_angle} /></label>
          {#if axis === 'rotor'}
            <label class="field">Lowest angle (°) <input type="number" step="any" bind:value={a.min_angle} /></label>
            <label class="field">Highest angle (°) <input type="number" step="any" bind:value={a.max_angle} /></label>
          {/if}
          <label class="check" style="grid-column: span 2">
            <input type="checkbox" bind:checked={a.invert} /> Reverse direction
          </label>
        </div>
        <p class="muted small">
          {degPerSec(a)}°/s at this speed.
          {#if axis === 'rotor'}
            The OpenScan Classic rotor has a 64:12 gear, so a 200 step motor at 1/16 microstepping makes 17067 steps
            per revolution. The rotor never moves outside the lowest and highest angles.
          {:else}
            The turntable is driven directly, so a 200 step motor at 1/16 microstepping makes 3200 steps per
            revolution.
          {/if}
        </p>
      </section>
    {/each}

    <section class="card">
      <h2>Camera</h2>
      <label class="field">
        Backend
        <select bind:value={cfg.camera.backend}>
          {#each Object.entries(backends) as [k, b]}<option value={k}>{k}: {b.description}</option>{/each}
        </select>
      </label>
      {#if optionKeys.length}
        <div class="grid2 opts">
          {#each optionKeys as k}
            {@const v = optValue(k)}
            {#if typeof v === 'boolean'}
              <label class="check" style="grid-column: span 2">
                <input type="checkbox" checked={v} onchange={(e) => setOpt(k, (e.target as HTMLInputElement).checked)} />
                {k.replaceAll('_', ' ')}
              </label>
            {:else if typeof v === 'number'}
              <label class="field">
                {k.replaceAll('_', ' ')}
                <input type="number" value={v} onchange={(e) => setOpt(k, Number((e.target as HTMLInputElement).value))} />
              </label>
            {:else}
              <label class="field">
                {k.replaceAll('_', ' ')}
                <input value={String(v ?? '')} onchange={(e) => setOpt(k, (e.target as HTMLInputElement).value)} />
              </label>
            {/if}
          {/each}
        </div>
      {/if}
      {#if cfg.camera.backend === 'gphoto2'}
        <p class="muted small">
          Keep on card leaves each photo on the camera's memory card as well as downloading it. Extra file wait is how
          long to wait for the second file when the camera is set to RAW + JPEG.
        </p>
      {/if}
    </section>

    <section class="card">
      <h2>Files and scans</h2>
      <label class="field">Projects folder <input bind:value={cfg.projects_dir} /></label>
      <h3 class="sub">After a scan, move to</h3>
      <div class="grid2">
        <label class="field">Rotor (°) <input type="number" step="any" bind:value={cfg.end_position.theta} /></label>
        <label class="field">Turntable (°) <input type="number" step="any" bind:value={cfg.end_position.phi} /></label>
      </div>
      <h3 class="sub">New scans start with</h3>
      <div class="grid2">
        <label class="field">Photos <input type="number" min="1" max="999" bind:value={cfg.scan_defaults.points} /></label>
        <label class="field">Pause (ms) <input type="number" min="0" bind:value={cfg.scan_defaults.settle_ms} /></label>
        <label class="field">Rotor from (°) <input type="number" bind:value={cfg.scan_defaults.min_theta} /></label>
        <label class="field">Rotor to (°) <input type="number" bind:value={cfg.scan_defaults.max_theta} /></label>
        <label class="field">Turntable from (°) <input type="number" bind:value={cfg.scan_defaults.min_phi} /></label>
        <label class="field">Turntable to (°) <input type="number" bind:value={cfg.scan_defaults.max_phi} /></label>
        <label class="check" style="grid-column: span 2">
          <input type="checkbox" bind:checked={cfg.scan_defaults.optimize_path} /> Reorder for the shortest moves
        </label>
      </div>
    </section>
  </div>
{/if}

<style>
  .head {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
    margin-bottom: 16px;
    position: sticky;
    top: 56px;
    background: var(--bg);
    padding: 6px 0;
    z-index: 2;
  }
  .head h1 {
    margin: 0;
  }
  .layout {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(340px, 1fr));
    gap: 16px;
    align-items: start;
  }
  .small {
    font-size: 0.82rem;
    margin-bottom: 0;
  }
  .sub {
    margin-top: 16px;
    font-size: 0.85rem;
    color: var(--text-muted);
  }
  .opts {
    margin-top: 12px;
  }
</style>
