import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  images: {
    // Ảnh căn hộ đang nằm trên Google Drive (link công khai). next/image chặn
    // mọi host lạ nên phải khai báo ở đây, nếu không ảnh sẽ không hiện.
    //
    // Khi chuyển ảnh sang Supabase Storage, chỉ cần bỏ hai mục Drive đi —
    // dữ liệu trong DB đã là URL nên component không phải sửa.
    remotePatterns: [
      { protocol: "https", hostname: "drive.google.com" },
      { protocol: "https", hostname: "lh3.googleusercontent.com" },
      { protocol: "https", hostname: "*.supabase.co" },
    ],
  },
};

export default nextConfig;
