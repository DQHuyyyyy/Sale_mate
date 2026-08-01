import { AIWidget } from "@/components/ai/AIWidget";
import { DemandSection } from "@/components/home/DemandSection";
import { Hero } from "@/components/home/Hero";
import { ListingSection } from "@/components/home/ListingSection";
import { ProjectSection } from "@/components/home/ProjectSection";
import { Footer } from "@/components/layout/Footer";
import { Header } from "@/components/layout/Header";
import {
  fetchDemands,
  fetchListings,
  fetchMarketStats,
  fetchProjects,
} from "@/lib/api";

// Dữ liệu portal thay đổi liên tục nên trang render theo từng request, không
// prerender lúc build (lúc build backend còn chưa chạy).
export const dynamic = "force-dynamic";

export default async function HomePage() {
  // Gọi song song để không cộng dồn độ trễ của bốn request.
  const [listings, projects, demands, market] = await Promise.all([
    fetchListings(),
    fetchProjects(),
    fetchDemands(),
    fetchMarketStats(),
  ]);

  const backendDown = market === null && listings.length === 0;

  return (
    <>
      <Header />

      <main className="flex-1">
        {backendDown && (
          <p className="bg-gold/15 px-5 py-2.5 text-center text-[13px]">
            Chưa kết nối được backend. Chạy{" "}
            <code className="font-mono">make run</code> ở thư mục gốc rồi tải lại
            trang.
          </p>
        )}

        <Hero stats={market} />

        <div className="mx-auto max-w-[1140px] px-5">
          <DemandSection demands={demands} />
          <ListingSection listings={listings} />
          <ProjectSection projects={projects} />
        </div>
      </main>

      <Footer />
      <AIWidget />
    </>
  );
}
