import { ChevronRightIcon } from "@/components/ui/icons";

export function SectionHeader({ title }: { title: string }) {
  return (
    <div className="mb-4 flex items-center">
      <h2 className="text-[19px] font-semibold">{title}</h2>
      <a
        href="#"
        className="ml-auto flex items-center gap-1 text-[13px] font-semibold text-brand"
      >
        Xem tất cả
        <ChevronRightIcon className="h-[15px] w-[15px]" />
      </a>
    </div>
  );
}
