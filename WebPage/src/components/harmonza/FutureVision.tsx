import { Reveal } from "./Reveal";
import { SectionShell } from "./SectionShell";

const items = [
  { title: "Richer gesture vocabulary", body: "More poses, more chords, dynamic modifiers." },
  { title: "Expressive control", body: "Velocity, articulation and voicing shaped by motion." },
  { title: "Real-time performance", body: "Stage-ready latency and reliability for live sets." },
  { title: "Browser-based interaction", body: "Gesture capture and playback directly on the web." },
  { title: "Deeper MIDI / VST", body: "Multi-plugin routing and full parameter automation." },
  { title: "Adaptive harmony", body: "Harmony that responds to performance, context and intent." },
];

export function FutureVision() {
  return (
    <SectionShell
      index="VII"
      eyebrow="Future vision"
      title={
        <>
          Where Harmonza <em className="text-gradient-ember">could go next</em>.
        </>
      }
      lede="Directions under exploration — not yet implemented. Each one widens the instrument rather than the interface: more nuance in the hand, more expression in the result, and eventually a version that runs anywhere a camera does."
    >
      <div className="grid gap-px bg-border/40 sm:grid-cols-2 lg:grid-cols-3">
        {items.map((it, i) => (
          <Reveal key={it.title} delay={i * 90}>
            <div className="group h-full bg-background p-7 transition-colors duration-700 hover:bg-secondary/30">
              <span className="block h-px w-10 origin-left bg-ember/70 transition-transform duration-700 group-hover:scale-x-[2.4]" />
              <h3 className="mt-6 font-display text-2xl">{it.title}</h3>
              <p className="mt-2 text-sm text-muted-foreground">{it.body}</p>
            </div>
          </Reveal>
        ))}
      </div>
    </SectionShell>
  );
}