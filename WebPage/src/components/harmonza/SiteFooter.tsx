

export function SiteFooter() {
  return (
    <footer className="border-t border-border/60">
      <div className="mx-auto grid max-w-6xl grid-cols-[minmax(0,1fr)_auto] items-center gap-4 px-5 py-10">
        <div className="flex min-w-0 items-center gap-3">
          <img src="/favicon.png" alt="Harmonza logo" className="h-8 w-8 shrink-0" />
          <div className="min-w-0">
            <p className="truncate font-display text-sm font-semibold">Harmonza</p>
            <p className="truncate text-xs text-muted-foreground">
              Turn gestures into harmony.
            </p>
          </div>
        </div>
        <p className="text-right text-xs text-muted-foreground">
          A music-technology research project by Kevin Raphy.
        </p>
      </div>
    </footer>
  );
}