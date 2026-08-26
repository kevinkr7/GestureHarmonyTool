import { useState } from "react";
import { harmonzaEngine, type GestureId } from "@/lib/harmonza-engine";
import { HandVisual } from "./HandVisual";
import { Waveform } from "./Waveform";
import { MidiLanes } from "./MidiLanes";
import { Reveal } from "./Reveal";
import { SectionShell } from "./SectionShell";

/**
 * Interactive gesture playground.
 * State comes from `harmonzaEngine` (simulated). Swapping in a real
 * WebSocket-backed engine requires no changes to this component.
 */
export function Playground() {
  const gestures = harmonzaEngine.gestures();
  const [activeId, setActiveId] = useState<GestureId>("gesture-1");
  const active = harmonzaEngine.resolve(activeId);

  return (
    <SectionShell
      id="playground"
      index="II"
      eyebrow="Playground"
      title={
        <>
          Select a gesture. <em className="text-gradient-ember">Hear the idea.</em>
        </>
      }
      lede="A simulation of the Harmonza runtime interface. Gesture input is emulated in the browser for demonstration."
    >
        <Reveal>
          <div className="surface-panel overflow-hidden rounded-[2px]">
            <div className="grid gap-0 lg:grid-cols-[300px_minmax(0,1fr)]">
              <div className="border-b border-border/60 p-6 lg:border-b-0 lg:border-r">
                <p className="eyebrow">Gesture input</p>
                <div className="mt-4 grid grid-cols-2 gap-3 lg:grid-cols-1">
                  {gestures.map((g) => {
                    const on = g.id === activeId;
                    return (
                      <button
                        key={g.id}
                        onClick={() => setActiveId(g.id)}
                        aria-pressed={on}
                        className="group rounded-[2px] border p-4 text-left transition-all duration-700 hover:-translate-y-0.5"
                        style={
                          on
                            ? {
                                borderColor: "color-mix(in oklab, var(--ember) 55%, transparent)",
                                background: "color-mix(in oklab, var(--ember) 9%, transparent)",
                                boxShadow: "var(--shadow-glow-ember)",
                              }
                            : { borderColor: "var(--border)" }
                        }
                      >
                        <span className="block font-display text-lg">{g.label}</span>
                        <span className="mt-1 block text-xs text-muted-foreground">{g.pose}</span>
                        <span
                          className={
                            "mt-3 block font-mono text-xs " +
                            (on ? "text-ember" : "text-muted-foreground/70")
                          }
                        >
                          {g.chord}
                        </span>
                      </button>
                    );
                  })}
                </div>
              </div>

              <div className="p-6 sm:p-8">
                <div className="grid gap-8 sm:grid-cols-[minmax(0,1fr)_170px] sm:items-start">
                  <div className="min-w-0">
                    <p className="eyebrow">Resolved chord</p>
                    <h3
                      key={active.id}
                      className="text-gradient-ember mt-2 font-display text-6xl italic sm:text-7xl"
                      style={{ animation: "hz-float 0.8s ease-out" }}
                    >
                      {active.chord}
                    </h3>
                    <p className="mt-2 text-sm text-muted-foreground">{active.quality}</p>
                  </div>
                  <div className="h-40 w-32 justify-self-center sm:justify-self-end">
                    <HandVisual gesture={active} />
                  </div>
                </div>

                <div className="mt-8 rounded-[2px] border border-border/60 bg-background/40 p-4">
                  <p className="eyebrow">Harmonized output</p>
                  <div className="mt-2 h-28">
                    <Waveform timbre={active.timbre} midi={active.midi} active />
                  </div>
                </div>

                <div className="mt-6 grid gap-6 sm:grid-cols-2">
                  <div>
                    <p className="eyebrow">MIDI events</p>
                    <div className="mt-3">
                      <MidiLanes gesture={active} />
                    </div>
                  </div>
                  <div className="rounded-[2px] border border-border/60 p-4">
                    <p className="eyebrow">Engine state</p>
                    <dl className="mt-3 space-y-2 font-mono text-xs">
                      <Line k="source" v="simulated" />
                      <Line k="gesture" v={active.label.toLowerCase().replace(" ", "_")} />
                      <Line k="voicing" v={`${active.midi.length} notes`} />
                      <Line k="vst" v="harmonizer · active" accent />
                    </dl>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </Reveal>
    </SectionShell>
  );
}

function Line({ k, v, accent }: { k: string; v: string; accent?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <dt className="text-muted-foreground">{k}</dt>
      <dd className={accent ? "text-ember" : "text-foreground"}>{v}</dd>
    </div>
  );
}