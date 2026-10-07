import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "RE — Realm Engine",
  description: "A foundation for a living, AI-guided game world.",
  manifest: "/manifest.webmanifest",
};

export const viewport: Viewport = {
  themeColor: "#101114",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
