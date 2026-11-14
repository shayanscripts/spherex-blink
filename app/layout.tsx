import type { Metadata } from "next";
import "@fontsource-variable/space-grotesk";
import "@fontsource-variable/dm-sans";
import "@fontsource/ibm-plex-mono/400.css";
import "./globals.css";

export const metadata: Metadata = {
  title: "SPHEREx · Sky Explorer",
  description: "Inspect a SPHEREx spectral observation, its detector data, wavelength calibration, and measurement uncertainty. Powered by real FITS files.",
};
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
