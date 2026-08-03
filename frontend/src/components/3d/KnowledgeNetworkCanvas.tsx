import { useEffect, useRef } from 'react'
import * as THREE from 'three'
import { useThemeStore } from '@/store/themeStore'

interface KnowledgeNetworkCanvasProps {
  className?: string
}

export function KnowledgeNetworkCanvas({ className = '' }: KnowledgeNetworkCanvasProps) {
  const mountRef = useRef<HTMLDivElement>(null)
  const { theme } = useThemeStore()

  useEffect(() => {
    const container = mountRef.current
    if (!container) return

    const width = container.clientWidth || 600
    const height = container.clientHeight || 600

    // 1. Scene, Camera, Renderer
    const scene = new THREE.Scene()
    const camera = new THREE.PerspectiveCamera(50, width / height, 0.1, 1000)
    camera.position.z = 18

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
    renderer.setSize(width, height)
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    container.appendChild(renderer.domElement)

    // 2. Colors based on theme
    const isLight = theme === 'light'
    const primaryColor = isLight ? 0x1a3a2b : 0x8b5cf6
    const secondaryColor = isLight ? 0x2b6e4f : 0x6366f1
    const particleColor = isLight ? 0x22573e : 0xc084fc

    // 3. Central AI Core Sphere (Geodesic Wireframe)
    const coreGroup = new THREE.Group()
    scene.add(coreGroup)

    const coreGeo = new THREE.IcosahedronGeometry(3.5, 2)
    const coreMat = new THREE.MeshBasicMaterial({
      color: primaryColor,
      wireframe: true,
      transparent: true,
      opacity: isLight ? 0.35 : 0.45,
    })
    const coreMesh = new THREE.Mesh(coreGeo, coreMat)
    coreGroup.add(coreMesh)

    // Inner Pulsing Core Nucleus
    const innerGeo = new THREE.SphereGeometry(1.8, 24, 24)
    const innerMat = new THREE.MeshBasicMaterial({
      color: secondaryColor,
      transparent: true,
      opacity: isLight ? 0.6 : 0.7,
    })
    const innerMesh = new THREE.Mesh(innerGeo, innerMat)
    coreGroup.add(innerMesh)

    // 4. Knowledge Node Constellation (Vector Embeddings)
    const nodeCount = 50
    const nodePositions: THREE.Vector3[] = []
    const nodeGeometry = new THREE.SphereGeometry(0.18, 12, 12)
    const nodeMaterial = new THREE.MeshBasicMaterial({
      color: primaryColor,
      transparent: true,
      opacity: 0.9,
    })

    const nodesGroup = new THREE.Group()
    scene.add(nodesGroup)

    for (let i = 0; i < nodeCount; i++) {
      const radius = 6 + Math.random() * 5
      const theta = Math.random() * Math.PI * 2
      const phi = Math.acos(2 * Math.random() - 1)

      const x = radius * Math.sin(phi) * Math.cos(theta)
      const y = radius * Math.sin(phi) * Math.sin(theta)
      const z = radius * Math.cos(phi)

      const pos = new THREE.Vector3(x, y, z)
      nodePositions.push(pos)

      const mesh = new THREE.Mesh(nodeGeometry, nodeMaterial)
      mesh.position.copy(pos)
      nodesGroup.add(mesh)
    }

    // 5. Laser Connection Lines between Nodes
    const linePositions: number[] = []
    const connectionDistance = 4.8

    for (let i = 0; i < nodeCount; i++) {
      for (let j = i + 1; j < nodeCount; j++) {
        const dist = nodePositions[i].distanceTo(nodePositions[j])
        if (dist < connectionDistance) {
          linePositions.push(
            nodePositions[i].x, nodePositions[i].y, nodePositions[i].z,
            nodePositions[j].x, nodePositions[j].y, nodePositions[j].z
          )
        }
      }
    }

    const lineGeo = new THREE.BufferGeometry()
    lineGeo.setAttribute('position', new THREE.Float32BufferAttribute(linePositions, 3))
    const lineMat = new THREE.LineBasicMaterial({
      color: secondaryColor,
      transparent: true,
      opacity: isLight ? 0.25 : 0.35,
    })
    const linesMesh = new THREE.LineSegments(lineGeo, lineMat)
    nodesGroup.add(linesMesh)

    // 6. Ambient Floating Particles
    const particleCount = 120
    const particleGeo = new THREE.BufferGeometry()
    const pCoords = new Float32Array(particleCount * 3)

    for (let i = 0; i < particleCount * 3; i += 3) {
      pCoords[i] = (Math.random() - 0.5) * 35
      pCoords[i + 1] = (Math.random() - 0.5) * 35
      pCoords[i + 2] = (Math.random() - 0.5) * 35
    }

    particleGeo.setAttribute('position', new THREE.BufferAttribute(pCoords, 3))
    const particleMat = new THREE.PointsMaterial({
      color: particleColor,
      size: 0.12,
      transparent: true,
      opacity: 0.5,
    })
    const particleSystem = new THREE.Points(particleGeo, particleMat)
    scene.add(particleSystem)

    // 7. Mouse Interaction
    let mouseX = 0
    let mouseY = 0
    let targetX = 0
    let targetY = 0

    const handleMouseMove = (e: MouseEvent) => {
      const rect = container.getBoundingClientRect()
      const x = e.clientX - rect.left - rect.width / 2
      const y = e.clientY - rect.top - rect.height / 2
      targetX = (x / rect.width) * 0.8
      targetY = (y / rect.height) * 0.8
    }

    window.addEventListener('mousemove', handleMouseMove)

    // 8. Animation Loop
    let animationFrameId: number
    let clock = new THREE.Clock()

    const animate = () => {
      const elapsedTime = clock.getElapsedTime()

      // Smooth mouse lerp
      mouseX += (targetX - mouseX) * 0.05
      mouseY += (targetY - mouseY) * 0.05

      // Rotations
      coreGroup.rotation.y = elapsedTime * 0.18 + mouseX * 0.8
      coreGroup.rotation.x = elapsedTime * 0.12 + mouseY * 0.8

      nodesGroup.rotation.y = -elapsedTime * 0.1 + mouseX * 0.5
      nodesGroup.rotation.x = elapsedTime * 0.08 - mouseY * 0.5

      particleSystem.rotation.y = elapsedTime * 0.03

      // Nucleus pulse scale
      const scale = 1 + Math.sin(elapsedTime * 2.5) * 0.08
      innerMesh.scale.set(scale, scale, scale)

      renderer.render(scene, camera)
      animationFrameId = requestAnimationFrame(animate)
    }

    animate()

    // 9. Resize Listener
    const handleResize = () => {
      if (!container) return
      const w = container.clientWidth
      const h = container.clientHeight
      camera.aspect = w / h
      camera.updateProjectionMatrix()
      renderer.setSize(w, h)
    }

    window.addEventListener('resize', handleResize)

    // Clean up
    return () => {
      cancelAnimationFrame(animationFrameId)
      window.removeEventListener('mousemove', handleMouseMove)
      window.removeEventListener('resize', handleResize)
      if (container.contains(renderer.domElement)) {
        container.removeChild(renderer.domElement)
      }
      renderer.dispose()
    }
  }, [theme])

  return (
    <div
      ref={mountRef}
      className={`w-full h-full min-h-[320px] pointer-events-auto relative ${className}`}
    />
  )
}
