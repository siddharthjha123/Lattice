"use client";

import React from "react";
import Link from "next/link";
import { LatticeLoader } from "@/components/ui/LatticeLoader";
import { usePathname } from "next/navigation";
import { useAuthStore } from "@/stores/authStore";
import { useUiStore } from "@/stores/uiStore";
import { usePools } from "@/hooks/usePools";
import {
  LayoutDashboard,
  Network,
  Box,
  Rocket,
  FolderGit2,
  Settings,
  Plus,
  Download,
  Terminal,
  CheckCircle2,
  Circle,
} from "lucide-react";

export function Sidebar() {
  const pathname = usePathname();
  const user = useAuthStore((state) => state.user);
  const openCreatePoolModal = useUiStore((state) => state.openCreatePoolModal);
  const openDownloadModal = useUiStore((state) => state.openDownloadModal);
  const { data: pools = [] } = usePools();

  const navLinks = [
    { title: "Overview", href: "/dashboard", icon: LayoutDashboard },
    { title: "Connection Pools", href: "/pools", icon: Network },
    {
      title: "Boxes",
      href: pools[0] ? `/pools/${pools[0].id}/boxes` : "/pools",
      icon: Box,
    },
    { title: "Deployments", href: "/deployments", icon: Rocket },
    { title: "Projects", href: "/projects/overview", icon: FolderGit2 },
    { title: "Settings", href: "/settings", icon: Settings },
  ];

  return (
    <aside className="hidden md:flex w-64 border-r border-surface-border bg-card flex flex-col justify-between shrink-0 h-screen sticky top-0 select-none z-30">
      {/* Top Section */}
      <div className="flex flex-col">
        {/* Brand Header */}
        <div className="p-5 border-b border-surface-border/60 flex items-center justify-between">
          <Link href="/dashboard" className="flex items-center gap-2.5 group">
            <div className="w-8 h-8 rounded-lg bg-surface border border-surface-border flex items-center justify-center group-hover:border-primary/50 transition-colors shadow-sm">
              <LatticeLoader size={22} stepMs={700} />
            </div>
            <div>
              <div className="text-base font-bold tracking-tight text-foreground flex items-center gap-1.5">
                <span>Lattice</span>
                <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-surface border border-surface-border text-primary font-normal">
                  mesh
                </span>
              </div>
              <div className="text-[11px] text-muted-foreground">
                Distributed Platform
              </div>
            </div>
          </Link>
        </div>

        {/* User Greeting & Workspace Profile */}
        <div className="px-5 py-3.5 border-b border-surface-border/40 bg-surface/20">
          <div className="text-xs font-medium text-foreground">
            Hi, {user.name}
          </div>
          <div className="text-[11px] text-muted-foreground truncate flex items-center gap-1.5 mt-0.5">
            <span className="w-1.5 h-1.5 rounded-full bg-primary" />
            <span>{user.workspace}</span>
          </div>
        </div>

        {/* Main Navigation */}
        <nav className="p-3 space-y-1">
          {navLinks.map((item) => {
            const Icon = item.icon;
            const isActive =
              item.href === "/dashboard"
                ? pathname === "/dashboard" || pathname === "/"
                : pathname.startsWith(item.href);

            return (
              <Link
                key={item.title}
                href={item.href}
                className={`flex items-center gap-3 px-3 py-2 rounded-md text-xs font-medium transition-colors ${
                  isActive
                    ? "bg-surface-active text-foreground font-semibold border border-surface-border shadow-sm"
                    : "text-muted-foreground hover:text-foreground hover:bg-surface/50"
                }`}
              >
                <Icon
                  className={`w-4 h-4 ${
                    isActive ? "text-primary" : "text-muted-foreground"
                  }`}
                />
                <span>{item.title}</span>
              </Link>
            );
          })}
        </nav>

        {/* Create Pool Action Button */}
        <div className="px-3 pt-3">
          <button
            onClick={openCreatePoolModal}
            className="w-full flex items-center justify-center gap-2 py-2 px-3 rounded-md bg-primary/10 border border-primary/30 text-primary hover:bg-primary/20 text-xs font-semibold transition-all shadow-sm"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>Create Connection Pool</span>
          </button>
        </div>

        {/* Download Lattice Action */}
        <div className="px-3 pt-2">
          <button
            onClick={openDownloadModal}
            className="w-full flex items-center justify-center gap-2 py-2 px-3 rounded-md bg-surface border border-surface-border text-zinc-300 hover:text-white hover:bg-surface-hover text-xs font-medium transition-all"
          >
            <Download className="w-3.5 h-3.5 text-zinc-400" />
            <span>Download Lattice</span>
          </button>
        </div>

        {/* Active Pools Quick List */}
        {pools.length > 0 && (
          <div className="px-4 pt-5 pb-2">
            <div className="text-[10px] font-semibold text-zinc-500 uppercase tracking-wider mb-2">
              Connection Pools
            </div>
            <div className="space-y-1">
              {pools.slice(0, 4).map((pool) => {
                const isPoolActive = pathname.includes(pool.id);
                return (
                  <Link
                    key={pool.id}
                    href={`/pools/${pool.id}`}
                    className={`flex items-center justify-between px-2 py-1.5 rounded text-xs transition-colors ${
                      isPoolActive
                        ? "text-foreground bg-surface font-medium"
                        : "text-zinc-400 hover:text-zinc-200"
                    }`}
                  >
                    <div className="flex items-center gap-2 truncate">
                      {pool.workerCount > 0 ? (
                        <CheckCircle2 className="w-3 h-3 text-emerald-400 shrink-0" />
                      ) : (
                        <Circle className="w-3 h-3 text-zinc-600 shrink-0" />
                      )}
                      <span className="truncate">{pool.name}</span>
                    </div>
                    <span className="text-[10px] font-mono text-zinc-500 shrink-0">
                      {pool.workerCount}w
                    </span>
                  </Link>
                );
              })}
            </div>
          </div>
        )}
      </div>

      {/* Footer Info */}
      <div className="p-4 border-t border-surface-border/60 bg-surface/10 text-[11px] text-muted-foreground flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <Terminal className="w-3 h-3 text-zinc-500" />
          <span>v1.0.0</span>
        </div>
        <span className="text-[10px] text-zinc-600 font-mono">
          Control Plane
        </span>
      </div>
    </aside>
  );
}
