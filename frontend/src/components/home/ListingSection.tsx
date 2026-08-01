"use client";

import { useMemo, useState } from "react";

import { ListingCard } from "@/components/home/ListingCard";
import { SectionHeader } from "@/components/home/SectionHeader";
import type { Listing, ListingType } from "@/lib/types";

const TABS: { value: ListingType; label: string }[] = [
  { value: "sale", label: "Mua bán" },
  { value: "rent", label: "Cho thuê" },
  { value: "transfer", label: "Sang nhượng" },
];

export function ListingSection({ listings }: { listings: Listing[] }) {
  const [active, setActive] = useState<ListingType>("sale");

  // Lọc phía client vì dữ liệu cả 3 tab đã tải sẵn — đổi tab không phải chờ mạng.
  const visible = useMemo(
    () => listings.filter((listing) => listing.listing_type === active),
    [listings, active],
  );

  return (
    <section className="py-[26px]">
      <SectionHeader title="Bất động sản nổi bật" />

      <div className="mb-4 flex gap-1.5" role="tablist" aria-label="Loại giao dịch">
        {TABS.map((tab) => (
          <button
            key={tab.value}
            type="button"
            role="tab"
            aria-selected={active === tab.value}
            onClick={() => setActive(tab.value)}
            className={`rounded-full border px-4 py-[7px] text-[13.5px] font-semibold transition ${
              active === tab.value
                ? "border-brand bg-brand text-white"
                : "border-line bg-card text-muted hover:text-ink"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {visible.length === 0 ? (
        <p className="rounded-card border border-line bg-card p-6 text-center text-sm text-muted">
          Chưa có tin đăng nào ở mục này. Bạn thử chọn tab khác nhé.
        </p>
      ) : (
        <div className="grid grid-cols-1 gap-4 narrow:grid-cols-2 wide:grid-cols-4">
          {visible.map((listing) => (
            <ListingCard key={listing.id} listing={listing} />
          ))}
        </div>
      )}
    </section>
  );
}
