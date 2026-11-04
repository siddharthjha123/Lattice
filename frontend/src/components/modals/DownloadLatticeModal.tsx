"use client";

import React, { useState } from "react";
import { PLATFORM_DOWNLOADS } from "@/lib/constants/downloads";
import { Copy, Check, Terminal, Apple, Monitor, Box, Cpu } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { toast } from "sonner";
import { LargeDetailModal } from "./LargeDetailModal";

const ICON_MAP: Record<string, React.ReactNode> = {
  Apple: <Apple className="w-4 h-4" />,
  Terminal: <Terminal className="w-4 h-4" />,
  Monitor: <Monitor className="w-4 h-4" />,
  Container: <Box className="w-4 h-4" />,
  Cpu: <Cpu className="w-4 h-4" />,
};

export function DownloadLatticeModal({
  isOpen,
  onClose,
}: {
  isOpen: boolean;
  onClose: () => void;
}) {
  const [selectedId, setSelectedId] = useState("macos");
  const [copiedCmd, setCopiedCmd] = useState(false);
  const [copiedVerify, setCopiedVerify] = useState(false);

  const current =
    PLATFORM_DOWNLOADS.find((p) => p.id === selectedId) ||
    PLATFORM_DOWNLOADS[0];

  const handleCopy = async (text: string, isVerify: boolean = false) => {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      toast.error(
        "Clipboard unavailable. Select and copy the command manually.",
      );
      return;
    }
    if (isVerify) {
      setCopiedVerify(true);
      setTimeout(() => setCopiedVerify(false), 2000);
    } else {
      setCopiedCmd(true);
      setTimeout(() => setCopiedCmd(false), 2000);
    }
    toast.success("Command copied to clipboard");
  };

  return (
    <LargeDetailModal
      isOpen={isOpen}
      onClose={onClose}
      title="Download & Install Lattice Agent"
      subtitle="Connect developer workstations, and supported edge computers to your distributed mesh"
    >
      <div className="grid grid-cols-1 md:grid-cols-12 gap-6 h-full">
        {/* Left: Platform tabs */}
        <div className="md:col-span-4 flex flex-col space-y-2 border-r border-surface-border/60 pr-6">
          <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-1">
            Target Platform
          </span>
          {PLATFORM_DOWNLOADS.map((platform) => {
            const isSelected = platform.id === selectedId;
            return (
              <button
                key={platform.id}
                onClick={() => setSelectedId(platform.id)}
                className={`flex items-center justify-between p-3 rounded-lg border text-left transition-all ${
                  isSelected
                    ? "bg-surface-active border-accent/40 text-foreground shadow-sm"
                    : "bg-surface/40 border-surface-border text-muted-foreground hover:bg-surface-hover hover:text-foreground"
                }`}
              >
                <div className="flex items-center gap-3">
                  <div
                    className={`p-2 rounded-md ${
                      isSelected
                        ? "bg-accent/10 text-accent"
                        : "bg-surface text-muted-foreground"
                    }`}
                  >
                    {ICON_MAP[platform.iconName] || (
                      <Terminal className="w-4 h-4" />
                    )}
                  </div>
                  <div>
                    <div className="text-sm font-medium text-foreground">
                      {platform.name}
                    </div>
                    {platform.badge && (
                      <div className="text-[11px] text-muted-foreground">
                        {platform.badge}
                      </div>
                    )}
                  </div>
                </div>
              </button>
            );
          })}
        </div>

        {/* Right: Instructions & commands */}
        <div className="md:col-span-8 flex flex-col space-y-6">
          <div>
            <h3 className="text-base font-semibold text-foreground">
              Installing on {current.name}
            </h3>
            <p className="mt-1 text-xs text-muted-foreground leading-relaxed">
              {current.instructions}
            </p>
          </div>

          {/* Installation snippet */}
          <div className="space-y-2">
            <span className="text-xs font-semibold text-zinc-400">
              1. Installation Command
            </span>
            <div className="relative rounded-lg border border-surface-border bg-black/90 p-4 font-mono text-xs text-zinc-200 overflow-x-auto flex items-center justify-between">
              <span className="text-emerald-400 select-none mr-3">$</span>
              <code className="flex-1 overflow-x-auto whitespace-pre">
                {current.command}
              </code>
              <Button
                variant="outline"
                size="sm"
                disabled={current.supported === false}
                onClick={() => handleCopy(current.command, false)}
                className="ml-3 h-7 px-2.5 text-xs gap-1 border-surface-border text-zinc-400 hover:text-zinc-100 hover:bg-surface"
              >
                {copiedCmd ? (
                  <>
                    <Check className="w-3.5 h-3.5 text-emerald-400" />
                    <span>Copied</span>
                  </>
                ) : (
                  <>
                    <Copy className="w-3.5 h-3.5" />
                    <span>Copy</span>
                  </>
                )}
              </Button>
            </div>
          </div>

          {/* Verify version command */}
          <div className="space-y-2">
            <span className="text-xs font-semibold text-zinc-400">
              2. Verify Installation
            </span>
            <div className="relative rounded-lg border border-surface-border bg-black/90 p-4 font-mono text-xs text-zinc-200 overflow-x-auto flex items-center justify-between">
              <span className="text-emerald-400 select-none mr-3">$</span>
              <code className="flex-1">{current.verifyCommand}</code>
              <Button
                variant="outline"
                size="sm"
                disabled={current.supported === false}
                onClick={() => handleCopy(current.verifyCommand, true)}
                className="ml-3 h-7 px-2.5 text-xs gap-1 border-surface-border text-zinc-400 hover:text-zinc-100 hover:bg-surface"
              >
                {copiedVerify ? (
                  <>
                    <Check className="w-3.5 h-3.5 text-emerald-400" />
                    <span>Copied</span>
                  </>
                ) : (
                  <>
                    <Copy className="w-3.5 h-3.5" />
                    <span>Copy</span>
                  </>
                )}
              </Button>
            </div>
          </div>

          {/* Next steps note */}
          <div className="rounded-lg border border-surface-border/70 bg-surface/30 p-4 text-xs text-muted-foreground space-y-1.5">
            <div className="font-medium text-zinc-300">
              Next Step: Join a Pool
            </div>
            <p>
              Once installed, return to your Connection Pool page and run the
              generated{" "}
              <code className="text-emerald-400 font-mono">
                lattice connect
              </code>{" "}
              command to register this machine into your distributed cluster.
            </p>
          </div>
        </div>
      </div>
    </LargeDetailModal>
  );
}
