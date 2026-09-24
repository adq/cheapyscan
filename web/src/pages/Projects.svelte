<!--
SPDX-License-Identifier: MIT
Copyright (c) 2026 Andrew de Quincey

Projects, their scans, and each scan's photos. Three levels, chosen by the
route: #/projects, #/projects/<name>, #/projects/<name>/<scan>.
-->
<script lang="ts">
  import {
    api,
    formatDuration,
    isPreviewable,
    type PathEntry,
    type ProjectDetail,
    type ProjectSummary,
    type ScanDetail,
  } from '../lib/api'
  import { attempt, live } from '../lib/live.svelte'
  import PathView from '../lib/PathView.svelte'
  import { href, route } from '../lib/route.svelte'

  let name = $derived(route.args[0] ?? null)
  let scanIndex = $derived(route.args[1] ? Number(route.args[1]) : null)

  let list = $state<ProjectSummary[]>([])
  let detail = $state<ProjectDetail | null>(null)
  let scan = $state<ScanDetail | null>(null)
  let path = $state<PathEntry[]>([])
  let newName = $state('')
  let lightbox = $state<string | null>(null)
  let bust = $state(Date.now())

  async function load() {
    if (!name) {
      list = (await attempt(() => api.projects())) ?? []
    } else if (scanIndex === null) {
      detail = (await attempt(() => api.project(name!))) ?? null
    } else {
      scan = (await attempt(() => api.scan(name!, scanIndex!))) ?? null
      path = (await attempt(() => api.scanPath(name!, scanIndex!))) ?? []
    }
  }

  $effect(() => {
    void name
    void scanIndex
    load()
  })

  // Reload when a photo lands in whatever is on screen, or a scan changes state.
  $effect(() => {
    void live.photoCount
    void live.status?.scan?.state
    load()
  })

  async function create() {
    const n = newName.trim()
    if (!n) return
    if (await attempt(() => api.createProject(n), `Created project ${n}.`)) {
      newName = ''
      load()
    }
  }

  async function removeProject(n: string) {
    if (!confirm(`Delete project "${n}" and all its photos? This cannot be undone.`)) return
    if (await attempt(() => api.deleteProject(n), `Deleted project ${n}.`)) {
      if (name) location.hash = href('projects')
      else load()
    }
  }

  async function removeScan(n: string, i: number) {
    if (!confirm(`Delete scan ${i} of "${n}" and its photos? This cannot be undone.`)) return
    if (await attempt(() => api.deleteScan(n, i), `Deleted scan ${i}.`)) {
      if (scanIndex !== null) location.hash = href('projects', n)
      else load()
    }
  }

  async function resume(n: string, i: number) {
    if (await attempt(() => api.resume(n, i), 'Scan resumed.')) location.hash = href('scan')
  }

  const fmtDate = (t: number) => new Date(t * 1000).toLocaleString()

  const statusClass = (s: string) =>
    s === 'completed' ? 'good' : s === 'failed' || s === 'interrupted' ? 'bad' : 'warn'
</script>

{#if !name}
  <div class="head">
    <h1>Projects</h1>
    <div class="row">
      <input placeholder="New project name" bind:value={newName} onkeydown={(e) => e.key === 'Enter' && create()} />
      <button onclick={create} disabled={!newName.trim()}>Create</button>
    </div>
  </div>
  <div class="cards">
    {#each list as p}
      <a class="card project" href={href('projects', p.name)}>
        <div class="thumb">
          {#if p.has_thumbnail}<img src={api.projectThumbUrl(p.name, bust)} alt="" />{/if}
        </div>
        <div class="meta">
          <strong>{p.name}</strong>
          <span class="muted">{p.scan_count} scans, {p.photo_count} photos</span>
          <span class="muted small">{fmtDate(p.created)}</span>
        </div>
      </a>
    {:else}
      <p class="muted">No projects yet. Create one here or on the Scan page.</p>
    {/each}
  </div>
{:else if scanIndex === null}
  <nav class="crumbs"><a href={href('projects')}>Projects</a> / {name}</nav>
  {#if detail}
    <div class="head">
      <h1>{detail.name}</h1>
      <div class="row">
        <a class="button" href={api.zipUrl(detail.name)} download>Download zip</a>
        <a class="button" href={api.zipUrl(detail.name, true)} download>Photos only</a>
        <button onclick={() => removeProject(detail!.name)}>Delete project</button>
      </div>
    </div>
    <div class="card">
      <table>
        <thead>
          <tr><th>Scan</th><th>Status</th><th>Photos</th><th>Time</th><th>Started</th><th></th></tr>
        </thead>
        <tbody>
          {#each detail.scans as s}
            <tr>
              <td><a href={href('projects', detail.name, s.index)}>Scan {s.index}</a></td>
              <td><span class="pill {statusClass(s.status)}">{s.status}</span></td>
              <td class="num">{s.photo_count} / {s.total_steps}</td>
              <td class="num">{formatDuration(s.duration_s)}</td>
              <td>{fmtDate(s.created)}</td>
              <td class="actions">
                {#if ['interrupted', 'cancelled', 'failed'].includes(s.status)}
                  <button onclick={() => resume(detail!.name, s.index)}>Resume</button>
                {/if}
                <button onclick={() => removeScan(detail!.name, s.index)}>Delete</button>
              </td>
            </tr>
          {:else}
            <tr><td colspan="6" class="muted">No scans yet. Start one on the Scan page.</td></tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
{:else}
  <nav class="crumbs">
    <a href={href('projects')}>Projects</a> / <a href={href('projects', name)}>{name}</a> / scan {scanIndex}
  </nav>
  {#if scan}
    <div class="head">
      <h1>Scan {scan.index}</h1>
      <div class="row">
        <span class="pill {statusClass(scan.status)}">{scan.status}</span>
        {#if ['interrupted', 'cancelled', 'failed'].includes(scan.status)}
          <button class="primary" onclick={() => resume(name!, scan!.index)}>Resume</button>
        {/if}
        <a class="button" href={`${api.zipUrl(name)}?scans=${scan.index}`} download>Download zip</a>
        <button onclick={() => removeScan(name!, scan!.index)}>Delete scan</button>
      </div>
    </div>
    <div class="scanlayout">
      <div class="card">
        <h2>{scan.photos.length} files</h2>
        <div class="photos">
          {#each scan.photos as f}
            {#if isPreviewable(f)}
              <button class="ph" onclick={() => (lightbox = f)} title={f}>
                <img loading="lazy" src={api.photoUrl(name, scan.index, f, 256)} alt={f} />
                <span>{f}</span>
              </button>
            {:else}
              <a class="ph raw" href={api.photoUrl(name, scan.index, f)} download title={f}>
                <div>{f.split('.').pop()?.toUpperCase()}</div>
                <span>{f}</span>
              </a>
            {/if}
          {/each}
        </div>
      </div>
      <div class="card side">
        <h2>Path</h2>
        <div class="pv"><PathView points={path} completed={scan.current_step} /></div>
        <dl>
          <dt>Photos</dt><dd>{scan.settings.points}</dd>
          <dt>Rotor</dt><dd>{scan.settings.min_theta}° to {scan.settings.max_theta}°</dd>
          <dt>Turntable</dt><dd>{scan.settings.min_phi}° to {scan.settings.max_phi}°</dd>
          <dt>Pause</dt><dd>{scan.settings.settle_ms} ms</dd>
          <dt>Reordered</dt><dd>{scan.settings.optimize_path ? 'yes' : 'no'}</dd>
          <dt>Camera</dt><dd>{scan.camera_backend ?? '–'}</dd>
          {#if scan.error}<dt>Error</dt><dd>{scan.error}</dd>{/if}
        </dl>
      </div>
    </div>
  {/if}
{/if}

{#if lightbox && name && scanIndex !== null}
  <!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions -->
  <div class="lightbox" onclick={() => (lightbox = null)}>
    <img src={api.photoUrl(name, scanIndex, lightbox)} alt={lightbox} />
    <span>{lightbox}</span>
  </div>
{/if}

<svelte:window onkeydown={(e) => e.key === 'Escape' && (lightbox = null)} />

<style>
  .head {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
    margin-bottom: 16px;
  }
  .head h1 {
    margin: 0;
  }
  .crumbs {
    margin-bottom: 8px;
    color: var(--text-muted);
  }
  .cards {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
    gap: 16px;
  }
  .project {
    padding: 0;
    overflow: hidden;
    text-decoration: none;
    color: inherit;
    display: grid;
  }
  .project:hover {
    border-color: var(--border-strong);
  }
  .thumb {
    aspect-ratio: 3 / 2;
    background: var(--surface-2);
  }
  .thumb img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
  }
  .meta {
    padding: 10px 12px;
    display: grid;
    gap: 2px;
  }
  .small {
    font-size: 0.8rem;
  }
  table {
    width: 100%;
    border-collapse: collapse;
  }
  th,
  td {
    text-align: left;
    padding: 8px;
    border-bottom: 1px solid var(--border);
  }
  th {
    font-weight: 500;
    color: var(--text-muted);
    font-size: 0.85rem;
  }
  .actions {
    text-align: right;
    white-space: nowrap;
  }
  .scanlayout {
    display: grid;
    grid-template-columns: 1fr 340px;
    gap: 16px;
    align-items: start;
  }
  .pv {
    height: 280px;
  }
  .photos {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
    gap: 10px;
  }
  .ph {
    display: grid;
    gap: 4px;
    padding: 0;
    border: none;
    background: none;
    text-align: left;
    color: var(--text-muted);
    font-size: 0.75rem;
    text-decoration: none;
  }
  .ph img,
  .ph.raw div {
    width: 100%;
    aspect-ratio: 3 / 2;
    object-fit: cover;
    border-radius: 4px;
    background: var(--surface-2);
    display: block;
  }
  .ph.raw div {
    display: grid;
    place-items: center;
    font-weight: 700;
    color: var(--text-faint);
  }
  .ph span {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-family: var(--mono);
  }
  dl {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 4px 12px;
    font-size: 0.85rem;
    margin: 12px 0 0;
  }
  dt {
    color: var(--text-muted);
  }
  dd {
    margin: 0;
  }
  .lightbox {
    position: fixed;
    inset: 0;
    background: rgb(0 0 0 / 0.85);
    display: grid;
    place-items: center;
    z-index: 20;
    padding: 24px;
    cursor: zoom-out;
  }
  .lightbox img {
    max-width: 100%;
    max-height: calc(100vh - 80px);
  }
  .lightbox span {
    color: #ddd;
    font-family: var(--mono);
  }
  @media (max-width: 860px) {
    .scanlayout {
      grid-template-columns: 1fr;
    }
    table {
      font-size: 0.85rem;
    }
  }
</style>
