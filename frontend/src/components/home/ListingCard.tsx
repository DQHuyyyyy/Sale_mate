import {
  AreaIcon,
  BedIcon,
  CheckIcon,
  HeartIcon,
  HouseIcon,
  PhotoIcon,
  PinIcon,
} from "@/components/ui/icons";
import type { Listing } from "@/lib/types";

export function ListingCard({ listing }: { listing: Listing }) {
  return (
    <article className="overflow-hidden rounded-card border border-line bg-card shadow-card transition duration-150 hover:-translate-y-[3px] hover:shadow-raised">
      <div className="relative grid aspect-4/3 place-items-center bg-linear-135 from-[#e7eef7] to-[#d4e0ee]">
        <HouseIcon className="h-11 w-11 text-[#b6c6da]" />

        {listing.is_verified && (
          <span className="absolute top-2.5 left-2.5 flex items-center gap-1 rounded-[5px] bg-verified/95 px-2 py-[3px] text-[10.5px] font-semibold text-white">
            <CheckIcon className="h-[11px] w-[11px]" />
            Xác thực
          </span>
        )}

        <button
          type="button"
          aria-label={`Lưu tin ${listing.title}`}
          className="absolute top-2 right-2 grid h-7 w-7 place-items-center rounded-full bg-white/90 text-muted hover:text-flag"
        >
          <HeartIcon className="h-[15px] w-[15px]" />
        </button>

        {listing.photo_count > 0 && (
          <span className="absolute right-2 bottom-2 flex items-center gap-1 rounded-full bg-ink/60 px-[7px] py-0.5 text-[11px] text-white">
            <PhotoIcon className="h-[11px] w-[11px]" />
            {listing.photo_count}
          </span>
        )}
      </div>

      <div className="px-[13px] py-3">
        <h3 className="clamp-2 mb-2 min-h-[38px] text-sm leading-snug font-semibold">
          {listing.title}
        </h3>

        <p className="text-base font-bold text-price">
          {listing.price_label}
          {listing.unit_price_label && (
            <span className="text-xs font-medium text-muted">
              {" "}
              · {listing.unit_price_label}
            </span>
          )}
        </p>

        <div className="my-2 flex gap-3 text-xs text-muted">
          {listing.area_label && (
            <span className="flex items-center gap-1">
              <AreaIcon className="h-[13px] w-[13px] text-faint" />
              {listing.area_label}
            </span>
          )}
          {listing.bedrooms_label && (
            <span className="flex items-center gap-1">
              <BedIcon className="h-[13px] w-[13px] text-faint" />
              {listing.bedrooms_label}
            </span>
          )}
        </div>

        <p className="flex items-center gap-1.5 border-t border-line-strong pt-2.5 text-xs text-faint">
          <PinIcon className="h-[13px] w-[13px]" />
          {listing.location}
        </p>
      </div>
    </article>
  );
}
