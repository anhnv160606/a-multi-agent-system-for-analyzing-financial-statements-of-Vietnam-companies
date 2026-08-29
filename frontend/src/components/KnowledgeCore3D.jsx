import React, { useEffect, useRef } from 'react';
import * as THREE from 'three';

export default function KnowledgeCore3D({ isProcessing }) {
  const canvasRef = useRef(null);

  useEffect(() => {
    if (!canvasRef.current) return;

    const width = 360;
    const height = 360;

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 1000);
    camera.position.z = 4.2;

    const renderer = new THREE.WebGLRenderer({
      canvas: canvasRef.current,
      alpha: true,
      antialias: true,
    });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));

    // Core Icosahedron geometry
    const geometry = new THREE.IcosahedronGeometry(1.35, 2);
    const material = new THREE.MeshPhongMaterial({
      color: 0x6366F1,
      emissive: 0x3B82F6,
      emissiveIntensity: isProcessing ? 0.9 : 0.3,
      shininess: 100,
      flatShading: true,
      transparent: true,
      opacity: isProcessing ? 0.65 : 0.4,
    });
    const sphereMesh = new THREE.Mesh(geometry, material);
    scene.add(sphereMesh);

    // Wireframe overlay
    const wireGeometry = new THREE.IcosahedronGeometry(1.38, 2);
    const wireMaterial = new THREE.MeshBasicMaterial({
      color: 0x06B6D4,
      wireframe: true,
      transparent: true,
      opacity: isProcessing ? 0.7 : 0.3,
    });
    const wireMesh = new THREE.Mesh(wireGeometry, wireMaterial);
    scene.add(wireMesh);

    // Ambient Particles
    const particleGeo = new THREE.BufferGeometry();
    const particleCount = 80;
    const posArray = new Float32Array(particleCount * 3);

    for (let i = 0; i < particleCount * 3; i += 3) {
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.acos(Math.random() * 2 - 1);
      const radius = 1.5 + Math.random() * 0.5;
      posArray[i] = radius * Math.sin(phi) * Math.cos(theta);
      posArray[i + 1] = radius * Math.sin(phi) * Math.sin(theta);
      posArray[i + 2] = radius * Math.cos(phi);
    }

    particleGeo.setAttribute('position', new THREE.BufferAttribute(posArray, 3));
    const particleMat = new THREE.PointsMaterial({
      size: 0.05,
      color: 0xA855F7,
      transparent: true,
      opacity: 0.6,
    });
    const particleSystem = new THREE.Points(particleGeo, particleMat);
    scene.add(particleSystem);

    // Lights
    const light1 = new THREE.PointLight(0x06B6D4, 2.5, 50);
    light1.position.set(3, 3, 3);
    scene.add(light1);

    const light2 = new THREE.PointLight(0xA855F7, 2.2, 50);
    light2.position.set(-3, -3, 3);
    scene.add(light2);

    const ambLight = new THREE.AmbientLight(0x1E293B, 1.2);
    scene.add(ambLight);

    let animId;
    const animate = () => {
      animId = requestAnimationFrame(animate);
      const speed = isProcessing ? 0.035 : 0.005;
      sphereMesh.rotation.y += speed;
      sphereMesh.rotation.x += speed * 0.4;
      wireMesh.rotation.y += speed * 1.1;
      wireMesh.rotation.x += speed * 0.4;
      particleSystem.rotation.y -= speed * 0.5;
      renderer.render(scene, camera);
    };

    animate();

    return () => {
      cancelAnimationFrame(animId);
      renderer.dispose();
    };
  }, [isProcessing]);

  return (
    <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 pointer-events-none z-0 opacity-40 select-none flex flex-col items-center justify-center">
      <canvas ref={canvasRef} className="w-[360px] h-[360px]" />
      <div className="text-center -mt-8 opacity-60">
        <div className="font-display font-extrabold text-[13px] tracking-[0.18em] uppercase text-white/70 drop-shadow-[0_0_15px_rgba(6,182,212,0.6)]">
          KNOWLEDGE CORE
        </div>
      </div>
    </div>
  );
}
