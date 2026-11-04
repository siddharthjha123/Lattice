"use client";

import React, { useState } from "react";
import { useAuthStore } from "@/stores/authStore";
import { useHealth } from "@/hooks/useWorkers";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import {
  Settings,
  Lock,
  Server,
  User,
  Radio,
  CheckCircle2,
  AlertTriangle,
} from "lucide-react";
import { toast } from "sonner";
import { useRouter } from "next/navigation";
import { verifyOperator } from "@/lib/api/client";
import { API_BASE_URL } from "@/lib/api/client";

export default function SettingsPage() {
  const { user, setUser, token, setToken, logout } = useAuthStore();
  const router = useRouter();
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [userName, setUserName] = useState(user.name);
  const [userWorkspace, setUserWorkspace] = useState(user.workspace);
  const [adminToken, setAdminToken] = useState(token);

  const {
    data: health,
    refetch: testHealth,
    isFetching: isTesting,
  } = useHealth();

  const handleSaveProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setSaveError("");
    try {
      await verifyOperator(adminToken);
      setUser({
        name: userName.trim() || "Operator",
        workspace: userWorkspace.trim() || "Controller workspace",
      });
      setToken(adminToken.trim());
      toast.success(
        "Operator authorization verified; local preferences saved.",
      );
    } catch (err) {
      setSaveError(
        err instanceof Error ? err.message : "Unable to verify credentials.",
      );
    } finally {
      setSaving(false);
    }
  };

  const isHealthy = health?.status === "healthy";

  return (
    <>
      <div className="border-b border-surface-border/60 pb-6">
        <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-foreground">
          Platform Settings
        </h1>
        <p className="text-xs sm:text-sm text-muted-foreground mt-1">
          Verify operator authorization and configure local display preferences.
          Controller origin is configured server-side with CONTROL_PLANE_URL.
        </p>
      </div>

      <div className="max-w-3xl space-y-6">
        {/* Connection Health Status Card */}
        <Card className="p-5 border border-surface-border bg-card space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <Server className="w-4 h-4 text-primary" />
              <h3 className="text-sm font-semibold text-foreground">
                Control Plane Backend Status
              </h3>
            </div>

            <Badge variant={isHealthy ? "healthy" : "warning"} showDot>
              {isHealthy ? "Online & Healthy" : "Offline / Unreachable"}
            </Badge>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs font-mono text-zinc-400 bg-surface/30 p-3 rounded-lg border border-surface-border/50">
            <div>
              <span className="text-zinc-500 block">REST API Endpoint:</span>
              <span className="text-zinc-200">{API_BASE_URL}</span>
            </div>
            <div>
              <span className="text-zinc-500 block">Database Status:</span>
              <span className="text-zinc-200">
                {health?.database || "Unknown"}
              </span>
            </div>
          </div>

          <div className="flex items-center justify-end">
            <Button
              variant="outline"
              size="sm"
              onClick={() => testHealth()}
              isLoading={isTesting}
              className="text-xs"
            >
              Test Backend Connection
            </Button>
          </div>
        </Card>

        {/* Profile & Auth Form */}
        <form onSubmit={handleSaveProfile} className="space-y-6">
          <Card className="p-5 border border-surface-border bg-card space-y-4">
            <div className="flex items-center gap-2.5 border-b border-surface-border/60 pb-3">
              <User className="w-4 h-4 text-primary" />
              <h3 className="text-sm font-semibold text-foreground">
                Local Display Preferences
              </h3>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold text-zinc-300 uppercase tracking-wider mb-1.5">
                  Display Name
                </label>
                <Input
                  value={userName}
                  onChange={(e) => setUserName(e.target.value)}
                  placeholder="e.g. My workstation"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-zinc-300 uppercase tracking-wider mb-1.5">
                  Workspace Title
                </label>
                <Input
                  value={userWorkspace}
                  onChange={(e) => setUserWorkspace(e.target.value)}
                  placeholder="e.g. Production Mesh"
                />
              </div>
            </div>
          </Card>

          <Card className="p-5 border border-surface-border bg-card space-y-4">
            <div className="flex items-center gap-2.5 border-b border-surface-border/60 pb-3">
              <Lock className="w-4 h-4 text-primary" />
              <h3 className="text-sm font-semibold text-foreground">
                Management Bearer Authorization
              </h3>
            </div>

            <div>
              <label className="block text-xs font-semibold text-zinc-300 uppercase tracking-wider mb-1.5">
                Admin Token (ADMIN_TOKEN)
              </label>
              <Input
                type="password"
                value={adminToken}
                onChange={(e) => setAdminToken(e.target.value)}
                placeholder="Paste your 32+ character ADMIN_TOKEN from .env..."
                className="font-mono text-xs"
              />
              <p className="mt-1.5 text-xs text-muted-foreground leading-relaxed">
                Adheres strictly to the integrated backend contract. All
                management requests to{" "}
                <code className="text-zinc-300 font-mono">
                  /api/workers/register
                </code>
                , <code className="text-zinc-300 font-mono">/api/boxes</code>,
                and{" "}
                <code className="text-zinc-300 font-mono">
                  /api/deployments
                </code>{" "}
                require this token.
              </p>
            </div>
          </Card>

          {saveError && (
            <p role="alert" className="text-sm text-rose-300">
              {saveError}
            </p>
          )}
          <div className="flex items-center justify-end gap-3">
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                logout();
                router.replace("/login");
              }}
            >
              Sign out
            </Button>
            <Button
              isLoading={saving}
              type="submit"
              variant="primary"
              size="md"
            >
              Save Settings
            </Button>
          </div>
        </form>
      </div>
    </>
  );
}
