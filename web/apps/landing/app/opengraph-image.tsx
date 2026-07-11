import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { ImageResponse } from "next/og";

export const dynamic = "force-static";

export const alt = "spawnd — deployed-first agent orchestration";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

function Glyph() {
  return (
    <svg viewBox="0 0 24 24" width={88} height={88} fill="none" role="img" aria-label="spawnd">
      <path d="M7 12h3c3 0 3-6 6-6h0.5" stroke="#818cf8" strokeWidth="2" strokeLinecap="round" />
      <path d="M10 12c3 0 3 6 6 6h0.5" stroke="#818cf8" strokeWidth="2" strokeLinecap="round" />
      <circle cx="5" cy="12" r="2.5" fill="#818cf8" />
      <circle cx="19" cy="6" r="2" stroke="#818cf8" strokeWidth="2" />
      <circle cx="19" cy="18" r="2" stroke="#818cf8" strokeWidth="2" />
    </svg>
  );
}

export default async function OpenGraphImage() {
  const fontsDir = join(process.cwd(), "node_modules/geist/dist/fonts");
  const [mono, sans] = await Promise.all([
    readFile(join(fontsDir, "geist-mono/GeistMono-SemiBold.ttf")),
    readFile(join(fontsDir, "geist-sans/Geist-Regular.ttf")),
  ]);

  return new ImageResponse(
    <div
      style={{
        width: "100%",
        height: "100%",
        display: "flex",
        flexDirection: "column",
        justifyContent: "space-between",
        backgroundColor: "#131316",
        backgroundImage: "radial-gradient(48rem 24rem at 85% -10%, #2a2a4a, #131316 70%)",
        padding: 72,
      }}
    >
      <div style={{ display: "flex" }}>
        <Glyph />
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
        <div
          style={{
            fontFamily: "mono",
            fontWeight: 600,
            fontSize: 112,
            color: "#fafafa",
            letterSpacing: "-0.04em",
          }}
        >
          spawnd
        </div>
        <div style={{ fontFamily: "sans", fontWeight: 400, fontSize: 36, color: "#a1a1aa" }}>
          deployed-first agent orchestration
        </div>
      </div>
      <div
        style={{
          display: "flex",
          fontFamily: "mono",
          fontWeight: 600,
          fontSize: 22,
          color: "#71717a",
          letterSpacing: "0.02em",
        }}
      >
        postgres-durable · budget-capped · check-verified · redacted-by-default
      </div>
    </div>,
    {
      ...size,
      fonts: [
        { name: "mono", data: mono, weight: 600, style: "normal" },
        { name: "sans", data: sans, weight: 400, style: "normal" },
      ],
    },
  );
}
