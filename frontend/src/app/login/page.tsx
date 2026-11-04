"use client";

import React, { useState } from "react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/stores/authStore";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Shield, ArrowRight, Lock } from "lucide-react";
import { toast } from "sonner";

export default function LoginPage() {
  const router = useRouter();
  const { user, login, explore } = useAuthStore();
  const [name, setName] = useState(user.name);
  const [adminToken, setAdminTokenInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const [error, setError] = useState("");
  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setError("");
    try {
      await login(adminToken, name);
      setAdminTokenInput("");
      toast.success("Operator authorization verified.");
      router.replace("/dashboard");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to verify operator.",
      );
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-background flex flex-col items-center justify-center p-4 selection:bg-primary/20 selection:text-primary">
      <div className="w-full max-w-md space-y-6">
        {/* Brand Header */}
        <div className="text-center space-y-2">
          <div className="w-14 h-14 rounded-2xl bg-surface border border-surface-border mx-auto flex items-center justify-center p-2.5 shadow-lg overflow-hidden">
            <Image
              src="/logo.png"
              alt="Lattice Logo"
              width={48}
              height={48}
              className="w-full h-full object-contain"
              priority
            />
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">
            Connect to Lattice
          </h1>
          <p className="text-xs text-muted-foreground">
            Distributed application deployment platform on developer-owned
            compute
          </p>
        </div>

        {/* Form Card */}
        <div className="rounded-xl border border-surface-border bg-card p-6 shadow-xl">
          <form onSubmit={handleLogin} className="space-y-4">
            <div>
              <label
                htmlFor="operator-name"
                className="block text-xs font-semibold text-zinc-300 uppercase tracking-wider mb-1.5"
              >
                Your Name
              </label>
              <Input
                id="operator-name"
                placeholder="Your display name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                autoFocus
              />
              <p className="mt-1 text-[11px] text-zinc-500">
                Used to personalize your dashboard and workspace session.
              </p>
            </div>

            <div>
              <label
                htmlFor="operator-token"
                className="block text-xs font-semibold text-zinc-300 uppercase tracking-wider mb-1.5 flex items-center justify-between"
              >
                <span>Management Bearer Token</span>
                <span className="text-[10px] text-zinc-500 font-normal">
                  Required
                </span>
              </label>
              <div className="relative">
                <Lock className="w-3.5 h-3.5 absolute left-3 top-3 text-zinc-500" />
                <Input
                  type="password"
                  id="operator-token"
                  autoComplete="off"
                  placeholder="Paste Control Plane ADMIN_TOKEN..."
                  value={adminToken}
                  onChange={(e) => setAdminTokenInput(e.target.value)}
                  className="pl-9 font-mono text-xs"
                />
              </div>
              <p className="mt-1 text-[11px] text-zinc-500">
                Verified against the controller. Kept only for this browser tab.
              </p>
            </div>

            {error && (
              <p role="alert" className="text-sm text-rose-300">
                {error}
              </p>
            )}
            <Button
              type="submit"
              variant="primary"
              className="w-full gap-2 mt-2"
              isLoading={isLoading}
            >
              <span>Continue to Dashboard</span>
              <ArrowRight className="w-4 h-4" />
            </Button>
            <Button
              type="button"
              variant="ghost"
              className="w-full"
              onClick={() => {
                explore();
                router.push("/dashboard");
              }}
            >
              Explore an empty preview
            </Button>
          </form>
        </div>

        {/* Architecture Notice */}
        <div className="p-3.5 rounded-lg border border-surface-border/60 bg-surface/30 text-xs text-muted-foreground flex items-center gap-3">
          <Shield className="w-4 h-4 text-primary shrink-0" />
          <span>
            This is an operator session using the existing controller bearer
            contract. The display name is a local preference; there are no
            backend user accounts.
          </span>
        </div>
      </div>
    </div>
  );
}
