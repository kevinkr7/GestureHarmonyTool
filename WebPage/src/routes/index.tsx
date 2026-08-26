import { createFileRoute } from "@tanstack/react-router";
import { SiteNav } from "@/components/harmonza/SiteNav";
import { HeroSection } from "@/components/harmonza/HeroSection";
import { HowItWorks } from "@/components/harmonza/HowItWorks";
import { Playground } from "@/components/harmonza/Playground";
import { Technology } from "@/components/harmonza/Technology";
import { Passion } from "@/components/harmonza/Passion";
import { DemoSection } from "@/components/harmonza/DemoSection";
import { Architecture } from "@/components/harmonza/Architecture";
import { FutureVision } from "@/components/harmonza/FutureVision";
import { SiteFooter } from "@/components/harmonza/SiteFooter";

const title = "Harmonza — Turn gestures into harmony";
const description =
  "A computer-vision-powered musical interface where hand gestures become chords, MIDI and VST harmonization.";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title },
      { name: "description", content: description },
      { property: "og:title", content: title },
      { property: "og:description", content: description },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: Index,
});

function Index() {
  return (
    <main className="relative min-h-screen overflow-x-hidden bg-background">
      <SiteNav />
      <HeroSection />
      <HowItWorks />
      <Playground />
      <Technology />
      <Passion />
      <DemoSection />
      <Architecture />
      <FutureVision />
      <SiteFooter />
    </main>
  );
}
