import { Architecture } from "@/components/architecture";
import { Cta } from "@/components/cta";
import { Features } from "@/components/features";
import { Footer } from "@/components/footer";
import { Header } from "@/components/header";
import { Hero } from "@/components/hero";
import { Quickstart } from "@/components/quickstart";
import { Showcase } from "@/components/showcase";

export default function Home() {
  return (
    <div id="top" className="flex min-h-screen flex-col">
      <Header />
      <main className="mx-auto w-full max-w-6xl flex-1 border-x">
        <Hero />
        <Features />
        <Architecture />
        <Showcase />
        <Quickstart />
        <Cta />
      </main>
      <Footer />
    </div>
  );
}
