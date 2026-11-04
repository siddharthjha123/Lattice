"use client";

import React from "react";
import { Toaster } from "sonner";

export function ToastProvider() {
  return (
    <Toaster
      theme="dark"
      position="top-right"
      toastOptions={{
        className:
          "bg-surface border border-surface-border text-foreground font-sans shadow-xl",
      }}
    />
  );
}
