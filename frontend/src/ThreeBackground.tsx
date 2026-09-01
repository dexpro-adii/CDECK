import { useEffect, useRef } from 'react';

interface Particle {
  x: number;
  y: number;
  vx: number;
  vy: number;
  radius: number;
  alpha: number;
  alphaDir: number;
}

export default function ThreeBackground() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const stateRef = useRef<{
    particles: Particle[];
    animId: number;
    lastTime: number;
    w: number;
    h: number;
    connections: [number, number][];
  }>({
    particles: [],
    animId: 0,
    lastTime: 0,
    w: 0,
    h: 0,
    connections: [],
  });

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const state = stateRef.current;

    function resize() {
      if (!canvas) return;
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      state.w = window.innerWidth;
      state.h = window.innerHeight;
      canvas.width = state.w * dpr;
      canvas.height = state.h * dpr;
      canvas.style.width = state.w + 'px';
      canvas.style.height = state.h + 'px';
      ctx!.scale(dpr, dpr);
    }

    function initParticles() {
      // Target ~100 particles — tuned for 60fps even on mobile
      const count = Math.min(100, Math.floor((state.w * state.h) / 12000));
      state.particles = [];
      for (let i = 0; i < count; i++) {
        state.particles.push({
          x: Math.random() * state.w,
          y: Math.random() * state.h,
          vx: (Math.random() - 0.5) * 0.25,
          vy: (Math.random() - 0.5) * 0.25,
          radius: Math.random() * 1.5 + 0.5,
          alpha: Math.random() * 0.5 + 0.1,
          alphaDir: Math.random() > 0.5 ? 1 : -1,
        });
      }
    }

    let frameCount = 0;

    function draw(timestamp: number) {
      state.animId = requestAnimationFrame(draw);

      // Throttle: 30fps max
      if (timestamp - state.lastTime < 33) return;
      state.lastTime = timestamp;
      frameCount++;

      if (!canvas || !ctx) return;
      ctx.clearRect(0, 0, state.w, state.h);

      const particles = state.particles;
      const len = particles.length;

      // Update positions
      for (let i = 0; i < len; i++) {
        const p = particles[i];
        p.x += p.vx;
        p.y += p.vy;

        // Wrap around edges
        if (p.x < 0) p.x = state.w;
        if (p.x > state.w) p.x = 0;
        if (p.y < 0) p.y = state.h;
        if (p.y > state.h) p.y = 0;

        // Pulse alpha
        p.alpha += p.alphaDir * 0.003;
        if (p.alpha > 0.55 || p.alpha < 0.05) p.alphaDir *= -1;
      }

      // Draw connection lines (recalculate every 3 frames for perf)
      if (frameCount % 3 === 0) {
        state.connections = [];
        const maxDist = 130;
        for (let i = 0; i < len; i++) {
          for (let j = i + 1; j < len; j++) {
            const dx = particles[i].x - particles[j].x;
            const dy = particles[i].y - particles[j].y;
            if (Math.abs(dx) > maxDist || Math.abs(dy) > maxDist) continue;
            const d = Math.sqrt(dx * dx + dy * dy);
            if (d < maxDist) {
              state.connections.push([i, j]);
            }
          }
        }
      }

      // Render connections
      const maxDist = 130;
      for (const [i, j] of state.connections) {
        const pi = particles[i];
        const pj = particles[j];
        const dx = pi.x - pj.x;
        const dy = pi.y - pj.y;
        const d = Math.sqrt(dx * dx + dy * dy);
        const lineAlpha = (1 - d / maxDist) * 0.06;
        ctx.beginPath();
        ctx.strokeStyle = `rgba(0, 160, 255, ${lineAlpha})`;
        ctx.lineWidth = 0.5;
        ctx.moveTo(pi.x, pi.y);
        ctx.lineTo(pj.x, pj.y);
        ctx.stroke();
      }

      // Render particles
      for (const p of particles) {
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(0, 180, 255, ${p.alpha})`;
        ctx.fill();
      }
    }

    resize();
    initParticles();
    state.animId = requestAnimationFrame(draw);

    const handleResize = () => {
      resize();
      initParticles();
    };
    window.addEventListener('resize', handleResize, { passive: true });

    return () => {
      cancelAnimationFrame(state.animId);
      window.removeEventListener('resize', handleResize);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      className="fixed inset-0 z-0 pointer-events-none"
      style={{ opacity: 0.6 }}
      aria-hidden="true"
    />
  );
}
