"use client";

import React from "react";
import { WorkerSnapshot } from "@/types/contracts";
import { WorkerCard } from "./WorkerCard";

export function WorkerList({
  workers,
  className,
}: {
  workers: WorkerSnapshot[];
  className?: string;
}) {
  return (
    <div
      className={`grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4 ${className || ""}`}
    >
      {workers.map((worker) => (
        <WorkerCard key={worker.worker_id} worker={worker} />
      ))}
    </div>
  );
}
