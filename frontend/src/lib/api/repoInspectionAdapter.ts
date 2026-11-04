/** Missing controller inspection endpoint: this adapter uses real public GitHub responses only. */
import { RepositoryInspection } from "@/types/repository";
export function parseGitHubUrl(value: string) {
  try {
    const u = new URL(value);
    if (
      u.protocol !== "https:" ||
      u.hostname !== "github.com" ||
      u.username ||
      u.password ||
      u.search ||
      u.hash
    )
      return null;
    const match = u.pathname.match(
      /^\/([A-Za-z0-9_.-]+)\/([A-Za-z0-9_.-]+)\/?$/,
    );
    return match
      ? { owner: match[1], repo: match[2].replace(/\.git$/, "") }
      : null;
  } catch {
    return null;
  }
}
async function github(path: string) {
  const res = await fetch("https://api.github.com" + path, {
    headers: { Accept: "application/vnd.github+json" },
    cache: "no-store",
    signal: AbortSignal.timeout(15000),
  });
  if (!res.ok)
    throw new Error(
      `GitHub inspection unavailable (HTTP ${res.status}). Check the repository/branch, or continue with manual configuration.`,
    );
  return res.json();
}
export async function inspectRepository(
  url: string,
  selectedBranch?: string,
): Promise<RepositoryInspection> {
  const parsed = parseGitHubUrl(url);
  if (!parsed)
    throw new Error("Enter a plain public HTTPS GitHub owner/repository URL.");
  const base = `/repos/${parsed.owner}/${parsed.repo}`;
  const repo = await github(base);
  const branch = selectedBranch || repo.default_branch;
  const [branches, commit, files] = await Promise.all([
    github(base + "/branches?per_page=100"),
    github(base + "/commits/" + encodeURIComponent(branch)),
    github(base + "/contents?ref=" + encodeURIComponent(branch)),
  ]);
  if (
    !commit.sha ||
    !commit.commit?.author?.date ||
    !Array.isArray(files) ||
    !Array.isArray(branches)
  )
    throw new Error(
      "GitHub returned incomplete metadata. Use manual configuration instead.",
    );
  const names = files.map((f: { name: string }) => f.name);
  const node = names.includes("package.json");
  let start: string[] = [];
  let port = 8000;
  let readiness = "/";
  let framework = "Not determined";
  const read = async (name: string) => {
    const file = await github(
      base + "/contents/" + name + "?ref=" + encodeURIComponent(branch),
    );
    if (file.size > 65536 || file.encoding !== "base64")
      throw new Error("Configuration file is too large or unsupported.");
    return atob(file.content.replace(/\s/g, ""));
  };
  if (names.includes("lattice.json")) {
    const c = JSON.parse(await read("lattice.json"));
    if (
      Array.isArray(c.start_command) &&
      c.start_command.every((x: unknown) => typeof x === "string")
    )
      start = c.start_command;
    if (Number.isInteger(c.internal_port)) port = c.internal_port;
    if (typeof c.readiness_path === "string") readiness = c.readiness_path;
  } else if (node) {
    const p = JSON.parse(await read("package.json"));
    if (p.scripts?.start) start = ["npm", "start"];
    framework = p.dependencies?.next
      ? "Next.js"
      : p.dependencies?.express
        ? "Express"
        : "Node.js";
  } else if (names.includes("requirements.txt")) {
    const requirements = await read("requirements.txt");
    if (
      /(?:^|\n)flask[=<>~!\s]/i.test(requirements) &&
      names.includes("app.py")
    ) {
      framework = "Flask";
      if (/gunicorn/i.test(requirements))
        start = ["gunicorn", "app:app", "--bind", "0.0.0.0:8000"];
    } else if (/fastapi/i.test(requirements) && names.includes("main.py")) {
      framework = "FastAPI";
      start = [
        "python",
        "-m",
        "uvicorn",
        "main:app",
        "--host",
        "0.0.0.0",
        "--port",
        "8000",
      ];
    }
  }
  return {
    repositoryUrl: url,
    repoName: repo.name,
    owner: repo.owner.login,
    defaultBranch: repo.default_branch,
    availableBranches: branches.map((b: { name: string }) => b.name),
    latestCommit: {
      hash: commit.sha,
      message: commit.commit.message,
      author: commit.commit.author.name,
      timestamp: commit.commit.author.date,
    },
    detectedLanguage: repo.language || "Not reported",
    detectedFramework: framework,
    applicationType: node ? "node" : "python",
    hasDockerfile: names.includes("Dockerfile"),
    hasLatticeJson: names.includes("lattice.json"),
    suggestedStartCommand: start,
    suggestedInternalPort: port,
    suggestedReadinessPath: readiness,
  };
}
