"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuthStore } from "@/stores/authStore";
import { MotionSurface } from "@/components/ui/MotionSurface";
import { useHealth } from "@/hooks/useWorkers";
import { ErrorState } from "@/components/ui/ErrorState";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";
import { useUiStore } from "@/stores/uiStore";
import { DownloadLatticeModal } from "@/components/modals/DownloadLatticeModal";
import { CreatePoolModal } from "@/components/modals/CreatePoolModal";
import { WorkerDetailsModal } from "@/components/workers/WorkerDetailsModal";

export function DashboardLayout({ children }: { children: React.ReactNode }) {
  const health = useHealth();
  const pathname = usePathname();
  const preview = useAuthStore((s) => s.preview);
  const {
    isDownloadModalOpen,
    closeDownloadModal,
    isCreatePoolModalOpen,
    closeCreatePoolModal,
  } = useUiStore();

  return (
    <div className="flex min-h-screen bg-background text-foreground font-sans antialiased selection:bg-primary/20 selection:text-primary">
      {/* Persistent Sidebar */}
      <Sidebar />

      {/* Main Column */}
      <div className="flex-1 flex flex-col min-w-0">
        <Topbar />
        <nav
          aria-label="Mobile navigation"
          className="md:hidden flex gap-4 overflow-x-auto px-4 py-3 border-b border-surface-border text-xs"
        >
          {[
            ["/dashboard", "Overview"],
            ["/pools", "Pools"],
            ["/deployments", "Deployments"],
            ["/projects/overview", "Projects"],
            ["/settings", "Settings"],
          ].map(([url, label]) => (
            <Link
              key={url}
              href={url}
              className="whitespace-nowrap text-zinc-300"
            >
              {label}
            </Link>
          ))}
        </nav>
        <main className="flex-1 p-6 md:p-8 max-w-7xl w-full mx-auto space-y-8">
          {health.error && (
            <ErrorState
              title="Controller unavailable"
              message="Live data cannot be refreshed. Cached readings may be stale; no success is simulated."
              onRetry={() => health.refetch()}
            />
          )}
          {preview && (
            <div
              role="status"
              className="border border-amber-500/30 bg-amber-500/5 rounded-lg p-3 text-sm text-amber-200"
            >
              Preview workspace — no operator session or live data.{" "}
              <Link href="/login" className="underline">
                Connect to the controller
              </Link>{" "}
              to create resources.
            </div>
          )}
          <MotionSurface key={pathname} className="space-y-8">
            {children}
          </MotionSurface>
        </main>
      </div>

      {/* Global Shared Modals */}
      <DownloadLatticeModal
        isOpen={isDownloadModalOpen}
        onClose={closeDownloadModal}
      />
      <CreatePoolModal
        isOpen={isCreatePoolModalOpen}
        onClose={closeCreatePoolModal}
      />
      <WorkerDetailsModal />
    </div>
  );
}
