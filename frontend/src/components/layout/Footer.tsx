import { LogoMark } from "@/components/ui/icons";

const COLUMNS = [
  {
    title: "Bán căn hộ chung cư",
    links: [
      "Căn hộ Hà Nội",
      "Căn hộ Hồ Chí Minh",
      "Căn hộ Hải Phòng",
      "Căn hộ Đà Nẵng",
    ],
  },
  {
    title: "Cho thuê",
    links: [
      "Cho thuê căn hộ",
      "Cho thuê văn phòng",
      "Cho thuê mặt bằng",
      "Cho thuê nhà riêng",
    ],
  },
  {
    title: "Dự án nổi bật",
    links: [
      "Lakeside Metropole",
      "The Origin Riverside",
      "Sunrise Garden City",
      "Xem tất cả dự án",
    ],
  },
  {
    title: "Hỗ trợ",
    links: ["Quy định đăng tin", "Liên hệ", "Chính sách bảo mật", "Trợ giúp"],
  },
];

export function Footer() {
  return (
    <footer className="mt-5 border-t border-line bg-card pt-[30px] pb-6">
      <div className="mx-auto max-w-[1140px] px-5">
        <div className="grid grid-cols-1 gap-6 border-b border-line-strong pb-6 narrow:grid-cols-2 wide:grid-cols-4">
          {COLUMNS.map((column) => (
            <div key={column.title}>
              <h2 className="mb-3 text-[13px] font-bold">{column.title}</h2>
              {column.links.map((link) => (
                <a
                  key={link}
                  href="#"
                  className="mb-2 block text-[13px] text-muted hover:text-brand"
                >
                  {link}
                </a>
              ))}
            </div>
          ))}
        </div>

        <div className="flex flex-wrap items-start gap-5 pt-5 text-[12.5px] text-muted">
          <div className="min-w-[220px] flex-1">
            <div className="mb-2 flex items-center gap-2 text-base font-bold text-brand">
              <LogoMark className="h-6 w-6" />
              SalesMate
            </div>
            Nền tảng bất động sản xác thực — kết nối người mua, người bán và môi
            giới.
          </div>
          <div>
            <strong className="font-semibold text-ink">Chứng nhận</strong>
            <div className="mt-2 flex gap-2">
              {["ISO 27001", "ISO 9001"].map((cert) => (
                <span
                  key={cert}
                  className="grid h-9 w-[52px] place-items-center rounded-md border border-line text-center text-[9px] font-semibold text-faint"
                >
                  {cert}
                </span>
              ))}
            </div>
          </div>
        </div>
      </div>
    </footer>
  );
}
