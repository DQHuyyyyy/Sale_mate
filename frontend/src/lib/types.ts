/**
 * Kiểu dữ liệu khớp DTO của backend (src/models/).
 *
 * ⚠️ Đây là nửa FE của HỢP ĐỒNG chung. Backend đổi src/models/ thì phải đổi
 * file này trong cùng một PR, nếu không FE và BE lệch nhau lặng lẽ.
 */

export type ListingType = "sale" | "rent" | "transfer";

export type PropertyKind =
  | "house"
  | "apartment"
  | "land"
  | "villa"
  | "shophouse";

export interface Listing {
  id: string;
  title: string;
  listing_type: ListingType;
  kind: PropertyKind;
  price_label: string;
  unit_price_label: string;
  area_label: string;
  bedrooms_label: string;
  location: string;
  is_verified: boolean;
  photo_count: number;
  image_url: string | null;
}

export interface Project {
  id: string;
  name: string;
  developer: string;
  location: string;
  price_from_label: string;
  image_url: string | null;
}

export interface Demand {
  id: string;
  author_name: string;
  author_initials: string;
  posted_label: string;
  summary: string;
}

export interface MarketBar {
  kind: PropertyKind;
  label: string;
  value: number;
  color: string;
}

export interface MarketStats {
  as_of: string;
  active_listings: number;
  listings_today: number;
  bars: MarketBar[];
}

/* ---------------- Chat ---------------- */

export type ChatEventType =
  | "start"
  | "route"
  | "token"
  | "sources"
  | "sensitive"
  | "done"
  | "error";

export interface Citation {
  doc_id: string;
  title: string;
  version: string;
  page: number | null;
  section: string;
  kind: "doc" | "db" | "live";
}

export interface ChatEvent {
  type: ChatEventType;
  content: string;
  session_id: string;
  citations: Citation[];
  data: Record<string, unknown>;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}
