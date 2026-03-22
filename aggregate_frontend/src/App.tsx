import { useEffect, useState } from "react";
import type { Programme, UnassignedProject, UnmappedOwner } from "./types";

async function loadJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export default function App() {
  const [programmes, setProgrammes] = useState<Programme[]>([]);
  const [unassignedProjects, setUnassignedProjects] = useState<UnassignedProject[]>([]);
  const [unmappedOwners, setUnmappedOwners] = useState<UnmappedOwner[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      loadJson<Programme[]>("/api/v1/programmes"),
      loadJson<UnassignedProject[]>("/api/v1/admin/unassigned-projects"),
      loadJson<UnmappedOwner[]>("/api/v1/admin/unmapped-owners"),
    ])
      .then(([loadedProgrammes, loadedProjects, loadedOwners]) => {
        setProgrammes(loadedProgrammes);
        setUnassignedProjects(loadedProjects);
        setUnmappedOwners(loadedOwners);
      })
      .catch((err: Error) => {
        setError(err.message);
      });
  }, []);

  return (
    <main style={{ fontFamily: "Segoe UI, Arial, sans-serif", padding: 24, color: "#1f2937" }}>
      <h1>Programme Portfolio Aggregation Dashboard</h1>
      <p style={{ color: "#6b7280", maxWidth: 900 }}>
        This is the React scaffold for the aggregate dashboard. It is not yet wired into the Flask
        build pipeline because Node/npm are not installed in this environment, but the source tree is
        ready for the next implementation step.
      </p>

      {error ? (
        <p style={{ color: "#b91c1c" }}>Failed to load API data: {error}</p>
      ) : null}

      <section>
        <h2>Programmes</h2>
        <p>{programmes.length} configured</p>
      </section>

      <section>
        <h2>Unassigned projects</h2>
        <ul>
          {unassignedProjects.map((project) => (
            <li key={project.name}>
              {project.name} ({project.task_count} tasks)
            </li>
          ))}
        </ul>
      </section>

      <section>
        <h2>Unmapped owners</h2>
        <ul>
          {unmappedOwners.map((owner) => (
            <li key={owner.owner_name}>
              {owner.owner_name} ({owner.task_count} tasks)
            </li>
          ))}
        </ul>
      </section>
    </main>
  );
}
