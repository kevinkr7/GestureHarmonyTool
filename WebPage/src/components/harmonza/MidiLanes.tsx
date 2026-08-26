import { type GestureState } from "@/lib/harmonza-engine";

/** MIDI note lane visualisation for the active chord. */
export function MidiLanes({ gesture }: { gesture: GestureState }) {
  return (
    <div className="space-y-2">
      {gesture.midi.map((note, i) => (
        <div key={`${gesture.id}-${note}`} className="flex items-center gap-3">
          <span className="w-12 shrink-0 font-mono text-[11px] text-muted-foreground">
            {gesture.notes[i]}
          </span>
          <div className="relative h-2.5 min-w-0 flex-1 overflow-hidden rounded-full bg-secondary">
            <div
              key={`${gesture.id}-bar-${note}`}
              className="absolute inset-y-0 left-0 rounded-full"
              style={{
                width: `${38 + ((note % 24) / 24) * 58}%`,
                background: "var(--gradient-brand)",
                animation: `hz-float 0.001s`,
                transition: "width 700ms cubic-bezier(0.16,1,0.3,1)",
                boxShadow: "var(--shadow-glow-cyan)",
                animationDelay: `${i * 70}ms`,
              }}
            />
          </div>
          <span className="w-10 shrink-0 text-right font-mono text-[11px] text-muted-foreground">
            {note}
          </span>
        </div>
      ))}
    </div>
  );
}