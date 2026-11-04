"use client";
import { useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useDeletePool } from "@/hooks/usePools";
import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/modals/ConfirmDialog";
export function DeletePoolButton({
  poolId,
  poolName,
}: {
  poolId: string;
  poolName: string;
}) {
  const [open, setOpen] = useState(false);
  const remove = useDeletePool();
  const router = useRouter();
  const pathname = usePathname();
  return (
    <>
      <Button
        variant="destructive"
        size="sm"
        onClick={() => {
          remove.reset();
          setOpen(true);
        }}
      >
        Delete pool
      </Button>
      <ConfirmDialog
        isOpen={open}
        onClose={() => setOpen(false)}
        title={`Delete pool "${poolName}"?`}
        description="Remove all workers and Boxes first. This removes the pool from active lists and revokes its enrollment code. Deployment history is retained, and this pool name remains reserved."
        confirmText="Delete pool"
        isLoading={remove.isPending}
        error={remove.error?.message}
        onConfirm={() =>
          remove.mutate(poolId, {
            onSuccess: () => {
              setOpen(false);
              if (pathname?.startsWith(`/pools/${poolId}`))
                router.replace("/pools");
            },
          })
        }
      />
    </>
  );
}
