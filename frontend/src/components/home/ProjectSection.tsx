import { SectionHeader } from "@/components/home/SectionHeader";
import { BuildingIcon } from "@/components/ui/icons";
import type { Project } from "@/lib/types";

function ProjectCard({ project }: { project: Project }) {
  return (
    <article className="overflow-hidden rounded-card border border-line bg-card shadow-card">
      <div className="grid aspect-video place-items-center bg-linear-135 from-[#dbe7f5] to-[#c3d5ec]">
        <BuildingIcon className="h-10 w-10 text-[#a9bdd6]" />
      </div>
      <div className="px-3.5 py-3">
        <h3 className="mb-1 text-[15px] font-semibold">{project.name}</h3>
        <p className="mb-2 text-xs text-faint">
          {project.developer} · {project.location}
        </p>
        <p className="text-[13px] text-muted">
          Từ <strong className="font-bold text-price">{project.price_from_label}</strong>
          /căn
        </p>
      </div>
    </article>
  );
}

export function ProjectSection({ projects }: { projects: Project[] }) {
  return (
    <section className="py-[26px]">
      <SectionHeader title="Dự án nổi bật" />

      {projects.length === 0 ? (
        <p className="rounded-card border border-line bg-card p-6 text-center text-sm text-muted">
          Chưa có dự án nào để hiển thị.
        </p>
      ) : (
        <div className="grid grid-cols-1 gap-4 narrow:grid-cols-2 wide:grid-cols-3">
          {projects.map((project) => (
            <ProjectCard key={project.id} project={project} />
          ))}
        </div>
      )}
    </section>
  );
}
