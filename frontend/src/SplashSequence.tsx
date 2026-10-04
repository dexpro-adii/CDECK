import { useState, useEffect, useCallback } from 'react';
import logoImg from './assets/logo.png';

interface SplashSequenceProps {
  onComplete: () => void;
}

export default function SplashSequence({ onComplete }: SplashSequenceProps) {
  const [phase, setPhase] = useState<'black' | 'wipe' | 'hold' | 'done'>('black');

  const finish = useCallback(() => {
    setPhase('done');
    onComplete();
  }, [onComplete]);

  useEffect(() => {
    // 0.0–0.3s: black
    const t1 = setTimeout(() => setPhase('wipe'), 300);
    // 3.0–3.3s: wipe done → hold
    const t2 = setTimeout(() => setPhase('hold'), 3000);
    // 3.5–4.0s: fade out and complete
    const t3 = setTimeout(finish, 4000);
    return () => { clearTimeout(t1); clearTimeout(t2); clearTimeout(t3); };
  }, [finish]);

  if (phase === 'done') return null;

  return (
    <div
      onClick={finish}
      className="fixed inset-0 z-[100] bg-black flex items-center justify-center overflow-hidden cursor-pointer select-none"
      style={{
        animation: phase === 'hold' ? 'splash-container-out 0.7s ease-in forwards 0.5s' : undefined,
      }}
    >
      <style>{`
        /* ═══════════════════════════════════════════════════
           Kali-style diagonal wipe reveal with leading glow
           ═══════════════════════════════════════════════════ */

        /* Container fade-out at end of hold phase */
        @keyframes splash-container-out {
          from { opacity: 1; }
          to   { opacity: 0; pointer-events: none; }
        }

        /* ── The diagonal wipe mask ──
           Uses a linear-gradient as a mask-image.
           The gradient sweeps from top-left to bottom-right.
           Key idea: the gradient goes from black (opaque) → transparent (hidden).
           We animate mask-position to slide this edge across the image. */
        @keyframes kali-wipe {
          0%   {
            -webkit-mask-position: -200% -200%;
            mask-position: -200% -200%;
          }
          100% {
            -webkit-mask-position: 0% 0%;
            mask-position: 0% 0%;
          }
        }

        .splash-logo-reveal {
          /* Diagonal gradient mask: fully opaque on the revealed side,
             sharp-ish transition, then transparent on the hidden side */
          -webkit-mask-image: linear-gradient(
            135deg,
            rgba(0,0,0,1) 0%,
            rgba(0,0,0,1) 40%,
            rgba(0,0,0,0.6) 45%,
            rgba(0,0,0,0) 50%,
            rgba(0,0,0,0) 100%
          );
          mask-image: linear-gradient(
            135deg,
            rgba(0,0,0,1) 0%,
            rgba(0,0,0,1) 40%,
            rgba(0,0,0,0.6) 45%,
            rgba(0,0,0,0) 50%,
            rgba(0,0,0,0) 100%
          );
          -webkit-mask-size: 300% 300%;
          mask-size: 300% 300%;
          -webkit-mask-repeat: no-repeat;
          mask-repeat: no-repeat;
        }

        .splash-logo-reveal.wiping {
          animation: kali-wipe 2.7s cubic-bezier(0.25, 0.1, 0.25, 1) forwards;
        }

        /* ── Leading glow edge ──
           A bright white-blue band that sits right at the wipe boundary.
           Same mask animation, but the gradient is narrow to only show
           a thin glowing strip. */
        @keyframes glow-edge-sweep {
          0%   {
            -webkit-mask-position: -200% -200%;
            mask-position: -200% -200%;
            opacity: 0;
          }
          5% { opacity: 1; }
          90% { opacity: 1; }
          100% {
            -webkit-mask-position: 0% 0%;
            mask-position: 0% 0%;
            opacity: 0;
          }
        }

        .splash-glow-edge {
          -webkit-mask-image: linear-gradient(
            135deg,
            rgba(0,0,0,0) 0%,
            rgba(0,0,0,0) 38%,
            rgba(0,0,0,0.3) 43%,
            rgba(0,0,0,1) 46%,
            rgba(0,0,0,1) 48%,
            rgba(0,0,0,0.3) 51%,
            rgba(0,0,0,0) 55%,
            rgba(0,0,0,0) 100%
          );
          mask-image: linear-gradient(
            135deg,
            rgba(0,0,0,0) 0%,
            rgba(0,0,0,0) 38%,
            rgba(0,0,0,0.3) 43%,
            rgba(0,0,0,1) 46%,
            rgba(0,0,0,1) 48%,
            rgba(0,0,0,0.3) 51%,
            rgba(0,0,0,0) 55%,
            rgba(0,0,0,0) 100%
          );
          -webkit-mask-size: 300% 300%;
          mask-size: 300% 300%;
          -webkit-mask-repeat: no-repeat;
          mask-repeat: no-repeat;
        }

        .splash-glow-edge.wiping {
          animation: glow-edge-sweep 2.7s cubic-bezier(0.25, 0.1, 0.25, 1) forwards;
        }

        /* ── Hold phase glow pulse ── */
        @keyframes hold-pulse {
          0%   { filter: brightness(1)   drop-shadow(0 0 12px rgba(0,170,255,0.4)); }
          50%  { filter: brightness(1.3) drop-shadow(0 0 30px rgba(0,200,255,0.7)); }
          100% { filter: brightness(1)   drop-shadow(0 0 12px rgba(0,170,255,0.4)); }
        }
      `}</style>

      <div className="relative w-[88vw] max-w-[750px]" style={{ aspectRatio: '16/9' }}>

        {/* Layer 1: The actual logo image, progressively revealed by the diagonal mask wipe */}
        <img
          src={logoImg}
          alt="CDECK Logo"
          draggable={false}
          className={`absolute inset-0 w-full h-full object-contain splash-logo-reveal ${phase === 'wipe' ? 'wiping' : ''}`}
          style={{
            filter: phase === 'hold'
              ? 'brightness(1) drop-shadow(0 0 12px rgba(0,170,255,0.4))'
              : undefined,
            animation: phase === 'hold'
              ? 'hold-pulse 1.2s ease-in-out 1'
              : undefined,
            // If still in black phase, keep fully masked out
            ...(phase === 'black' ? {
              WebkitMaskPosition: '-200% -200%',
              maskPosition: '-200% -200%',
            } : {}),
            // If in hold phase, mask is fully open
            ...(phase === 'hold' ? {
              WebkitMaskPosition: '0% 0%',
              maskPosition: '0% 0%',
            } : {}),
          }}
        />

        {/* Layer 2: The glowing leading edge — a bright white-blue band at the wipe boundary */}
        <div
          className={`absolute inset-0 splash-glow-edge ${phase === 'wipe' ? 'wiping' : ''}`}
          style={{
            background: 'linear-gradient(135deg, rgba(0,180,255,0.15) 0%, rgba(0,210,255,0.3) 40%, rgba(255,255,255,0.7) 47%, rgba(0,210,255,0.3) 54%, rgba(0,180,255,0.15) 100%)',
            filter: 'blur(6px)',
            opacity: phase === 'wipe' ? undefined : 0,
            pointerEvents: 'none',
            ...(phase === 'black' ? {
              WebkitMaskPosition: '-200% -200%',
              maskPosition: '-200% -200%',
            } : {}),
          }}
        />
      </div>

      {/* Skip hint */}
      <div className="absolute bottom-8 text-neutral-600 text-[11px] font-medium tracking-[0.2em] uppercase opacity-40 hover:opacity-80 transition-opacity duration-300">
        Click anywhere to skip
      </div>
    </div>
  );
}
