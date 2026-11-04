"use client";
import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useAuthStore } from "@/stores/authStore";
import { DashboardLayout } from "./DashboardLayout";
import { LoadingState } from "@/components/ui/LoadingState";
export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { hydrated, isAuthenticated, preview, hydrate } = useAuthStore();
  useEffect(() => {
    void hydrate();
  }, [hydrate]);
  useEffect(() => {
    if (hydrated && !isAuthenticated && !preview && pathname !== "/login")
      router.replace("/login");
  }, [hydrated, isAuthenticated, preview, pathname, router]);
  if (pathname === "/login") return <>{children}</>;
  if (!hydrated || (!isAuthenticated && !preview))
    return (
      <div className="p-12">
        <LoadingState text="Checking operator session…" />
      </div>
    );
  return <DashboardLayout>{children}</DashboardLayout>;
}
