import { MapIcon, ShieldCheckIcon, TrendIcon } from "@/components/ui/icons";

/**
 * Ba tín hiệu tin cậy đặt ngay hero — đây là lời hứa chính của sản phẩm:
 * thông tin đã được xác thực.
 */
const ITEMS = [
  { Icon: ShieldCheckIcon, title: "Xác thực pháp lý", note: "sổ đỏ, giấy tờ" },
  { Icon: MapIcon, title: "Xác thực quy hoạch", note: "bản đồ đất" },
  { Icon: TrendIcon, title: "Xác thực giá", note: "định giá AI" },
];

export function VerifyBanner() {
  return (
    <ul className="mt-4 flex flex-col gap-2.5 narrow:flex-row">
      {ITEMS.map(({ Icon, title, note }) => (
        <li
          key={title}
          className="flex flex-1 items-center gap-2.5 rounded-lg border border-white/20 bg-white/15 px-3 py-[11px] text-white"
        >
          <Icon className="h-5 w-5 shrink-0 text-[#bcd7ff]" />
          <div>
            <strong className="block text-[13px] leading-tight font-semibold">
              {title}
            </strong>
            <span className="text-[11px] opacity-80">{note}</span>
          </div>
        </li>
      ))}
    </ul>
  );
}
