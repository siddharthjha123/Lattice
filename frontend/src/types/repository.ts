import { ApplicationType } from "./contracts";

export interface GitCommit {
  hash: string;
  message: string;
  author: string;
  timestamp: string;
}

export interface RepositoryInspection {
  repositoryUrl: string;
  repoName: string;
  owner: string;
  defaultBranch: string;
  availableBranches: string[];
  latestCommit: GitCommit;
  detectedLanguage: string;
  detectedFramework: string;
  applicationType: ApplicationType;
  hasDockerfile: boolean;
  hasLatticeJson: boolean;
  suggestedStartCommand?: string[];
  suggestedInternalPort?: number;
  suggestedReadinessPath?: string;
}
