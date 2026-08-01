import { CaretDownIcon, PinIcon, SearchIcon } from "@/components/ui/icons";

export function SearchBar() {
  return (
    <form
      className="flex items-center rounded-panel bg-card p-1.5 pl-1 shadow-raised"
      role="search"
    >
      <button
        type="button"
        className="flex items-center gap-1.5 px-3 py-2 text-sm font-medium whitespace-nowrap"
      >
        <PinIcon className="h-4 w-4 text-brand" />
        Toàn quốc
        <CaretDownIcon className="h-3.5 w-3.5" />
      </button>

      <span className="h-[22px] w-px bg-line-strong" aria-hidden />

      <input
        type="search"
        name="q"
        aria-label="Từ khoá tìm kiếm"
        placeholder="Nhập khu vực, dự án, từ khoá…"
        className="min-w-0 flex-1 border-0 bg-transparent px-3 py-2.5 text-[15px] outline-none placeholder:text-faint"
      />

      <button
        type="submit"
        aria-label="Tìm kiếm"
        className="grid h-[42px] w-[42px] shrink-0 place-items-center rounded-lg bg-brand text-white"
      >
        <SearchIcon className="h-[19px] w-[19px]" />
      </button>
    </form>
  );
}
