import { useEffect, useState } from "react";
import { GESTURES } from "@/lib/harmonza-engine";
import { HandVisual } from "./HandVisual";
import { useParallax } from "@/hooks/use-parallax";

export function HeroSection() {
  const [index, setIndex] = useState(1);
  const gesture = GESTURES[index]!;
  const glow = useParallax<HTMLDivElement>(0.22);
  const hand = useParallax<HTMLDivElement>(-0.08);

  useEffect(() => {
    const id = window.setInterval(() => setIndex((i) => (i + 1) % GESTURES.length), 3200);
    return () => window.clearInterval(id);
  }, []);

  return (
    <section id="top" className="grain relative min-h-[100svh] w-full overflow-x-hidden">
      <div
        ref={glow.ref}
        style={glow.style}
        className="animate-drift pointer-events-none absolute -top-52 left-1/2 h-[52rem] w-[52rem] -translate-x-1/2 rounded-full opacity-30 blur-3xl"
      >
        <div className="h-full w-full" style={{ background: "var(--gradient-brand-soft)" }} />
      </div>

      <div className="relative mx-auto flex min-h-[100svh] max-w-[86rem] flex-col justify-center px-6 pt-36 pb-16 sm:px-10">
        <p className="eyebrow line-rise">
          <span>Est. gesture instrument · no. 01</span>
        </p>

        <h1 className="mt-8 font-display leading-[0.82] tracking-tight [-webkit-text-stroke:0.5px_currentColor]">
          <span className="line-rise text-[19vw] sm:text-[15vw] lg:text-[12.5rem]">
            <span style={{ animationDelay: "80ms" }}>Harmonza</span>
          </span>
        </h1>

        <div className="mt-10 grid gap-10 lg:grid-cols-[1fr_auto] lg:items-end">
          <div>
            <p className="max-w-md font-display text-2xl italic leading-snug text-parchment sm:text-3xl">
              Hands in the air. Harmony in the room.
            </p>
            <div className="mt-10 flex flex-wrap gap-3">
              <a href="#playground" className="btn-slab">
                Playground
              </a>
              <a href="#demo" className="btn-hairline">
                The demo
              </a>
            </div>
          </div>

          <div ref={hand.ref} style={hand.style} className="relative w-full max-w-xs lg:w-72">
            <div className="h-52 w-full sm:h-64">
              <HandVisual gesture={gesture} />
            </div>
            <div className="hairline" />
            <div className="mt-4 flex items-baseline justify-between font-mono text-[0.65rem] uppercase tracking-[0.28em] text-muted-foreground">
              <span>{gesture.label}</span>
              <span key={gesture.chord} className="text-gradient-ember font-display text-2xl italic tracking-normal">
                {gesture.chord}
              </span>
            </div>
          </div>
        </div>
      </div>

    </section>
  );
}