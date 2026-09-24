<!--
SPDX-License-Identifier: MIT
Copyright (c) 2026 Andrew de Quincey
-->
<script lang="ts">
  import { api } from './lib/api'
  import { attempt, live } from './lib/live.svelte'
  import { route } from './lib/route.svelte'
  import Control from './pages/Control.svelte'
  import Projects from './pages/Projects.svelte'
  import Scan from './pages/Scan.svelte'
  import Settings from './pages/Settings.svelte'

  const tabs = [
    { id: 'scan', label: 'Scan' },
    { id: 'control', label: 'Control' },
    { id: 'projects', label: 'Projects' },
    { id: 'settings', label: 'Settings' },
  ]

  let st = $derived(live.status)
  let logOpen = $state(false)
  let latest = $derived(live.log[0])
  let showLatest = $state(false)
  let hideTimer: ReturnType<typeof setTimeout> | undefined

  $effect(() => {
    if (!latest) return
    showLatest = true
    clearTimeout(hideTimer)
    hideTimer = setTimeout(() => (showLatest = false), latest.level === 'error' ? 10000 : 4000)
  })

  async function abort() {
    await attempt(() => api.abort(), 'Motors stopped.')
  }

  function fmtTime(t: number) {
    return new Date(t).toLocaleTimeString()
  }
</script>

<div class="shell">
  <header>
    <div class="brand">
      <img src="/favicon.svg" alt="" width="22" height="22" />
      <span>cheapyscan</span>
    </div>
    <nav>
      {#each tabs as t}
        <a href={`#/${t.id}`} class:active={route.page === t.id}>{t.label}</a>
      {/each}
    </nav>
    <div class="status">
      {#if !live.online}
        <span class="pill bad">Host offline</span>
      {:else if st}
        {#if st.connected}
          <span class="pill good" title={st.port ?? ''}>Board{st.simulate ? ' (simulated)' : ''}</span>
          <span class="pill {st.referenced ? 'good' : 'warn'}">{st.referenced ? 'Referenced' : 'Not referenced'}</span>
        {:else}
          <span class="pill bad">Board not connected</span>
        {/if}
        <span class="pill {st.camera.connected ? 'good' : ''}">Camera: {st.camera.backend}</span>
      {/if}
      <button class="danger" onclick={abort} disabled={!st?.connected} title="Stop both motors now">Stop</button>
    </div>
  </header>

  <main>
    {#if route.page === 'scan'}
      <Scan />
    {:else if route.page === 'control'}
      <Control />
    {:else if route.page === 'projects'}
      <Projects />
    {:else if route.page === 'settings'}
      <Settings />
    {/if}
  </main>

  <footer>
    <button class="logtoggle" onclick={() => (logOpen = !logOpen)}>
      Log ({live.log.length}) {logOpen ? '▾' : '▴'}
    </button>
    {#if latest && showLatest && !logOpen}
      <span class="latest {latest.level}">{latest.message}</span>
    {/if}
  </footer>
  {#if logOpen}
    <div class="log">
      {#each live.log as l}
        <div class={l.level}><span class="num muted">{fmtTime(l.time)}</span> {l.message}</div>
      {:else}
        <div class="muted">Nothing yet.</div>
      {/each}
    </div>
  {/if}
</div>

<style>
  .shell {
    min-height: 100vh;
    display: flex;
    flex-direction: column;
  }
  header {
    display: flex;
    align-items: center;
    gap: 20px;
    padding: 10px 20px;
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    position: sticky;
    top: 0;
    z-index: 5;
    flex-wrap: wrap;
  }
  .brand {
    display: flex;
    align-items: center;
    gap: 8px;
    font-weight: 700;
    letter-spacing: -0.02em;
    font-size: 1.05rem;
  }
  nav {
    display: flex;
    gap: 2px;
  }
  nav a {
    padding: 6px 12px;
    border-radius: 6px;
    color: var(--text-muted);
    text-decoration: none;
    font-weight: 500;
  }
  nav a:hover {
    background: var(--surface-2);
  }
  nav a.active {
    color: var(--text);
    background: var(--surface-2);
  }
  .status {
    margin-left: auto;
    display: flex;
    gap: 8px;
    align-items: center;
    flex-wrap: wrap;
  }
  main {
    flex: 1;
    padding: 20px;
    width: 100%;
    max-width: 1400px;
    margin: 0 auto;
  }
  footer {
    position: sticky;
    bottom: 0;
    display: flex;
    gap: 12px;
    align-items: center;
    padding: 6px 20px;
    background: var(--surface);
    border-top: 1px solid var(--border);
    min-height: 38px;
  }
  .logtoggle {
    border: none;
    background: none;
    color: var(--text-muted);
    padding: 2px 4px;
  }
  .latest {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .log {
    position: fixed;
    bottom: 38px;
    left: 0;
    right: 0;
    max-height: 40vh;
    overflow: auto;
    background: var(--surface);
    border-top: 1px solid var(--border);
    padding: 8px 20px;
    font-size: 0.85rem;
    z-index: 6;
  }
  .error {
    color: var(--danger);
  }
  .warning {
    color: var(--warn);
  }
  @media (max-width: 700px) {
    header,
    main,
    footer {
      padding-left: 16px;
      padding-right: 16px;
    }
    .status {
      margin-left: 0;
    }
  }
</style>
