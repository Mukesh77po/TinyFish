import type { Metadata } from "next";
import { Inter, Space_Grotesk } from "next/font/google";
import "./globals.css";

// Self-hosted at build time: no request to Google when the page loads (the fallback demo runs offline).
const inter = Inter({ subsets: ["latin"], variable: "--font-inter", display: "swap" });
const grotesk = Space_Grotesk({ subsets: ["latin"], weight: ["500", "600", "700"], variable: "--font-grotesk",
                                display: "swap" });

export const metadata: Metadata = {
  title: "TenderHawk",
  description: "AI web agents that find the government tenders a small business can actually win, and tell it why.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`h-full scroll-smooth ${inter.variable} ${grotesk.variable}`}>
      <body className="flex min-h-full flex-col font-sans">{children}</body>
    </html>
  );
}
