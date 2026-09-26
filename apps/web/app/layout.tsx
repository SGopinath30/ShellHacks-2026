import type { Metadata } from "next";
import "maplibre-gl/dist/maplibre-gl.css";
import "./globals.css";
export const metadata: Metadata = {
  title: "Synchro | Coordination workspace",
  description: "Explore synthetic cross-utility construction opportunities.",
};
export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
