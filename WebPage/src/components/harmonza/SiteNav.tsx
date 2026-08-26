

const links = [
  { href: "#how", label: "How it works" },
  { href: "#playground", label: "Playground" },
  { href: "#technology", label: "Technology" },
  { href: "#demo", label: "Demo" },
  { href: "#architecture", label: "Architecture" },
];

export function SiteNav() {
  return (
    <header className="fixed inset-x-0 top-0 z-50">
      <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-4 border-b border-border/40 bg-background/70 px-6 py-3.5 backdrop-blur-xl sm:px-10">
        <a href="#top" className="flex min-w-0 items-center gap-3">
          <img src="/favicon.png" alt="Harmonza logo" className="h-7 w-7 shrink-0" />
          <span className="truncate font-display text-xl italic tracking-tight">
            Harmonza
          </span>
        </a>
        <nav className="hidden items-center gap-8 lg:flex">
          {links.map((l) => (
            <a
              key={l.href}
              href={l.href}
              className="font-mono text-[0.65rem] uppercase tracking-[0.28em] text-muted-foreground transition-all duration-500 hover:tracking-[0.34em] hover:text-foreground"
            >
              {l.label}
            </a>
          ))}
        </nav>
        <a
          href="#playground"
          className="btn-slab !px-4 !py-2 lg:hidden"
        >
          Try
        </a>
      </div>
    </header>
  );
}