import { MarketPanel } from "@/components/home/MarketPanel";
import { SearchBar } from "@/components/home/SearchBar";
import { VerifyBanner } from "@/components/home/VerifyBanner";
import type { MarketStats } from "@/lib/types";

export function Hero({ stats }: { stats: MarketStats | null }) {
  return (
    <div className="bg-linear-160 from-brand to-brand-dark pt-[34px] pb-10">
      <div className="mx-auto grid max-w-[1140px] grid-cols-1 gap-[26px] px-5 wide:grid-cols-[1fr_420px]">
        <div>
          <h1 className="mb-4.5 text-[21px] font-semibold tracking-tight text-white narrow:text-[26px]">
            Nền tảng bất động sản xác thực
          </h1>
          <SearchBar />
          <VerifyBanner />
        </div>

        <MarketPanel stats={stats} />
      </div>
    </div>
  );
}
