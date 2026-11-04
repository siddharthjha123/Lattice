"use client";

import React, { Suspense } from "react";
import { DeploymentWizard } from "@/components/deployments/DeploymentWizard";
import { LoadingState } from "@/components/ui/LoadingState";

export default function NewDeploymentPage() {
  return (
    <>
      <Suspense
        fallback={<LoadingState text="Preparing deployment wizard..." />}
      >
        <DeploymentWizard />
      </Suspense>
    </>
  );
}
