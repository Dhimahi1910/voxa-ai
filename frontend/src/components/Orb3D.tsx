import { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import { prefersReducedMotion } from '../hooks'

const VERT = /* glsl */ `
uniform float uTime; uniform float uAmp;
varying vec3 vNormal; varying vec3 vPos; varying float vNoise;
float hash(vec3 p){ p=fract(p*0.3183099+.1); p*=17.0; return fract(p.x*p.y*p.z*(p.x+p.y+p.z)); }
float noise(vec3 x){ vec3 i=floor(x); vec3 f=fract(x); f=f*f*(3.0-2.0*f);
  return mix(mix(mix(hash(i),hash(i+vec3(1,0,0)),f.x), mix(hash(i+vec3(0,1,0)),hash(i+vec3(1,1,0)),f.x),f.y),
             mix(mix(hash(i+vec3(0,0,1)),hash(i+vec3(1,0,1)),f.x), mix(hash(i+vec3(0,1,1)),hash(i+vec3(1,1,1)),f.x),f.y),f.z); }
void main(){
  vNormal = normalize(normalMatrix * normal);
  float n = noise(normal * 1.9 + uTime * 0.35); vNoise = n;
  vec3 p = position + normal * (n - 0.5) * uAmp;
  vec4 mv = modelViewMatrix * vec4(p, 1.0); vPos = mv.xyz;
  gl_Position = projectionMatrix * mv;
}`

const FRAG = /* glsl */ `
varying vec3 vNormal; varying vec3 vPos; varying float vNoise;
void main(){
  vec3 V = normalize(-vPos);
  float fres = pow(1.0 - max(dot(normalize(vNormal), V), 0.0), 2.2);
  vec3 violet = vec3(0.55,0.42,1.0); vec3 teal = vec3(0.18,0.89,0.79); vec3 deep = vec3(0.04,0.05,0.18);
  vec3 col = mix(deep, mix(violet, teal, vNoise), 0.5 + 0.5 * fres);
  col += fres * vec3(0.6,0.78,1.0) * 0.9;
  gl_FragColor = vec4(col, 0.55 + 0.45 * fres);
}`

/**
 * A living 3D orb. `intensity` (0..1) drives how strongly it pulses, e.g. more activity -> livelier.
 * Falls back to a CSS orb if WebGL is unavailable, and renders a still frame for reduced-motion users.
 */
export default function Orb3D({ intensity = 0.3 }: { intensity?: number }) {
  const host = useRef<HTMLDivElement>(null)
  const level = useRef(intensity)
  const [fallback, setFallback] = useState(false)
  useEffect(() => { level.current = intensity }, [intensity])

  useEffect(() => {
    const el = host.current
    if (!el) return
    let renderer: THREE.WebGLRenderer
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'low-power' })
    } catch { setFallback(true); return }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    el.appendChild(renderer.domElement)

    const scene = new THREE.Scene()
    const camera = new THREE.PerspectiveCamera(40, 1, 0.1, 50)
    camera.position.z = 5.2

    const uniforms = { uTime: { value: 0 }, uAmp: { value: 0.35 } }
    const core = new THREE.Mesh(
      new THREE.IcosahedronGeometry(1.25, 24),
      new THREE.ShaderMaterial({ vertexShader: VERT, fragmentShader: FRAG, uniforms, transparent: true }),
    )
    const ring = new THREE.Mesh(
      new THREE.TorusGeometry(1.9, 0.006, 8, 240),
      new THREE.MeshBasicMaterial({ color: 0x8b6cff, transparent: true, opacity: 0.55 }),
    )
    ring.rotation.x = 1.15
    const ring2 = new THREE.Mesh(
      new THREE.TorusGeometry(2.15, 0.004, 8, 240),
      new THREE.MeshBasicMaterial({ color: 0x2de2c9, transparent: true, opacity: 0.35 }),
    )
    ring2.rotation.set(0.5, 0.4, 0.8)

    const N = 360
    const pos = new Float32Array(N * 3)
    for (let i = 0; i < N; i++) {
      const r = 1.7 + Math.random() * 1.0, th = Math.random() * Math.PI * 2, ph = Math.acos(2 * Math.random() - 1)
      pos.set([r * Math.sin(ph) * Math.cos(th), r * Math.sin(ph) * Math.sin(th), r * Math.cos(ph)], i * 3)
    }
    const pg = new THREE.BufferGeometry()
    pg.setAttribute('position', new THREE.BufferAttribute(pos, 3))
    const points = new THREE.Points(pg, new THREE.PointsMaterial({
      color: 0x9ff5e8, size: 0.028, transparent: true, opacity: 0.8, blending: THREE.AdditiveBlending, depthWrite: false,
    }))
    const group = new THREE.Group()
    group.add(core, ring, ring2, points)
    scene.add(group)

    const resize = () => {
      const w = el.clientWidth, h = el.clientHeight
      if (!w || !h) return
      renderer.setSize(w, h, false)
      camera.aspect = w / h
      camera.updateProjectionMatrix()
    }
    resize()
    const ro = new ResizeObserver(resize)
    ro.observe(el)

    const target = { x: 0, y: 0 }
    const onMove = (e: PointerEvent) => {
      target.x = (e.clientY / window.innerHeight - 0.5) * 0.6
      target.y = (e.clientX / window.innerWidth - 0.5) * 0.9
    }
    window.addEventListener('pointermove', onMove)

    const still = prefersReducedMotion()
    const clock = new THREE.Clock()
    let raf = 0
    const frame = () => {
      const t = clock.getElapsedTime(), lv = level.current
      uniforms.uTime.value = t * (0.6 + lv * 1.6)
      uniforms.uAmp.value = 0.25 + lv * 0.35 + Math.sin(t * (1.2 + lv * 3)) * 0.05 * (0.4 + lv)
      core.rotation.y = t * 0.12
      ring.rotation.z = t * 0.18
      ring2.rotation.z = -t * 0.12
      points.rotation.y = t * 0.05
      group.rotation.x += (target.x - group.rotation.x) * 0.05
      group.rotation.y += (target.y - group.rotation.y) * 0.05
      renderer.render(scene, camera)
      if (!still) raf = requestAnimationFrame(frame)
    }
    const onVisibility = () => {
      cancelAnimationFrame(raf)
      if (!document.hidden && !still) { clock.start(); raf = requestAnimationFrame(frame) }
    }
    document.addEventListener('visibilitychange', onVisibility)
    frame()

    return () => {
      cancelAnimationFrame(raf)
      document.removeEventListener('visibilitychange', onVisibility)
      window.removeEventListener('pointermove', onMove)
      ro.disconnect()
      scene.traverse(o => {
        const m = o as THREE.Mesh
        m.geometry?.dispose()
        const mat = m.material as THREE.Material | THREE.Material[] | undefined
        if (Array.isArray(mat)) mat.forEach(x => x.dispose()); else mat?.dispose()
      })
      renderer.dispose()
      renderer.domElement.remove()
    }
  }, [])

  return <div className="orb-wrap" ref={host} aria-hidden="true">{fallback && <div className="orb-fallback" />}</div>
}
