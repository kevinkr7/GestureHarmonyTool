import { useState } from "react";
import { Github } from "lucide-react";
import { Reveal } from "./Reveal";
import { SectionShell } from "./SectionShell";

const nodes = [
  { title: "Hand Gesture", detail: "A performer's pose, held in front of the camera." },
  { title: "Computer Vision", detail: "21 hand landmarks extracted per frame." },
  { title: "Gesture Mapping", detail: "Landmark geometry reduced to a discrete gesture label." },
  { title: "Musical Chord", detail: "The gesture resolves to a chord and voicing." },
  { title: "MIDI", detail: "Note events emitted on a virtual MIDI port." },
  { title: "VST Harmonization", detail: "A plugin voices and harmonizes the incoming notes." },
  { title: "Audio Output", detail: "The rendered harmony reaches the audio interface." },
];

export function Architecture() {
  const [hovered, setHovered] = useState<number | null>(null);

  return (
    <SectionShell
      id="architecture"
      index="VI"
      eyebrow="Architecture"
      title={
        <>
          Hover any stage <em className="text-gradient-ember">to inspect it</em>.
        </>
      }
      lede="The full chain from a raised hand to audible harmony, expressed as seven discrete plates. Each one owns a single responsibility and can be swapped without disturbing its neighbours."
    >
      <Reveal>
        <div className="flex flex-wrap items-stretch gap-3">
          {nodes.map((n, i) => {
            const on = hovered === i;
            return (
              <div key={n.title} className="flex min-w-0 flex-1 basis-[220px] items-center gap-3">
                <button
                  onMouseEnter={() => setHovered(i)}
                  onMouseLeave={() => setHovered(null)}
                  onFocus={() => setHovered(i)}
                  onBlur={() => setHovered(null)}
                  className="min-w-0 flex-1 rounded-[2px] border p-5 text-left transition-all duration-700"
                  style={
                    on
                      ? {
                          borderColor: "color-mix(in oklab, var(--ember) 60%, transparent)",
                          background: "color-mix(in oklab, var(--ember) 8%, transparent)",
                          boxShadow: "var(--shadow-glow-ember)",
                          transform: "translateY(-6px)",
                        }
                      : { borderColor: "var(--border)" }
                  }
                >
                  <span className="font-mono text-[10px] tracking-[0.3em] text-ember">
                    {String(i + 1).padStart(2, "0")}
                  </span>
                  <h3 className="mt-3 font-display text-xl">{n.title}</h3>
                  <p
                    className="grid text-sm text-muted-foreground transition-all duration-700"
                    style={{
                      gridTemplateRows: on ? "1fr" : "0fr",
                      opacity: on ? 1 : 0,
                      marginTop: on ? "0.5rem" : 0,
                    }}
                  >
                    <span className="overflow-hidden">{n.detail}</span>
                  </p>
                </button>
                {i < nodes.length - 1 && (
                  <span
                    className="hidden h-px w-4 shrink-0 opacity-50 sm:block"
                    style={{ background: "var(--gradient-ember)" }}
                  />
                )}
              </div>
            );
          })}
        </div>

        <div className="mt-16">
          <a
            href="https://github.com/kevinkr7/Harmonza"
            target="_blank"
            rel="noopener noreferrer"
            className="group flex w-full flex-col sm:flex-row sm:items-center justify-between gap-6 rounded-[2px] border border-border bg-background p-6 sm:px-8 sm:py-6 transition-all duration-700 hover:border-ember/40 hover:bg-ember/5"
          >
            <div className="flex items-center gap-5">
              <div className="grid h-12 w-12 shrink-0 place-items-center rounded-full bg-muted/50 border border-border/50 transition-colors duration-700 group-hover:bg-ember/10 group-hover:border-ember/30">
                <Github className="h-5 w-5 text-muted-foreground transition-colors duration-700 group-hover:text-ember" />
              </div>
              <div className="text-left">
                <p className="font-display text-lg text-foreground transition-colors duration-700 group-hover:text-ember">
                  View the source
                </p>
                <p className="mt-1 text-sm text-muted-foreground">
                  Explore the full Python application and architecture on GitHub.
                </p>
              </div>
            </div>
            <span className="shrink-0 font-mono text-xs uppercase tracking-[0.2em] text-muted-foreground transition-all duration-700 group-hover:text-ember group-hover:tracking-[0.25em]">
              github.com/kevinkr7/Harmonza &rarr;
            </span>
          </a>
        </div>
      </Reveal>
    </SectionShell>
  );
}