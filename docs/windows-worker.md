# Windows worker setup

Use ordinary PowerShell, Python 3.12 and Docker Desktop in Linux-container mode. The central controller requires a POSIX host or WSL; installing a Windows worker does not change that requirement.

From the repository root:

```powershell
$LatticeVenv = Join-Path $env:LOCALAPPDATA 'Lattice\venv'
py -3.12 -m venv $LatticeVenv
& "$LatticeVenv\Scripts\python.exe" -m pip install .
$LatticeCli = Join-Path $LatticeVenv 'Scripts\lattice.exe'
& $LatticeCli --help
```

Alternatively install an actual controller-served wheel after the operator has built and configured it. No wheel URL is live merely because it appears in the dashboard.

```powershell
$LatticeState = Join-Path $env:USERPROFILE '.lattice\pools\development'
& $LatticeCli connect --server https://api.example.com --pool-name development --state-dir $LatticeState
```

Replace the example domain with your controller and enter its join code privately. Configure read-only registry credentials on this machine if images are private. `docker info` must succeed in the same user session. Check daemon CPU/RAM and Linux image architecture compatibility.

Owner controls use authenticated loopback RPC on Windows. Run status/pause/resume/disconnect with the same state directory. Do not remove state to bypass a live process lock. Pausing persists until resumed; disconnect stops owned execution without introducing a new persistent pause.

If startup fails, identify whether Docker, enrollment, registry authorization, image architecture, available resources or the network is responsible. Do not distribute the controller's admin token to workers. Native Windows operation still needs validation on your hardware.
