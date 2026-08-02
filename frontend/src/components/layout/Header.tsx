"use client";

import { useState } from "react";

import {
  BellIcon,
  CloseIcon,
  HeartIcon,
  LogoMark,
  MenuIcon,
  PlusIcon,
} from "@/components/ui/icons";

const NAV_ITEMS = [
  { label: "Mua bán nhà đất", href: "#" },
  { label: "Cho thuê", href: "#" },
  { label: "Sang nhượng", href: "#" },
  { label: "Dự án", href: "#" },
  { label: "Tin tức", href: "#" },
  { label: "Bảng giá", href: "#" },
  { label: "Khám phá", href: "#", isNew: true },
];

export function Header() {
  const [navOpen, setNavOpen] = useState(false);

  return (
    <>
      <header className="sticky top-0 z-40 bg-brand">
        <div className="mx-auto flex h-16 max-w-[1140px] items-center gap-3 px-5 wide:gap-[26px]">
          <button
            type="button"
            className="p-0.5 text-white wide:hidden"
            aria-label="Mở menu"
            aria-expanded={navOpen}
            onClick={() => setNavOpen(true)}
          >
            <MenuIcon className="h-6 w-6" />
          </button>

          <a
            href="#"
            className="flex shrink-0 items-center gap-2 text-xl font-bold text-white"
          >
            <LogoMark className="h-[30px] w-[30px]" />
            SalesMate
          </a>

          <nav
            id="main-nav"
            className={`fixed inset-y-0 left-0 z-50 w-[250px] flex-col gap-5 bg-brand-dark px-[18px] pt-[70px] pb-[18px] transition-transform duration-200 wide:static wide:z-auto wide:w-auto wide:flex-1 wide:flex-row wide:gap-5 wide:bg-transparent wide:p-0 wide:transition-none ${
              navOpen ? "flex translate-x-0" : "flex -translate-x-full wide:translate-x-0"
            }`}
            aria-label="Điều hướng chính"
          >
            <button
              type="button"
              className="absolute top-4 right-4 p-1 text-white wide:hidden"
              aria-label="Đóng menu"
              onClick={() => setNavOpen(false)}
            >
              <CloseIcon className="h-6 w-6" />
            </button>

            {NAV_ITEMS.map((item) => (
              <a
                key={item.label}
                href={item.href}
                className="flex items-center gap-1.5 text-sm font-medium whitespace-nowrap text-white/95 hover:text-white"
                onClick={() => setNavOpen(false)}
              >
                {item.label}
                {item.isNew && (
                  <span className="rounded-full bg-flag px-[5px] py-px text-[9px] font-bold tracking-wide text-white">
                    NEW
                  </span>
                )}
              </a>
            ))}
          </nav>

          <div className="ml-auto flex items-center gap-3.5">
            <button
              type="button"
              className="hidden text-white/90 hover:text-white wide:grid"
              aria-label="Tin đã lưu"
            >
              <HeartIcon className="h-[21px] w-[21px]" />
            </button>
            <button
              type="button"
              className="hidden text-white/90 hover:text-white wide:grid"
              aria-label="Thông báo"
            >
              <BellIcon className="h-[21px] w-[21px]" />
            </button>
            <span className="hidden text-sm font-medium whitespace-nowrap text-white wide:inline">
              Đăng nhập / Đăng ký
            </span>
            <button
              type="button"
              className="flex items-center gap-1.5 rounded-btn bg-white px-[15px] py-[9px] text-sm font-semibold whitespace-nowrap text-brand"
            >
              <PlusIcon className="h-4 w-4" />
              <span className="hidden narrow:inline">Đăng tin</span>
            </button>
          </div>
        </div>
      </header>

      {navOpen && (
        <div
          className="fixed inset-0 z-40 bg-ink/40 wide:hidden"
          onClick={() => setNavOpen(false)}
          aria-hidden
        />
      )}
    </>
  );
}
