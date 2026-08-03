import { BarsIcon, TrendIcon } from "@/components/ui/icons";
import type { MarketStats } from "@/lib/types";

const numberFormat = new Intl.NumberFormat("vi-VN");

function formatDate(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleDateString("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

export function MarketPanel({ stats }: { stats: MarketStats | null }) {
  if (!stats) {
    return (
      <section className="rounded-2xl border border-white/20 bg-white/10 p-4 text-sm text-white/85">
        Chưa lấy được số liệu thị trường. Thử tải lại trang sau ít phút nhé.
      </section>
    );
  }

  const maxValue = Math.max(...stats.bars.map((bar) => bar.value), 1);

  return (
    <section
      className="rounded-2xl border border-white/20 bg-white/10 px-[18px] py-4 text-white"
      aria-label="Thống kê thị trường"
    >
      <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold">
        <TrendIcon className="h-[18px] w-[18px] text-[#bcd7ff]" />
        Thị trường hôm nay
        <span className="ml-auto font-medium text-[#bcd7ff]">
          {formatDate(stats.as_of)}
        </span>
      </h2>

      <p className="mb-1.5 text-[13px] text-[#dbe8ff]">
        Tin đang hiệu lực:{" "}
        <strong className="font-mono text-white">
          {numberFormat.format(stats.active_listings)}
        </strong>
      </p>
      <p className="text-[13px] text-[#dbe8ff]">
        Tin đăng hôm nay:{" "}
        <strong className="font-mono text-white">
          {numberFormat.format(stats.listings_today)}
        </strong>
      </p>

      <hr className="my-3 border-white/20" />

      <h3 className="mb-3.5 flex items-center gap-[7px] text-[13px] font-semibold">
        <BarsIcon className="h-[15px] w-[15px] text-[#bcd7ff]" />
        Thống kê tin đăng trong ngày
      </h3>

      <div className="flex h-[140px] items-end gap-3.5 px-1">
        {stats.bars.map((bar) => (
          <div
            key={bar.kind}
            className="flex h-full flex-1 flex-col items-center justify-end gap-1.5"
          >
            <span className="font-mono text-xs font-semibold">
              {numberFormat.format(bar.value)}
            </span>
            <div
              className="w-full rounded-t"
              style={{
                height: `${Math.max((bar.value / maxValue) * 100, 5)}%`,
                background: bar.color,
              }}
              role="img"
              aria-label={`${bar.label}: ${bar.value} tin`}
            />
          </div>
        ))}
      </div>

      <ul className="mt-3 flex flex-wrap gap-x-4 gap-y-2.5">
        {stats.bars.map((bar) => (
          <li
            key={bar.kind}
            className="flex items-center gap-1.5 text-[11px] text-[#dbe8ff]"
          >
            <span
              className="inline-block h-[9px] w-[9px] rounded-sm"
              style={{ background: bar.color }}
              aria-hidden
            />
            {bar.label}
          </li>
        ))}
      </ul>
    </section>
  );
}
