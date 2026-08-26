import { Reveal } from "./Reveal";
import { SectionShell } from "./SectionShell";

const chain = [
  { title: "Python", body: "Runtime orchestrating capture, inference and MIDI dispatch." },
  { title: "Computer Vision", body: "Frame-by-frame hand landmark detection from a webcam feed." },
  { title: "Gesture Recognition", body: "Landmark geometry classified into a discrete gesture set." },
  { title: "Chord Mapping", body: "A deterministic table binding each gesture to a chord voicing." },
  { title: "MIDI", body: "Note-on / note-off events emitted to a virtual MIDI port." },
  { title: "VST Harmonization", body: "A hosted plugin renders the harmonized musical result." },
];

export function Technology() {
  return (
    <SectionShell
      id="technology"
      index="III"
      eyebrow="Technology"
      title={
        <>
          The signal path, <em className="text-gradient-ember">end to end</em>.
        </>
      }
      lede="Every layer of Harmonza is deliberately small and legible: capture, classify, map, emit, render. Each stage hands the next a single, well-defined artefact — a frame, a label, a chord, a note event, a sound."
    >
      <div className="border-t border-border/40">
        {chain.map((step, i) => (
          <Reveal key={step.title} delay={i * 70}>
            <div className="group grid grid-cols-[3rem_minmax(0,1fr)] items-baseline gap-6 border-b border-border/40 py-7 transition-[padding,background] duration-700 hover:bg-secondary/20 hover:pl-4 sm:grid-cols-[4rem_16rem_minmax(0,1fr)]">
              <span className="font-mono text-[0.65rem] tracking-[0.3em] text-ember">
                {String(i + 1).padStart(2, "0")}
              </span>
              <h3 className="font-display text-2xl transition-transform duration-700 group-hover:translate-x-1 sm:text-3xl">
                {step.title}
              </h3>
              <p className="col-span-full text-sm leading-relaxed text-muted-foreground sm:col-span-1">
                {step.body}
              </p>
            </div>
          </Reveal>
        ))}
      </div>
    </SectionShell>
  );
}