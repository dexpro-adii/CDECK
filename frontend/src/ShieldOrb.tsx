import { useEffect, useRef } from 'react';

type RiskLevel = 'high' | 'medium' | 'low' | 'idle';

interface ShieldOrbProps {
  riskLevel?: RiskLevel;
  size?: number;
}

export default function ShieldOrb({ riskLevel = 'idle', size = 72 }: ShieldOrbProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const stateRef = useRef<{
    animId: number;
    lastTime: number;
    angle: number;
    pulseT: number;
    riskLevel: RiskLevel;
    shockT: number; // 0..1 for shatter/ripple animation on state change
  }>({
    animId: 0,
    lastTime: 0,
    angle: 0,
    pulseT: 0,
    riskLevel: 'idle',
    shockT: 0,
  });

  // Trigger shock effect whenever riskLevel changes to something notable
  useEffect(() => {
    const s = stateRef.current;
    if (riskLevel !== 'idle') {
      s.shockT = 1.0;
    }
    s.riskLevel = riskLevel;
  }, [riskLevel]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = size * dpr;
    canvas.height = size * dpr;
    canvas.style.width = size + 'px';
    canvas.style.height = size + 'px';
    ctx.scale(dpr, dpr);

    const cx = size / 2;
    const cy = size / 2;
    const r = size * 0.36;

    function getColors(risk: RiskLevel) {
      switch (risk) {
        case 'high':   return { core: '#ff3355', glow: 'rgba(255,40,60,', ring: '#ff6680' };
        case 'medium': return { core: '#f59e0b', glow: 'rgba(245,158,11,', ring: '#fcd34d' };
        case 'low':    return { core: '#10b981', glow: 'rgba(16,185,129,', ring: '#34d399' };
        default:       return { core: '#00aaff', glow: 'rgba(0,170,255,', ring: '#38bdf8' };
      }
    }

    function drawShield(ctx: CanvasRenderingContext2D, cx: number, cy: number, r: number, angle: number, riskLevel: RiskLevel, pulseT: number, shockT: number) {
      const colors = getColors(riskLevel);

      // Base pulse: gentle 0..1 oscillation
      const pulse = 0.5 + 0.5 * Math.sin(pulseT);
      // Shock ripple on state change
      const shock = shockT > 0 ? Math.sin(shockT * Math.PI) : 0;
      const glowR = r * (1.1 + pulse * 0.15 + shock * 0.4);

      // Outer glow
      const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, glowR * 1.8);
      grad.addColorStop(0, `${colors.glow}${0.35 + pulse * 0.2 + shock * 0.3})`);
      grad.addColorStop(0.5, `${colors.glow}0.08)`);
      grad.addColorStop(1, `${colors.glow}0)`);
      ctx.beginPath();
      ctx.arc(cx, cy, glowR * 1.8, 0, Math.PI * 2);
      ctx.fillStyle = grad;
      ctx.fill();

      // Draw shield path (rotated slightly)
      ctx.save();
      ctx.translate(cx, cy);
      ctx.rotate(angle);

      const sh = r * 1.0;
      const sw = r * 0.82;

      ctx.beginPath();
      ctx.moveTo(0, -sh);
      ctx.bezierCurveTo(sw, -sh * 0.7, sw, -sh * 0.1, 0, sh * 0.9);
      ctx.bezierCurveTo(-sw, -sh * 0.1, -sw, -sh * 0.7, 0, -sh);
      ctx.closePath();

      // Shield fill
      const sfill = ctx.createRadialGradient(0, -sh * 0.2, 0, 0, 0, sh * 1.2);
      sfill.addColorStop(0, `${colors.glow}0.25)`);
      sfill.addColorStop(1, `${colors.glow}0.05)`);
      ctx.fillStyle = sfill;
      ctx.fill();

      // Shield stroke
      ctx.strokeStyle = colors.ring;
      ctx.lineWidth = 1.5 + pulse * 0.5;
      ctx.shadowBlur = 12 + pulse * 8 + shock * 15;
      ctx.shadowColor = colors.core;
      ctx.stroke();

      // Inner padlock icon (simplified)
      ctx.shadowBlur = 0;
      const lk = r * 0.22;
      ctx.strokeStyle = colors.ring;
      ctx.lineWidth = 1.2;
      // Shackle arc
      ctx.beginPath();
      ctx.arc(0, -lk * 0.4, lk * 0.55, Math.PI, 0);
      ctx.stroke();
      // Body
      ctx.strokeRect(-lk * 0.65, -lk * 0.2, lk * 1.3, lk * 1.1);

      // Rotating ring of dots
      const dotCount = riskLevel === 'high' ? 8 : 6;
      for (let i = 0; i < dotCount; i++) {
        const a = (i / dotCount) * Math.PI * 2;
        const dr = sh * 1.15 + pulse * 3;
        const dx = Math.cos(a) * dr;
        const dy = Math.sin(a) * dr;
        const dotA = 0.4 + pulse * 0.3 + (riskLevel === 'high' ? shock * 0.5 : 0);
        ctx.beginPath();
        ctx.arc(dx, dy, 1.5, 0, Math.PI * 2);
        ctx.fillStyle = `${colors.glow}${dotA})`;
        ctx.fill();
      }

      ctx.restore();
    }

    function draw(timestamp: number) {
      stateRef.current.animId = requestAnimationFrame(draw);
      // 30fps cap
      if (timestamp - stateRef.current.lastTime < 33) return;
      stateRef.current.lastTime = timestamp;

      const dt = 0.033;
      const s = stateRef.current;

      // Slow rotation
      s.angle += dt * 0.3;
      s.pulseT += dt * (s.riskLevel === 'high' ? 3.5 : s.riskLevel === 'medium' ? 2.0 : 1.2);
      if (s.shockT > 0) s.shockT = Math.max(0, s.shockT - dt * 1.5);

      ctx!.clearRect(0, 0, size, size);
      drawShield(ctx!, cx, cy, r, s.angle, s.riskLevel, s.pulseT, s.shockT);
    }

    stateRef.current.animId = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(stateRef.current.animId);
  }, [size]);

  return (
    <canvas
      ref={canvasRef}
      className="shrink-0"
      style={{ imageRendering: 'pixelated' }}
      aria-hidden="true"
    />
  );
}
