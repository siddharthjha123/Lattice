"use client";
import { useState } from "react";
import { Copy, Download, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/Button";
import { useUiStore } from "@/stores/uiStore";
import { useRotatePoolCode } from "@/hooks/usePools";
import { joinCommand, WorkerPlatform } from "@/lib/constants/downloads";
import { ConfirmDialog } from "@/components/modals/ConfirmDialog";
interface Props {
  joinCode: string | null;
  poolName: string;
  poolId?: string;
  expiresAt?: string;
  joinsUsed?: number;
  maxJoins?: number;
  className?: string;
}
export function ConnectionCommand({
  joinCode,
  poolName,
  poolId,
  expiresAt,
  joinsUsed = 0,
  maxJoins = 10,
  className,
}: Props) {
  const [includeCode, setIncludeCode] = useState(false);
  const [platform, setPlatform] = useState<WorkerPlatform>("windows");
  const [confirm, setConfirm] = useState(false);
  const openDownload = useUiStore((s) => s.openDownloadModal);
  const rotate = useRotatePoolCode();
  const expired =
    (!!expiresAt && new Date(expiresAt).getTime() <= Date.now()) ||
    joinsUsed >= maxJoins;
  const code = joinCode;
  const command = joinCommand(
    poolName,
    includeCode && !expired ? code : null,
    platform,
  );
  const copy = async (value: string) => {
    try {
      await navigator.clipboard.writeText(value);
      toast.success("Copied.");
    } catch {
      toast.error("Clipboard unavailable. Copy the text manually.");
    }
  };
  return (
    <div className={`space-y-4 ${className || ""}`}>
      <label className="block text-xs text-zinc-400">
        Worker platform
        <select
          aria-label="Worker command platform"
          value={platform}
          onChange={(event) =>
            setPlatform(event.target.value as WorkerPlatform)
          }
          className="block mt-2 rounded-md border border-surface-border bg-surface p-2 text-zinc-200"
        >
          <option value="windows">Windows (PowerShell)</option>
          <option value="macos">macOS</option>
          <option value="linux">Linux</option>
        </select>
      </label>
      <div className="rounded-lg border border-surface-border bg-black/80 p-4 flex gap-3 items-start">
        <code className="text-xs text-zinc-200 break-all flex-1 select-all">
          {command}
        </code>
        <Button size="sm" variant="outline" onClick={() => copy(command)}>
          <Copy className="w-3.5 h-3.5 mr-1" />
          Copy command
        </Button>
      </div>
      {code && !expired ? (
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-3 text-xs">
            <span>Enrollment code:</span>
            <code className="select-all text-primary">{code}</code>
            <Button variant="ghost" size="sm" onClick={() => copy(code)}>
              Copy code
            </Button>
          </div>
          <label className="flex items-center gap-2 text-xs text-zinc-400">
            <input
              type="checkbox"
              checked={includeCode}
              onChange={(e) => setIncludeCode(e.target.checked)}
            />
            Include the code in the command (also records it in shell history)
          </label>
        </div>
      ) : (
        <p className="text-xs text-zinc-400">
          {expired
            ? "This enrollment code has expired or reached its join limit."
            : "The server stores only a hash of the enrollment code. Use your saved code, or rotate it to generate a new one."}
        </p>
      )}
      <p className="text-xs text-zinc-500">
        The command prompts for the pool code. Existing workers reuse their
        saved enrollment in this pool's separate directory. Stop any old worker
        connection before switching pools; keep this connect terminal open.{" "}
        {expiresAt && `Code expiry: ${new Date(expiresAt).toLocaleString()}.`}{" "}
        {joinsUsed}/{maxJoins} enrollments used.
      </p>
      <div className="flex flex-wrap gap-3">
        <Button variant="outline" size="sm" onClick={openDownload}>
          <Download className="w-3.5 h-3.5 mr-2" />
          Install worker
        </Button>
        {poolId && (
          <Button
            variant="outline"
            size="sm"
            onClick={() => setConfirm(true)}
            isLoading={rotate.isPending}
          >
            <RefreshCw className="w-3.5 h-3.5 mr-2" />
            Rotate enrollment code
          </Button>
        )}
      </div>
      <ConfirmDialog
        isOpen={confirm}
        onClose={() => setConfirm(false)}
        title="Rotate this pool's enrollment code?"
        description="New enrollments must use the new code. Existing enrolled workers keep their credentials. The new code is shown in this session."
        confirmText="Rotate code"
        isLoading={rotate.isPending}
        onConfirm={() => {
          if (poolId)
            rotate.mutate(poolId, { onSuccess: () => setConfirm(false) });
        }}
      />
    </div>
  );
}
