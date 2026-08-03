import { SectionHeader } from "@/components/home/SectionHeader";
import { PlusIcon } from "@/components/ui/icons";
import type { Demand } from "@/lib/types";

function DemandCard({ demand }: { demand: Demand }) {
  return (
    <article className="w-[184px] shrink-0 rounded-card border border-line bg-card p-3.5 shadow-card">
      <div className="mb-2.5 flex items-center gap-2.5">
        <span
          className="grid h-[34px] w-[34px] shrink-0 place-items-center rounded-full bg-linear-135 from-[#cfe0ff] to-[#9cc0ff] text-[13px] font-bold text-brand"
          aria-hidden
        >
          {demand.author_initials}
        </span>
        <div className="text-[12.5px] leading-tight font-semibold">
          {demand.author_name}
          <span className="block text-[11px] font-normal text-faint">
            {demand.posted_label}
          </span>
        </div>
      </div>
      <p className="text-[12.5px] leading-relaxed text-muted">
        {demand.summary}
      </p>
    </article>
  );
}

export function DemandSection({ demands }: { demands: Demand[] }) {
  return (
    <section className="py-[26px]">
      <SectionHeader title="Nhu cầu" />

      <div className="scrollbar-thin flex gap-3 overflow-x-auto pb-1.5">
        <button
          type="button"
          className="flex w-[184px] shrink-0 flex-col items-start justify-center gap-2 rounded-card bg-brand p-3.5 text-left text-white"
        >
          <span className="grid h-[34px] w-[34px] place-items-center rounded-full bg-white/20">
            <PlusIcon className="h-[18px] w-[18px]" />
          </span>
          <strong className="text-sm font-semibold">Thêm nhu cầu BĐS</strong>
        </button>

        {demands.map((demand) => (
          <DemandCard key={demand.id} demand={demand} />
        ))}
      </div>
    </section>
  );
}
