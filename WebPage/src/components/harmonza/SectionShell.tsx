import { type ReactNode } from "react";
import { Reveal } from "./Reveal";
import { useParallax } from "@/hooks/use-parallax";

export function SectionShell({
  id,
  index,
  eyebrow,
  title,
  lede,
  children,
}: {
  id?: string;
  index: string;
  eyebrow: string;
  title: ReactNode;
  lede?: string;
  children: ReactNode;
}) {
  const { ref, style } = useParallax<HTMLSpanElement>(0.06);

  return (
    <section id={id} className="grain relative w-full border-t border-border/40 py-24 sm:py-32">
      <div className="mx-auto max-w-[86rem] px-6 sm:px-10">
        <Reveal>
          <div className="flex items-baseline justify-between gap-6">
            <p className="eyebrow">{eyebrow}</p>
            <span
              ref={ref}
              style={style}
              className="font-display text-5xl italic text-muted-foreground/25 sm:text-7xl"
            >
              {index}
            </span>
          </div>
          <div className="hairline mt-5" />
          <h2 className="mt-10 max-w-4xl font-display text-4xl leading-[1.02] sm:text-6xl lg:text-7xl">
            {title}
          </h2>
          {lede && (
            <p className="mt-6 max-w-xl text-sm leading-relaxed text-muted-foreground">{lede}</p>
          )}
        </Reveal>
        <div className="mt-16">{children}</div>
      </div>
    </section>
  );
}