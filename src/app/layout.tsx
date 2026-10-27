import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "경복궁 · 3D 아카이브",
  description:
    "블렌더로 절차적으로 생성한 경복궁 11개 전각을 3D로 살펴보고, 부재 하나하나로 분해해 보세요.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
  themeColor: "#07090c",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="ko" className="h-full">
      <body className="h-full overflow-hidden bg-[#07090c]">{children}</body>
    </html>
  );
}
