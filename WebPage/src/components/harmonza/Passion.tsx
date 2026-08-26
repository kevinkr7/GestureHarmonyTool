import { Reveal } from "./Reveal";

export function Passion() {
  return (
    <section className="relative overflow-hidden py-28">
      <div className="mx-auto max-w-5xl px-5">
        <Reveal>
          <div className="surface-panel relative overflow-hidden rounded-[2px] px-7 py-16 sm:px-14">
            <img
              src="/favicon.png"
              alt=""
              aria-hidden="true"
              className="animate-float pointer-events-none absolute -right-16 -bottom-16 h-64 w-64 opacity-10"
            />
            <p className="eyebrow">Built from passion</p>
            <blockquote className="mt-8 max-w-3xl font-display text-3xl italic leading-tight sm:text-5xl">
              <span className="text-gradient-ember">
                “I wanted to explore what happens when a musical instrument doesn't have to be
                touched.”
              </span>
            </blockquote>
            <div className="mt-10 grid max-w-3xl gap-6 text-sm leading-relaxed text-muted-foreground sm:grid-cols-2">
              <p>
                Harmonza was built at the intersection of two things I've never been able to
                separate: music and computer science. One taught me to listen for structure, the
                other taught me to build it.
              </p>
              <p>
                Every part of the system — the landmark tracking, the gesture classifier, the chord
                table, the MIDI bridge — exists to remove one thing: the physical barrier between
                an idea of a chord and the sound of it.
              </p>
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  );
}