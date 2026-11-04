export const WORKER_SERVER =
  process.env.NEXT_PUBLIC_WORKER_SERVER || "http://127.0.0.1:8000";
export const WORKER_WHEEL =
  WORKER_SERVER + "/downloads/lattice-0.3.2-py3-none-any.whl";
export interface PlatformInstallOption {
  id: string;
  name: string;
  iconName: string;
  badge?: string;
  instructions: string;
  command: string;
  verifyCommand: string;
  supported?: boolean;
}
const unix = `python3 -m venv "$HOME/lattice-venv"
"$HOME/lattice-venv/bin/python" -m pip install --upgrade "${WORKER_WHEEL}"`;
export const PLATFORM_DOWNLOADS: PlatformInstallOption[] = [
  {
    id: "macos",
    name: "macOS",
    iconName: "Apple",
    badge: "Python 3.12+ · Linux-container Docker",
    instructions:
      "Install the controller-served Python wheel in a local environment. Keep Docker Desktop running; the worker runs as your ordinary user.",
    command: unix,
    verifyCommand: '"$HOME/lattice-venv/bin/lattice" --help',
  },
  {
    id: "windows",
    name: "Windows",
    iconName: "Monitor",
    badge: "PowerShell · Python 3.12+",
    instructions:
      "Use ordinary PowerShell with Docker Desktop's Linux-container engine. No Winget package or Ubuntu sudo password is required.",
    command: `$LatticeVenv = Join-Path $env:LOCALAPPDATA "Lattice\venv"
py -3 -m venv $LatticeVenv
& "$LatticeVenv\Scripts\python.exe" -m pip install --upgrade "${WORKER_WHEEL}"`,
    verifyCommand:
      '& "$env:LOCALAPPDATA\Lattice\venv\Scripts\lattice.exe" --help',
  },
  {
    id: "linux",
    name: "Linux",
    iconName: "Terminal",
    badge: "Python 3.12+ · Docker Engine",
    instructions:
      "Install the same wheel in an isolated local Python environment. The user must be able to access the local Linux Docker socket.",
    command: unix,
    verifyCommand: '"$HOME/lattice-venv/bin/lattice" --help',
  },
  {
    id: "raspberry-pi",
    name: "Raspberry Pi",
    iconName: "Cpu",
    badge: "64-bit ARM Linux",
    instructions:
      "Requires 64-bit ARM Linux, Python 3.12+ and Docker. ARM64 support is conditional on compatible application images; this is not a verified physical Pi trial.",
    command: unix,
    verifyCommand: '"$HOME/lattice-venv/bin/lattice" --help',
  },
  {
    id: "docker",
    name: "Docker",
    iconName: "Container",
    badge: "Worker image unavailable",
    supported: false,
    instructions:
      "A packaged worker service container has not been published. Use the host Python installation with Docker Engine; no image URL is invented here.",
    command: "No worker service container release is configured.",
    verifyCommand: "Use the host installation instructions instead.",
  },
];
export type WorkerPlatform = "windows" | "macos" | "linux";
export function joinCommand(
  poolName: string,
  code?: string | null,
  platform: WorkerPlatform = "macos",
) {
  if (!/^[a-z][a-z0-9-]{2,47}$/.test(poolName))
    throw new Error("Select a valid pool before copying its command.");
  if (code && !/^[A-Za-z0-9-]+$/.test(code))
    throw new Error("Enrollment code contains unsupported command characters.");
  const executable =
    platform === "windows"
      ? '& "$env:LOCALAPPDATA\\Lattice\\venv\\Scripts\\lattice.exe"'
      : '"$HOME/lattice-venv/bin/lattice"';
  const state =
    platform === "windows"
      ? `"$env:USERPROFILE\\.lattice\\pools\\${poolName}"`
      : `"$HOME/.lattice/pools/${poolName}"`;
  return `${executable} connect --server ${WORKER_SERVER} --pool-name ${poolName} --state-dir ${state}${code ? ` --pool-code ${code}` : ""}`;
}
