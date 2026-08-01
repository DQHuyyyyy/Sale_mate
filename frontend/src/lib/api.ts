/**
 * Gọi API backend.
 *
 * Backend chưa chạy thì trang vẫn render được với danh sách rỗng thay vì đổ
 * lỗi — người dùng thấy trạng thái trống có ý nghĩa, không thấy màn hình vỡ.
 */

import type { Demand, Listing, MarketStats, Project } from "@/lib/types";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function getJson<T>(path: string, fallback: T): Promise<T> {
  try {
    const response = await fetch(`${API_BASE}/api/v1${path}`, {
      cache: "no-store",
    });
    if (!response.ok) {
      console.error(`API ${path} trả về ${response.status}`);
      return fallback;
    }
    return (await response.json()) as T;
  } catch (error) {
    console.error(`Không gọi được API ${path}:`, error);
    return fallback;
  }
}

export function fetchListings(listingType?: string): Promise<Listing[]> {
  const query = listingType ? `?listing_type=${listingType}` : "";
  return getJson<Listing[]>(`/listings${query}`, []);
}

export function fetchProjects(): Promise<Project[]> {
  return getJson<Project[]>("/projects", []);
}

export function fetchDemands(): Promise<Demand[]> {
  return getJson<Demand[]>("/demands", []);
}

export function fetchMarketStats(): Promise<MarketStats | null> {
  return getJson<MarketStats | null>("/market", null);
}
