"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { CheckCircle2 } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { LargeDetailModal } from "./LargeDetailModal";
import { ConnectionCommand } from "@/components/pools/ConnectionCommand";
import { useCreatePool } from "@/hooks/usePools";
export function CreatePoolModal({
  isOpen,
  onClose,
}: {
  isOpen: boolean;
  onClose: () => void;
}) {
  const [name, setName] = useState("");
  const [hours, setHours] = useState(24);
  const [joins, setJoins] = useState(10);
  const router = useRouter();
  const create = useCreatePool();
  const close = () => {
    if (create.isPending) return;
    create.reset();
    setName("");
    onClose();
  };
  return (
    <LargeDetailModal
      isOpen={isOpen}
      onClose={close}
      title="Create Connection Pool"
      subtitle="Connect your computers to create a distributed compute pool."
    >
      <div className="max-w-xl mx-auto py-6 space-y-6">
        {create.data ? (
          <>
            <div className="flex items-center gap-3">
              <CheckCircle2 className="w-8 h-8 text-primary" />
              <div>
                <h3 className="text-lg font-semibold">Pool created</h3>
                <p className="text-xs text-zinc-400">
                  Confirmed by the controller. Save the enrollment code before
                  leaving.
                </p>
              </div>
            </div>
            <ConnectionCommand
              joinCode={create.data.joinCode}
              poolName={create.data.name}
              poolId={create.data.id}
              expiresAt={create.data.expiresAt}
            />
            <Button
              onClick={() => {
                const id = create.data.id;
                close();
                router.push(`/pools/${id}`);
              }}
            >
              Open pool dashboard
            </Button>
          </>
        ) : (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              create.mutate({ name, expires_hours: hours, max_joins: joins });
            }}
            className="space-y-5"
          >
            <div>
              <label htmlFor="pool-name" className="text-sm">
                Pool name
              </label>
              <Input
                id="pool-name"
                required
                pattern="[a-z][a-z0-9-]{2,47}"
                minLength={3}
                maxLength={48}
                placeholder="development"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
              <p className="text-xs text-zinc-500 mt-2">
                3–48 lowercase letters, numbers or hyphens; start with a letter.
              </p>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <label className="text-sm">
                Code validity (hours)
                <Input
                  type="number"
                  min={1}
                  max={168}
                  value={hours}
                  onChange={(e) => setHours(Number(e.target.value))}
                  required
                />
              </label>
              <label className="text-sm">
                Maximum enrollments
                <Input
                  type="number"
                  min={1}
                  max={100}
                  value={joins}
                  onChange={(e) => setJoins(Number(e.target.value))}
                  required
                />
              </label>
            </div>
            {create.error && (
              <p role="alert" className="text-sm text-rose-300">
                {create.error.message}
              </p>
            )}
            <Button type="submit" isLoading={create.isPending}>
              Create pool
            </Button>
          </form>
        )}
      </div>
    </LargeDetailModal>
  );
}
