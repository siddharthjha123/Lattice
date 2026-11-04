import React from "react";
import { DeploymentStatus } from "@/types/contracts";
import { Badge } from "@/components/ui/Badge";

export function DeploymentStatusBadge({
  status,
  className,
}: {
  status: DeploymentStatus | string;
  className?: string;
}) {
  switch (status) {
    case "running":
      return (
        <Badge variant="healthy" showDot className={className}>
          Ready
        </Badge>
      );
    case "building":
      return (
        <Badge variant="info" showDot className={className}>
          Building
        </Badge>
      );
    case "deploying":
      return (
        <Badge variant="info" showDot className={className}>
          Deploying
        </Badge>
      );
    case "queued":
      return (
        <Badge variant="warning" showDot className={className}>
          Queued
        </Badge>
      );
    case "failed":
      return (
        <Badge variant="unhealthy" showDot className={className}>
          Failed
        </Badge>
      );
    case "stopped":
      return (
        <Badge variant="offline" className={className}>
          Stopped
        </Badge>
      );
    default:
      return (
        <Badge variant="default" className={className}>
          {status}
        </Badge>
      );
  }
}
