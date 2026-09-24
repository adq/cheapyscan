<!--
SPDX-License-Identifier: MIT
Copyright (c) 2026 Andrew de Quincey

Manual control: connect, jog, set the reference position, test the camera.
-->
<script lang="ts">
  import { onMount } from 'svelte'
  import { api, isPreviewable, type AxisName, type Settings } from '../lib/api'
  import { attempt, live } from '../lib/live.svelte'
  import PathView from '../lib/PathView.svelte'

  let st = $derived(live.status)
  let cfg = $state<Settings | null>(null)
  let busy = $state(false)
  let goTheta = $state(90)
  let goPhi = $state(0)
  let camInfo = $state<Record<string, unknown> | null>(null)
  let testPhoto = $state<string | null>(null)
  let camBusy = $state(false)

  const steps = [1, 5, 15, 45]
  let scanRunning = $derived(!!st?.scan && ['running', 'paused', 'cancelling'].includes(st.scan.state))
  let canMove = $derived(!!st?.connected && !busy && !scanRunning)

  onMount(async () => {
    cfg = (await attempt(() => api.config())) ?? null
  })

  async function run(fn: () => Promise<unknown>, done?: string) {
    busy = true
    try {
      const r = await attempt(fn, done)
      if (r && typeof r === 'object' && 'connected' in r) live.setStatus(r as never)
    } finally {
      busy = false
    }
  }

  const jog = (axis: AxisName, deg: number) => run(() => api.jog(axis, deg))
  const goto = () => run(() => api.move({ theta: goTheta, phi: goPhi }))

  async function info() {
    camBusy = true
    camInfo = (await attempt(() => api.cameraInfo())) ?? null
    camBusy = false
  }

  async function capture() {
    camBusy = true
    const r = await attempt(() => api.testCapture(), 'Test photo taken.')
    if (r) testPhoto = r.files.find(isPreviewable) ?? r.files[0] ?? null
    camBusy = false
  }

  function fmt(v: number | undefined) {
    return v === undefined ? '–' : v.toFixed(1) + '°'
  }
</script>

<div class="layout">
  <section class="card">
    <h2>Board</h2>
    {#if st?.connected}
      <p>Connected on <span class="num">{st.port}</span>{st.simulate ? ', simulated' : ''}.</p>
      <button onclick={() => run(() => api.disconnect(), 'Disconnected.')} disabled={busy || scanRunning}>Disconnect</button>
    {:else}
      <p class="muted">
        Connecting resets the board, so the motors lose their position. Set the reference again afterwards.
      </p>
      <button class="primary" onclick={() => run(() => api.connect())} disabled={busy}>Connect</button>
    {/if}
  </section>

  <section class="card position">
    <h2>Position</h2>
    <div class="readout">
      <div>
        <span class="label">Rotor (theta)</span>
        <span class="value num">{fmt(st?.angles?.theta)}</span>
      </div>
      <div>
        <span class="label">Turntable (phi)</span>
        <span class="value num">{fmt(st?.angles?.phi)}</span>
      </div>
    </div>
    {#if scanRunning}
      <p class="notice">A scan is controlling the motors. Pause or cancel it on the Scan page to move by hand.</p>
    {/if}

    {#each ['rotor', 'turntable'] as const as axis}
      <div class="jog">
        <span class="axis">{axis === 'rotor' ? 'Rotor' : 'Turntable'}</span>
        <div class="row">
          {#each [...steps].reverse() as s}
            <button onclick={() => jog(axis, -s)} disabled={!canMove}>−{s}°</button>
          {/each}
          <span class="sep"></span>
          {#each steps as s}
            <button onclick={() => jog(axis, s)} disabled={!canMove}>+{s}°</button>
          {/each}
        </div>
        <label class="check hold">
          <input
            type="checkbox"
            checked={st?.hold?.[axis] ?? true}
            disabled={!canMove}
            onchange={(e) => run(() => api.hold(axis, (e.target as HTMLInputElement).checked))}
          />
          Hold when stopped
        </label>
      </div>
    {/each}

    <div class="goto">
      <label class="field">Rotor angle <input type="number" step="0.5" bind:value={goTheta} /></label>
      <label class="field">Turntable angle <input type="number" step="0.5" bind:value={goPhi} /></label>
      <button onclick={goto} disabled={!canMove}>Go to</button>
    </div>
  </section>

  <section class="card view">
    <h2>Pose</h2>
    <div class="pv"><PathView points={[]} current={st?.angles ?? null} /></div>
  </section>

  <section class="card">
    <h2>Reference position</h2>
    <p>
      The rig has no endstops. It counts motor steps from a reference position that you set. Jog the rotor until
      the object sits at <strong>{cfg?.rotor.reference_angle ?? 90}°</strong> (90° is level). Jog the turntable
      until its marked edge is at <strong>{cfg?.turntable.reference_angle ?? 0}°</strong>, facing the camera. Then
      press Set reference.
    </p>
    <p class="muted">Set it again after reconnecting, and whenever an axis may have slipped.</p>
    <button class="primary" onclick={() => run(() => api.reference(), 'Reference set.')} disabled={!canMove}>
      Set reference
    </button>
  </section>

  <section class="card camera">
    <h2>Camera</h2>
    <p class="muted">Backend: {st?.camera.backend ?? '–'}</p>
    <div class="row">
      <button onclick={info} disabled={camBusy}>Check camera</button>
      <button onclick={capture} disabled={camBusy || scanRunning}>Take test photo</button>
    </div>
    {#if camInfo}
      <dl>
        {#each Object.entries(camInfo) as [k, v]}
          <dt>{k}</dt>
          <dd>{String(v)}</dd>
        {/each}
      </dl>
    {/if}
    {#if testPhoto}
      {#if isPreviewable(testPhoto)}
        <a href={api.testPhotoUrl(testPhoto)} target="_blank"><img src={api.testPhotoUrl(testPhoto)} alt="Test" /></a>
      {:else}
        <p>Saved {testPhoto}. This file type has no preview.</p>
      {/if}
    {/if}
  </section>
</div>

<style>
  .layout {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(340px, 1fr));
    gap: 16px;
    align-items: start;
  }
  .position {
    grid-row: span 2;
  }
  .readout {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
    margin-bottom: 16px;
  }
  .readout > div {
    background: var(--surface-2);
    border-radius: 6px;
    padding: 10px 12px;
    display: grid;
  }
  .label {
    font-size: 0.8rem;
    color: var(--text-muted);
  }
  .value {
    font-size: 1.8rem;
    font-weight: 600;
  }
  .jog {
    margin-bottom: 14px;
    display: grid;
    gap: 6px;
  }
  .axis {
    font-weight: 600;
  }
  .jog button {
    padding: 5px 8px;
    min-width: 46px;
    justify-content: center;
  }
  .sep {
    width: 8px;
  }
  .hold {
    font-size: 0.85rem;
    color: var(--text-muted);
  }
  .goto {
    display: grid;
    grid-template-columns: 1fr 1fr auto;
    gap: 10px;
    align-items: end;
    padding-top: 8px;
    border-top: 1px solid var(--border);
  }
  .pv {
    height: 300px;
  }
  dl {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 2px 12px;
    font-size: 0.85rem;
  }
  dt {
    color: var(--text-muted);
  }
  dd {
    margin: 0;
  }
  .camera img {
    margin-top: 12px;
    max-width: 100%;
    border-radius: 6px;
    border: 1px solid var(--border);
  }
  @media (max-width: 480px) {
    .goto {
      grid-template-columns: 1fr 1fr;
    }
  }
</style>
