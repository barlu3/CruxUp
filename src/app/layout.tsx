import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "CruxUp",
  description: "Climbing shoe recommendations matched on fit, style and budget.",
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
