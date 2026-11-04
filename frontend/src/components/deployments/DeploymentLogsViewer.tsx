"use client";

import React, { useState, useRef, useEffect, useMemo } from "react";
import { DeploymentLogEntry } from "@/types/contracts";
import {
  Search,
  Copy,
  Check,
  Download,
  ArrowDown,
  Terminal,
  Radio,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { LatticeLoader } from "@/components/ui/LatticeLoader";
import { toast } from "sonner";
import { formatDate } from "@/lib/utils/formatters";

interface DeploymentLogsViewerProps {
  logs: DeploymentLogEntry[];
  isLoading?: boolean;
  isLive?: boolean;
  className?: string;
}

export function DeploymentLogsViewer({
  logs,
  isLoading = false,
  isLive = true,
  className,
}: DeploymentLogsViewerProps) {
  const [activeTab, setActiveTab] = useState<
    "all" | "build" | "runtime" | "events"
  >("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [autoScroll, setAutoScroll] = useState(true);
  const [copied, setCopied] = useState(false);

  const terminalEndRef = useRef<HTMLDivElement>(null);

  // Filter logs by tab and search
  const filteredLogs = useMemo(() => {
    return logs.filter((log) => {
      // Tab filter
      const msg = (log.message || "").toLowerCase();
      if (activeTab === "build") {
        const isBuild =
          msg.includes("cloning") ||
          msg.includes("docker") ||
          msg.includes("building") ||
          msg.includes("pushing") ||
          msg.includes("image");
        if (!isBuild) return false;
      } else if (activeTab === "runtime") {
        const isRuntime =
          log.container_id ||
          msg.includes("started") ||
          msg.includes("listening") ||
          msg.includes("uvicorn") ||
          msg.includes("node");
        if (!isRuntime) return false;
      } else if (activeTab === "events") {
        const isEvent =
          msg.includes("status_transition") ||
          msg.includes("health") ||
          msg.includes("ready") ||
          msg.includes("queued");
        if (!isEvent) return false;
      }

      // Query filter
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        return (
          msg.includes(q) ||
          log.log_level.toLowerCase().includes(q) ||
          (log.container_id && log.container_id.toLowerCase().includes(q))
        );
      }

      return true;
    });
  }, [logs, activeTab, searchQuery]);

  // Handle auto-scroll to bottom
  useEffect(() => {
    if (autoScroll && terminalEndRef.current) {
      terminalEndRef.current.scrollIntoView({ behavior: "auto" });
    }
  }, [filteredLogs, autoScroll]);

  const handleCopy = async () => {
    const text = filteredLogs
      .map(
        (l) =>
          `[${formatDate(l.timestamp)}] [${l.log_level.toUpperCase()}] ${l.message}`,
      )
      .join("\n");
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      toast.error(
        "Clipboard unavailable. Select the diagnostics to copy manually.",
      );
      return;
    }
    setCopied(true);
    toast.success("Logs copied to clipboard");
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownload = () => {
    const text = filteredLogs
      .map(
        (l) =>
          `[${formatDate(l.timestamp)}] [${l.log_level.toUpperCase()}] ${l.message}`,
      )
      .join("\n");
    const blob = new Blob([text], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `lattice-deployment-logs-${Date.now()}.log`;
    a.click();
    URL.revokeObjectURL(url);
    toast.success("Log file downloaded");
  };

  return (
    <div
      className={`rounded-lg border border-surface-border bg-black/95 font-mono text-xs overflow-hidden flex flex-col shadow-2xl ${className || ""}`}
    >
      {/* Top Bar: Tabs & Controls */}
      <div className="flex flex-wrap items-center justify-between border-b border-surface-border/80 bg-surface/50 px-3 py-2 gap-2 shrink-0">
        {/* Category Tabs */}
        <div className="flex items-center space-x-1">
          {[
            { id: "all", label: "All Logs" },
            { id: "build", label: "Build" },
            { id: "runtime", label: "Runtime" },
            { id: "events", label: "Events" },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id as any)}
              className={`px-2.5 py-1 rounded text-xs transition-colors ${
                activeTab === tab.id
                  ? "bg-surface-active text-zinc-100 font-medium"
                  : "text-zinc-400 hover:text-zinc-200"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Live Status indicator */}
        <div className="flex items-center gap-1.5 text-[11px] text-zinc-400">
          <Radio
            className={`w-3 h-3 ${isLive ? "text-primary animate-pulse" : "text-zinc-600"}`}
          />
          <span>{isLive ? "Polling diagnostics" : "Stored diagnostics"}</span>
        </div>

        {/* Actions: Search, AutoScroll, Copy, Download */}
        <div className="flex items-center gap-2">
          {/* Search Input */}
          <div className="relative">
            <Search className="w-3.5 h-3.5 absolute left-2 top-2 text-zinc-500" />
            <input
              type="text"
              placeholder="Search logs..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="h-7 w-36 sm:w-44 rounded border border-surface-border bg-black/50 pl-7 pr-2 text-[11px] text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:border-accent"
            />
          </div>

          {/* Auto-scroll toggle */}
          <button
            onClick={() => setAutoScroll(!autoScroll)}
            className={`p-1.5 rounded border transition-colors ${
              autoScroll
                ? "bg-primary/10 border-primary/30 text-primary"
                : "border-surface-border text-zinc-400 hover:text-zinc-200"
            }`}
            title={autoScroll ? "Auto-scroll ON" : "Auto-scroll OFF"}
          >
            <ArrowDown className="w-3.5 h-3.5" />
          </button>

          {/* Copy button */}
          <button
            onClick={handleCopy}
            className="p-1.5 rounded border border-surface-border text-zinc-400 hover:text-zinc-200 hover:bg-surface transition-colors"
            title="Copy logs"
          >
            {copied ? (
              <Check className="w-3.5 h-3.5 text-emerald-400" />
            ) : (
              <Copy className="w-3.5 h-3.5" />
            )}
          </button>

          {/* Download button */}
          <button
            onClick={handleDownload}
            className="p-1.5 rounded border border-surface-border text-zinc-400 hover:text-zinc-200 hover:bg-surface transition-colors"
            title="Download log file"
          >
            <Download className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Terminal Output Area */}
      <div className="p-4 overflow-y-auto space-y-1 max-h-[500px] min-h-[260px] font-mono leading-relaxed select-text">
        {isLoading && filteredLogs.length === 0 ? (
          <div className="text-zinc-500 flex items-center gap-2 py-8 justify-center">
            <LatticeLoader size={48} />
            <span>Loading deployment diagnostics…</span>
          </div>
        ) : filteredLogs.length === 0 ? (
          <div className="text-zinc-600 py-8 text-center">
            {searchQuery
              ? `No log lines matching "${searchQuery}"`
              : "No logs recorded for this deployment yet."}
          </div>
        ) : (
          filteredLogs.map((log, idx) => {
            const isError =
              log.log_level === "error" || log.log_level === "critical";
            const isWarning = log.log_level === "warning";
            const isInfo = log.log_level === "info";

            return (
              <div
                key={idx}
                className={`flex items-start gap-2.5 hover:bg-zinc-900/50 px-1 rounded transition-colors ${
                  isError
                    ? "text-rose-400 bg-rose-500/5"
                    : isWarning
                      ? "text-amber-400"
                      : "text-zinc-300"
                }`}
              >
                {/* Timestamp */}
                <span className="text-zinc-600 shrink-0 text-[11px] select-none">
                  {formatDate(log.timestamp)}
                </span>

                {/* Level badge */}
                <span
                  className={`text-[10px] uppercase font-bold shrink-0 select-none ${
                    isError
                      ? "text-rose-400"
                      : isWarning
                        ? "text-amber-400"
                        : isInfo
                          ? "text-sky-400"
                          : "text-zinc-500"
                  }`}
                >
                  [{log.log_level}]
                </span>

                {/* Log Message */}
                <span className="whitespace-pre-wrap break-all flex-1">
                  {log.message}
                </span>
              </div>
            );
          })
        )}
        <div ref={terminalEndRef} />
      </div>
    </div>
  );
}
