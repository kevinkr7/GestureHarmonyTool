import { Reveal } from "./Reveal";
import { SectionShell } from "./SectionShell";

export function DemoSection() {
  return (
    <SectionShell
      id="demo"
      index="V"
      eyebrow="Demonstration"
      title={
        <>
          See Harmonza <em className="text-gradient-ember">performed</em>.
        </>
      }
      lede="A recorded session of the Python application running live."
    >
      <Reveal>
        <div className="surface-panel overflow-hidden rounded-[2px]">
          <div className="relative aspect-video w-full bg-muted/20">
            <iframe
              src="https://www.linkedin.com/embed/feed/update/urn:li:ugcPost:7491130584572944384?compact=1"
              className="absolute inset-0 h-full w-full border-0"
              allowFullScreen
              title="Embedded post"
            />
          </div>
          <div className="grid grid-cols-2 gap-4 border-t border-border/60 px-6 py-5 text-xs text-muted-foreground sm:grid-cols-4">
            <Meta k="Input" v="Webcam" />
            <Meta k="Latency" v="Real time" />
            <Meta k="Output" v="MIDI → VST" />
            <Meta k="Runtime" v="Python" />
          </div>
        </div>
      </Reveal>
    </SectionShell>
  );
}

function Meta({ k, v }: { k: string; v: string }) {
  return (
    <div className="min-w-0">
      <p className="font-mono uppercase tracking-[0.25em]">{k}</p>
      <p className="mt-1 truncate font-mono text-foreground">{v}</p>
    </div>
  );
}