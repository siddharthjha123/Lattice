"use client";

import React from "react";
import { DeploymentTable } from "@/components/deployments/DeploymentTable";
import { ErrorState } from "@/components/ui/ErrorState";
import { useDeployments } from "@/hooks/useDeployments";
import { Button } from "@/components/ui/Button";
import { Rocket, Plus } from "lucide-react";
import Link from "next/link";

export default function DeploymentsPage() {
  const {
    data: deployments = [],
    isLoading,
    error,
    refetch,
  } = useDeployments();

  if (error)
    return <ErrorState message={error.message} onRetry={() => refetch()} />;
  return (
    <>
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-surface-border/60 pb-6">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-foreground">
            Deployments
          </h1>
          <p className="text-xs sm:text-sm text-muted-foreground mt-1">
            Manage and monitor all containerized application deployments across
            your distributed Lattice mesh.
          </p>
        </div>

        <Link href="/deployments/new">
          <Button variant="primary" size="sm" className="gap-1.5 shadow-sm">
            <Plus className="w-3.5 h-3.5" />
            <span>New Deployment</span>
          </Button>
        </Link>
      </div>

      {/* Main Deployments Table */}
      <div className="space-y-4">
        {isLoading ? (
          <div className="py-16 text-center text-xs text-muted-foreground">
            Loading deployments from Control Plane...
          </div>
        ) : (
          <DeploymentTable deployments={deployments} />
        )}
      </div>
    </>
  );
}
