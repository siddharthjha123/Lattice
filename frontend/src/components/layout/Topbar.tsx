"use client";

import React from "react";
import { Breadcrumbs } from "./Breadcrumbs";
import { useHealth, useWorkers } from "@/hooks/useWorkers";
import { Rocket, Radio, Shield, ExternalLink } from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/Button";

export function Topbar() {
  const { data: health, isError } = useHealth();
  const { data: workers = [] } = useWorkers();

  const isConnected = !isError && health?.status === "healthy";
  const onlineCount = workers.filter((w) => w.status === "online").length;

  return (
    <header className="h-14 border-b border-surface-border bg-card/60 backdrop-blur-md px-6 flex items-center justify-between shrink-0 sticky top-0 z-20">
      {/* Left: Breadcrumbs */}
      <div className="flex items-center gap-4">
        <Breadcrumbs />
      </div>

      {/* Right: Cluster Health & Quick Actions */}
      <div className="flex items-center gap-4">
        {/* Mesh connection indicator */}
        <div className="hidden lg:flex items-center gap-2 px-2.5 py-1 rounded-full bg-surface border border-surface-border text-xs">
          <Radio
            className={`w-3 h-3 ${
              isConnected ? "text-emerald-400 animate-pulse" : "text-amber-400"
            }`}
          />
          <span className="text-zinc-300 font-medium">
            {isConnected
              ? "Control Plane Connected"
              : isError
                ? "Controller unavailable"
                : "Connecting to Mesh"}
          </span>
          <span className="text-zinc-600">|</span>
          <span className="font-mono text-zinc-400">
            {onlineCount} {onlineCount === 1 ? "worker" : "workers"} online
          </span>
        </div>

        {/* Deploy button */}
        <Link href="/deployments/new">
          <Button
            variant="primary"
            size="sm"
            className="gap-1.5 h-8 text-xs font-semibold shadow-sm"
          >
            <Rocket className="w-3.5 h-3.5" />
            <span>New Deployment</span>
          </Button>
        </Link>
      </div>
    </header>
  );
}
