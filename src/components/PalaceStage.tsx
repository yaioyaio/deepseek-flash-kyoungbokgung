"use client";

import dynamic from "next/dynamic";

const PalaceExperience = dynamic(() => import("./PalaceExperience"), {
  ssr: false,
  loading: () => (
    <div className="flex h-dvh w-full items-center justify-center bg-[#06080b]">
      <div className="flex flex-col items-center">
        <div className="flex h-16 w-16 items-center justify-center border border-[#d9b779]/35">
          <span className="font-serif text-[26px] text-[#e2c48c]">景</span>
        </div>
        <p className="mt-7 font-serif text-[26px] tracking-[0.5em] text-[#f2e8d6]">
          경복궁
        </p>
        <p className="mt-2.5 text-[9px] tracking-[0.5em] text-[#8e8069]">
          景福宮 · GYEONGBOKGUNG
        </p>
      </div>
    </div>
  ),
});

export default function PalaceStage() {
  return <PalaceExperience />;
}
