import { LatticeLoader } from "@/components/ui/LatticeLoader";

export default function Loading() {
  return (
    <div className="min-h-screen bg-background flex flex-col items-center justify-center gap-4 text-muted-foreground">
      <LatticeLoader size={80} />
      <span className="text-xs font-mono tracking-wider uppercase text-zinc-500">
        Loading Lattice Mesh...
      </span>
    </div>
  );
}
