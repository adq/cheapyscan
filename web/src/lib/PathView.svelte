<!--
SPDX-License-Identifier: MIT
Copyright (c) 2026 Andrew de Quincey

3D view of the scan path. Each dot is one camera viewpoint on a unit sphere
around the object: theta 0 looks straight down, theta 90 looks level. Dots
already photographed are filled in, and the red ring shows where the rig
points now. The grey block is the object, centred on the turntable. The tick
on the turntable's rim marks 0 degrees, the edge that faces the camera at the
reference position. Drag to orbit, scroll to zoom.
-->
<script lang="ts">
  import { onMount } from 'svelte'
  import * as THREE from 'three'
  import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
  import type { Angles, PathEntry } from './api'

  interface Props {
    points: PathEntry[]
    completed?: number
    current?: Angles | null
  }
  let { points, completed = 0, current = null }: Props = $props()

  let host: HTMLDivElement
  let renderer: THREE.WebGLRenderer | undefined
  let scene: THREE.Scene
  let camera: THREE.PerspectiveCamera
  let controls: OrbitControls
  let pathGroup = new THREE.Group()
  let pose: THREE.Group
  let colors = { pending: '#888', done: '#2a7', next: '#e90', line: '#666', grid: '#444', pose: '#e33', object: '#999' }

  // Scan coordinates have z up; three.js has y up.
  function toVec(theta: number, phi: number, r = 1): THREE.Vector3 {
    const t = (theta * Math.PI) / 180
    const f = (phi * Math.PI) / 180
    return new THREE.Vector3(r * Math.sin(t) * Math.cos(f), r * Math.cos(t), -r * Math.sin(t) * Math.sin(f))
  }

  function readColors() {
    const cs = getComputedStyle(host)
    const v = (n: string, d: string) => cs.getPropertyValue(n).trim() || d
    colors = {
      pending: v('--pv-pending', colors.pending),
      done: v('--pv-done', colors.done),
      next: v('--pv-next', colors.next),
      line: v('--pv-line', colors.line),
      grid: v('--pv-grid', colors.grid),
      pose: v('--pv-pose', colors.pose),
      object: v('--pv-object', colors.object),
    }
  }

  function buildStatic() {
    const grid = new THREE.Group()
    const mat = new THREE.LineBasicMaterial({ color: colors.grid, transparent: true, opacity: 0.5 })
    // Latitude rings every 30 degrees and meridians every 45.
    for (let th = 30; th < 180; th += 30) {
      const pts = []
      for (let f = 0; f <= 360; f += 6) pts.push(toVec(th, f))
      grid.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), mat))
    }
    for (let f = 0; f < 360; f += 45) {
      const pts = []
      for (let th = 0; th <= 180; th += 6) pts.push(toVec(th, f))
      grid.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), mat))
    }
    scene.add(grid)

    // The turntable.
    const disc = new THREE.Mesh(
      new THREE.CylinderGeometry(0.35, 0.35, 0.03, 48),
      new THREE.MeshBasicMaterial({ color: colors.grid, transparent: true, opacity: 0.6 }),
    )
    disc.position.y = -0.1
    scene.add(disc)
    // The object, centred on the turntable at the middle of the sphere.
    const object = new THREE.Mesh(
      new THREE.BoxGeometry(0.16, 0.2, 0.16),
      new THREE.MeshBasicMaterial({ color: colors.object }),
    )
    object.position.set(0, 0.015, 0)
    scene.add(object)
    // A tick on the rim at phi = 0: the edge that faces the camera at the
    // reference position.
    const tick = new THREE.Mesh(
      new THREE.BoxGeometry(0.08, 0.035, 0.02),
      new THREE.MeshBasicMaterial({ color: colors.next }),
    )
    tick.position.set(0.35, -0.1, 0)
    scene.add(tick)

    pose = new THREE.Group()
    const ring = new THREE.Mesh(
      new THREE.TorusGeometry(0.07, 0.012, 8, 32),
      new THREE.MeshBasicMaterial({ color: colors.pose }),
    )
    pose.add(ring)
    scene.add(pose)
    scene.add(pathGroup)
  }

  function rebuildPath() {
    if (!renderer) return
    for (const c of [...pathGroup.children]) {
      pathGroup.remove(c)
      if (c instanceof THREE.Mesh || c instanceof THREE.Line) c.geometry.dispose()
    }
    if (!points.length) return
    const ordered = [...points].sort((a, b) => a.execution_step - b.execution_step)
    const line = new THREE.Line(
      new THREE.BufferGeometry().setFromPoints(ordered.map((p) => toVec(p.theta, p.phi))),
      new THREE.LineBasicMaterial({ color: colors.line, transparent: true, opacity: 0.35 }),
    )
    pathGroup.add(line)
    const geo = new THREE.SphereGeometry(0.022, 10, 8)
    const matPending = new THREE.MeshBasicMaterial({ color: colors.pending })
    const matDone = new THREE.MeshBasicMaterial({ color: colors.done })
    const matNext = new THREE.MeshBasicMaterial({ color: colors.next })
    for (const p of ordered) {
      const state = p.execution_step < completed ? matDone : p.execution_step === completed ? matNext : matPending
      const m = new THREE.Mesh(geo, state)
      if (state === matNext) m.scale.setScalar(1.6)
      m.position.copy(toVec(p.theta, p.phi))
      pathGroup.add(m)
    }
  }

  function placePose() {
    if (!pose) return
    pose.visible = !!current
    if (!current) return
    const v = toVec(current.theta, current.phi, 1.12)
    pose.position.copy(v)
    pose.lookAt(0, 0, 0)
  }

  $effect(() => {
    void points
    void completed
    rebuildPath()
  })

  $effect(() => {
    void current?.theta
    void current?.phi
    placePose()
  })

  onMount(() => {
    readColors()
    scene = new THREE.Scene()
    camera = new THREE.PerspectiveCamera(40, 1, 0.1, 100)
    camera.position.set(2.2, 1.6, 2.6)
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
    } catch {
      host.textContent = 'This browser cannot show the 3D view (WebGL is not available).'
      return
    }
    renderer.setPixelRatio(window.devicePixelRatio)
    host.appendChild(renderer.domElement)
    controls = new OrbitControls(camera, renderer.domElement)
    controls.enableDamping = true
    controls.minDistance = 1.5
    controls.maxDistance = 8
    buildStatic()
    rebuildPath()
    placePose()

    const resize = () => {
      const w = host.clientWidth
      const h = host.clientHeight
      renderer!.setSize(w, h, false)
      camera.aspect = w / Math.max(h, 1)
      camera.updateProjectionMatrix()
    }
    const ro = new ResizeObserver(resize)
    ro.observe(host)
    resize()

    let raf = 0
    const tick = () => {
      controls.update()
      renderer!.render(scene, camera)
      raf = requestAnimationFrame(tick)
    }
    tick()
    return () => {
      cancelAnimationFrame(raf)
      ro.disconnect()
      controls.dispose()
      renderer?.dispose()
    }
  })
</script>

<div class="pathview" bind:this={host}></div>

<style>
  .pathview {
    width: 100%;
    height: 100%;
    min-height: 280px;
    position: relative;
    --pv-pending: var(--text-faint);
    --pv-done: var(--good);
    --pv-next: var(--accent);
    --pv-line: var(--text-faint);
    --pv-grid: var(--border-strong);
    --pv-pose: var(--danger);
    --pv-object: var(--text-muted);
  }
  .pathview :global(canvas) {
    width: 100% !important;
    height: 100% !important;
    display: block;
    touch-action: none;
  }
</style>
