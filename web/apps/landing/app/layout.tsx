import { GeistMono } from "geist/font/mono";
import { GeistSans } from "geist/font/sans";
import type { Metadata, Viewport } from "next";
import { ThemeProvider } from "next-themes";
import "./globals.css";

const TITLE = "spawnd — deployed-first agent orchestration";
const DESCRIPTION =
  "Run DAGs of Claude Code and Codex agents against real repositories. Postgres is the system of record; checks gate dependents; budgets cap spend; artifacts are redacted by default.";

export const metadata: Metadata = {
  metadataBase: new URL("https://spawnd.dev"),
  title: TITLE,
  description: DESCRIPTION,
  keywords: [
    "agent orchestration",
    "coding agents",
    "claude code",
    "codex",
    "agent DAG",
    "llm infrastructure",
  ],
  openGraph: {
    title: TITLE,
    description: DESCRIPTION,
    url: "https://spawnd.dev",
    siteName: "spawnd",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: TITLE,
    description: DESCRIPTION,
  },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#fcfcfd" },
    { media: "(prefers-color-scheme: dark)", color: "#131316" },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${GeistSans.variable} ${GeistMono.variable}`}
    >
      <body className="min-h-screen bg-background font-sans text-foreground antialiased">
        <ThemeProvider
          attribute="class"
          defaultTheme="system"
          enableSystem
          disableTransitionOnChange
        >
          {children}
        </ThemeProvider>
      </body>
    </html>
  );
}
