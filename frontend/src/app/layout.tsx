import type { Metadata } from "next";
import "./globals.css";
import { QueryProvider } from "@/components/providers/QueryProvider";
import { AppShell } from "@/components/layout/AppShell";
import { ToastProvider } from "@/components/ui/ToastProvider";

export const metadata: Metadata = {
  title: "Lattice — Distributed Application Deployment Platform",
  description:
    "Deploy containerized applications across a distributed mesh of developer-owned computers.",
  icons: {
    icon: "/logo.png",
    shortcut: "/favicon.ico",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen bg-background font-sans text-foreground antialiased selection:bg-primary/20 selection:text-primary">
        <QueryProvider>
          <AppShell>{children}</AppShell>
          <ToastProvider />
        </QueryProvider>
      </body>
    </html>
  );
}
