import { useEffect, useRef } from "react";

/** Animated harmonic waveform. Amplitude/frequency follow the active chord. */
export function Waveform({
  timbre,
  active,
  midi,
}: {
  timbre: number;
  active: boolean;
  midi: number[];
}) {
  const ref = useRef<HTMLCanvasElement | null>(null);
  const stateRef = useRef({ timbre, active, midi, energy: 0 });
  stateRef.current.timbre = timbre;
  stateRef.current.active = active;
  stateRef.current.midi = midi;

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let raf = 0;
    let t = 0;

    const resize = () => {
      const dpr = window.devicePixelRatio || 1;
      const rect = canvas.getBoundingClientRect();
      canvas.width = rect.width * dpr;
      canvas.height = rect.height * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    resize();
    window.addEventListener("resize", resize);

    const render = () => {
      const rect = canvas.getBoundingClientRect();
      const w = rect.width;
      const h = rect.height;
      const s = stateRef.current;
      s.energy += ((s.active ? 1 : 0.25) - s.energy) * 0.06;
      ctx.clearRect(0, 0, w, h);

      const gradient = ctx.createLinearGradient(0, 0, w, 0);
      gradient.addColorStop(0, "rgba(139,64,255,0.95)");
      gradient.addColorStop(1, "rgba(56,199,255,0.95)");

      const layers = Math.max(3, s.midi.length);
      for (let layer = 0; layer < layers; layer++) {
        ctx.beginPath();
        const amp = (h / 2.6) * s.energy * (1 - layer * 0.16);
        const freq = (0.012 + layer * 0.004) * s.timbre;
        for (let x = 0; x <= w; x += 2) {
          const y =
            h / 2 +
            Math.sin(x * freq + t * (0.9 + layer * 0.18)) *
              amp *
              Math.sin((x / w) * Math.PI);
          if (x === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }
        ctx.strokeStyle = gradient;
        ctx.globalAlpha = 0.9 - layer * 0.2;
        ctx.lineWidth = layer === 0 ? 2.4 : 1.2;
        ctx.stroke();
      }
      ctx.globalAlpha = 1;
      t += 0.045;
      raf = requestAnimationFrame(render);
    };
    raf = requestAnimationFrame(render);

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
    };
  }, []);

  return <canvas ref={ref} className="h-full w-full" aria-hidden="true" />;
}