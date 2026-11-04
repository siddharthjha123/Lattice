import { Deployment } from "./contracts";

export interface Project {
  projectId: string;
  name: string;
  repositoryUrl: string;
  owner: string;
  productionDeployment?: Deployment | null;
  latestDeployment?: Deployment | null;
  deploymentCount: number;
  createdAt: string;
}
