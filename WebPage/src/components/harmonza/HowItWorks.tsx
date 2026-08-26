import { Reveal } from "./Reveal";
import { SectionShell } from "./SectionShell";
import { GESTURES } from "@/lib/harmonza-engine";

const stages = [
  {
    title: "Gesture",
    body: "A hand pose is performed in front of the camera — open palm, pinch, fist.",
  },
  {
    title: "Recognition",
    body: "Computer vision extracts hand landmarks and classifies the pose in real time.",
  },
  {
    title: "Chord Mapping",
    body: "Each recognised gesture resolves to a chord and voicing in the mapping table.",
  },
  {
    title: "Harmonization",
    body: "MIDI events drive a VST harmonization engine that renders the audible result.",
  },
];

export function HowItWorks() {
  return (
    <SectionShell
      id="how"
      index="I"
      eyebrow="How it works"
      title={
        <>
          Four stages between <em className="text-gradient-ember">a hand</em> and a chord.
        </>
      }
    >
      <div className="grid gap-px bg-border/40 sm:grid-cols-2 lg:grid-cols-4">
        {stages.map((s, i) => (
          <Reveal key={s.title} delay={i * 120}>
            <div className="group h-full bg-background p-7 transition-colors duration-700 hover:bg-secondary/30">
              <div className="flex items-baseline justify-between">
                <span className="font-mono text-[0.65rem] tracking-[0.3em] text-ember">
                  {String(i + 1).padStart(2, "0")}
                </span>
                <span className="h-px w-10 origin-right scale-x-50 bg-ember/60 transition-transform duration-700 group-hover:scale-x-100" />
              </div>
              <h3 className="mt-8 font-display text-2xl">{s.title}</h3>
              <p className="mt-3 text-sm leading-relaxed text-muted-foreground">{s.body}</p>
            </div>
          </Reveal>
        ))}
      </div>

      <div className="pointer-events-none mt-16 -mx-6 sm:-mx-10 overflow-hidden border-t border-b border-border/40 py-4">
        <div className="animate-marquee flex w-max gap-12 font-mono text-[0.65rem] uppercase tracking-[0.4em] text-muted-foreground/60">
          {Array.from({ length: 2 }).map((_, k) => (
            <span key={k} className="flex gap-12">
              {GESTURES.concat(GESTURES).map((g, i) => (
                <span key={`${k}-${i}`}>
                  {g.label} — {g.chord}
                </span>
              ))}
            </span>
          ))}
        </div>
      </div>
    </SectionShell>
  );
}