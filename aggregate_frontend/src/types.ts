export interface Programme {
  id: number;
  name: string;
  division: string;
  owner: string;
  status: "active" | "hold" | "complete";
  project_count?: number;
}

export interface UnassignedProject {
  id: number;
  name: string;
  manager: string | null;
  task_count: number;
  completed_count: number;
}

export interface UnmappedOwner {
  owner_name: string;
  task_count: number;
  project_count: number;
}
