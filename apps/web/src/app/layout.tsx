import type { Metadata } from "next";
import { DashboardShell } from "@/components/layout/DashboardShell";
import "./globals.css";

export const metadata: Metadata = {
  title: "Case Analytics",
  description: "Agile analytics dashboard for case management",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="antialiased">
        <DashboardShell>{children}</DashboardShell>
      </body>
    </html>
  );
}
