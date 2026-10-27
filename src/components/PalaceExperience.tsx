"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { AnimatePresence, motion } from "motion/react";
import {
  Boxes,
  ChevronLeft,
  ChevronRight,
  Eye,
  EyeOff,
  Layers,
  Menu,
  Moon,
  MousePointer2,
  RotateCcw,
  Sparkles,
  Sun,
  Sunset,
  X,
} from "lucide-react";
import { PalaceViewer } from "@/lib/palace/viewer";
import {
  BUILDINGS,
  BUILDING_BY_ID,
  CAMERA_PRESETS,
  KIND_LABEL,
  LAYERS,
  TIME_PRESETS,
} from "@/lib/palace/data";
import type { LabelPosition, LayerGroup, LayerInfo, TimeKey } from "@/lib/palace/types";

const cx = (...parts: (string | false | null | undefined)[]) =>
  parts.filter(Boolean).join(" ");

const TIME_ICON = { day: Sun, sunset: Sunset, night: Moon } as const;

/** the member list is split into storeys so 30 chips stay readable */
const LAYER_GROUP_LABEL: Record<LayerGroup, string> = {
  lower: "하층 부재",
  upper: "상층 부재",
  cap: "상부 마루",
};

const LAYER_GROUP_HINT: Record<LayerGroup, string> = {
  lower: "기단에서 하층 지붕까지",
  upper: "하층 지붕 위 · 상층 지붕까지",
  cap: "가장 높은 지붕의 용마루",
};

const GROUP_ORDER: LayerGroup[] = ["lower", "upper", "cap"];

/** 1 → "01" so the chip numbers line up */
const partNo = (n: number) => String(n).padStart(2, "0");

function groupLayers(layers: LayerInfo[]) {
  return GROUP_ORDER.map((group) => ({
    group,
    items: layers.filter((layer) => layer.group === group),
  })).filter((entry) => entry.items.length > 0);
}

/** the side panel covers the whole viewport below the md breakpoint */
const isNarrowViewport = () =>
  typeof window !== "undefined" &&
  window.matchMedia("(max-width: 767px)").matches;

export default function PalaceExperience() {
  const stageRef = useRef<HTMLDivElement | null>(null);
  const viewerRef = useRef<PalaceViewer | null>(null);

  const [progress, setProgress] = useState(0);
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [labels, setLabels] = useState<LabelPosition[]>([]);

  const [explode, setExplode] = useState(0);
  const [isolated, setIsolated] = useState<number | null>(null);
  const [missingLayer, setMissingLayer] = useState<string | null>(null);
  const [timeKey, setTimeKey] = useState<TimeKey>("day");
  const [showLabels, setShowLabels] = useState(true);
  const [preset, setPreset] = useState<string | null>("overview");
  const [panelOpen, setPanelOpen] = useState(false);
  const [hintVisible, setHintVisible] = useState(false);

  useEffect(() => {
    const stage = stageRef.current;
    if (!stage) return;

    const canvas = document.createElement("canvas");
    canvas.className = "block h-full w-full touch-none outline-none";
    stage.appendChild(canvas);

    const viewer = new PalaceViewer(canvas, {
      onProgress: (ratio) => setProgress(ratio),
      onReady: () => setReady(true),
      onError: () => setFailed(true),
      onHover: (id) => setHoveredId(id),
      onLabels: (next) => setLabels(next),
      onSelect: (id) => {
        setSelectedId(id);
        setPreset(null);
        setPanelOpen(false);
        setIsolated(null);
        setMissingLayer(null);
        if (id) viewer.select(id, true);
        else viewer.select(null);
      },
    });
    viewerRef.current = viewer;
    viewer.load();

    return () => {
      viewer.dispose();
      viewerRef.current = null;
      canvas.remove();
    };
  }, []);

  useEffect(() => {
    if (!ready) return;
    const timer = window.setTimeout(() => setHintVisible(true), 1200);
    const hide = window.setTimeout(() => setHintVisible(false), 9000);
    return () => {
      window.clearTimeout(timer);
      window.clearTimeout(hide);
    };
  }, [ready]);

  const selectBuilding = useCallback((id: string | null) => {
    setSelectedId(id);
    setPreset(null);
    setPanelOpen(id !== null);
    setIsolated(null);
    setMissingLayer(null);
    viewerRef.current?.setIsolatedLayer(null);
    if (!id) {
      viewerRef.current?.select(null, true);
      return;
    }
    viewerRef.current?.select(id, true);
  }, []);

  const applyExplode = useCallback((value: number) => {
    setExplode(value);
    viewerRef.current?.setExplode(value);
    // on phones the panel covers the canvas, so slide it away to show the result
    if (isNarrowViewport()) setPanelOpen(false);
  }, []);

  const toggleLayer = useCallback(
    (index: number | null) => {
      const next = isolated === index ? null : index;
      const applied = viewerRef.current?.setIsolatedLayer(next) ?? true;
      // an open pavilion simply has no walls: say so instead of doing nothing
      if (!applied) {
        setMissingLayer(next === null ? null : (LAYERS[next]?.ko ?? "이 부재"));
        return;
      }
      setMissingLayer(null);
      setIsolated(next);
      if (next !== null && explode < 0.45) {
        setExplode(0.55);
        viewerRef.current?.setExplode(0.55);
      }
      if (next !== null && isNarrowViewport()) setPanelOpen(false);
    },
    [isolated, explode],
  );

  const clearLayers = useCallback(() => {
    setMissingLayer(null);
    setIsolated(null);
    viewerRef.current?.setIsolatedLayer(null);
  }, []);

  const changeTime = useCallback((key: TimeKey) => {
    setTimeKey(key);
    viewerRef.current?.setTime(key);
  }, []);

  const toggleLabels = useCallback(() => {
    setShowLabels((prev) => {
      viewerRef.current?.setShowLabels(!prev);
      return !prev;
    });
  }, []);

  const applyPreset = useCallback((id: string) => {
    const next = CAMERA_PRESETS.find((p) => p.id === id);
    if (!next) return;
    setPreset(id);
    setSelectedId(null);
    viewerRef.current?.select(null);
    viewerRef.current?.applyCamera(next);
  }, []);

  const resetView = useCallback(() => {
    applyPreset("overview");
  }, [applyPreset]);

  const selected = selectedId ? BUILDING_BY_ID.get(selectedId) : undefined;
  const isolatedInfo = isolated !== null ? LAYERS[isolated] : null;
  // single-storey halls have no upper storey, so their chips stay hidden
  const visibleLayers = useMemo(
    () =>
      selected?.tiers === 2
        ? LAYERS
        : LAYERS.filter((layer) => layer.group !== "upper"),
    [selected],
  );
  const layerGroups = useMemo(() => groupLayers(visibleLayers), [visibleLayers]);
  // single-storey halls skip 16–28, so the chips are numbered by their place in
  // the visible list instead of by the (sparse) layer index
  const displayNo = useMemo(
    () => new Map(visibleLayers.map((layer, i) => [layer.index, i + 1])),
    [visibleLayers],
  );

  return (
    <div className="relative h-dvh w-full overflow-hidden bg-[#07090c] text-[#e9e2d4]">
      <div ref={stageRef} className="absolute inset-0" />

      {/* atmosphere */}
      <div className="pointer-events-none absolute inset-0 z-10 bg-[radial-gradient(120%_90%_at_50%_10%,transparent_48%,rgba(4,6,9,0.42)_100%)]" />
      <div className="pointer-events-none absolute inset-x-0 top-0 z-10 h-32 bg-gradient-to-b from-[#05070a]/55 to-transparent" />
      <div className="pointer-events-none absolute inset-x-0 bottom-0 z-10 h-44 bg-gradient-to-t from-[#05070a]/80 to-transparent" />

      {/* labels */}
      {ready && showLabels && (
        <div className="pointer-events-none absolute inset-0 z-20 overflow-hidden">
          {labels.map((label) => {
            const building = BUILDING_BY_ID.get(label.id);
            if (!building) return null;
            const active = selectedId === label.id;
            const hovered = hoveredId === label.id;
            return (
              <button
                key={label.id}
                type="button"
                onClick={() => selectBuilding(label.id)}
                className={cx(
                  "group pointer-events-auto absolute flex -translate-x-1/2 -translate-y-full items-center gap-1.5 whitespace-nowrap rounded-full border px-2 py-0.5 text-[10px] tracking-wide backdrop-blur-md transition-colors duration-200",
                  active
                    ? "border-[#e0bd7c]/80 bg-[#1a1408]/90 text-[#f6e6c4]"
                    : hovered
                      ? "border-[#d9b779]/50 bg-[#0b0e12]/85 text-[#f0e6d2]"
                      : "border-white/[0.08] bg-[#080b0f]/55 text-[#cfc8b8]/85",
                )}
                style={{
                  left: label.x,
                  top: label.y,
                  zIndex: Math.round(40 - label.depth * 10),
                }}
              >
                <span
                  className={cx(
                    "h-1 w-1 rounded-full",
                    active ? "bg-[#e9c77c]" : "bg-[#d9b779]/70",
                  )}
                />
                <span className="font-serif">{building.ko}</span>
              </button>
            );
          })}
        </div>
      )}

      {/* header */}
      <header className="pointer-events-none absolute inset-x-0 top-0 z-30 flex items-start justify-between gap-3 p-4 md:p-6">
        <div className="pointer-events-auto flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center border border-[#d9b779]/40">
            <span className="font-serif text-[17px] text-[#e6c88a]">景</span>
          </div>
          <div>
            <h1 className="font-serif text-[19px] leading-none tracking-[0.24em] text-[#f4ecdc]">
              경복궁
            </h1>
            <p className="mt-1.5 text-[9px] tracking-[0.34em] text-[#b8a582]/70">
              GYEONGBOKGUNG · 3D
            </p>
          </div>
        </div>

        <div className="pointer-events-auto flex items-center gap-2">
          <div className="flex items-center gap-0.5 rounded-full border border-white/10 bg-[#0a0d11]/70 p-1 backdrop-blur-xl">
            {TIME_PRESETS.map((presetItem) => {
              const Icon = TIME_ICON[presetItem.key];
              const active = timeKey === presetItem.key;
              return (
                <button
                  key={presetItem.key}
                  type="button"
                  onClick={() => changeTime(presetItem.key)}
                  aria-pressed={active}
                  className={cx(
                    "flex items-center gap-1.5 rounded-full px-2.5 py-1.5 text-[11px] transition-colors",
                    active
                      ? "bg-[#d9b779]/15 text-[#f0d9a7]"
                      : "text-[#a9a49a] hover:text-[#e8dfcd]",
                  )}
                >
                  <Icon size={14} strokeWidth={1.7} />
                  <span className="hidden sm:inline">{presetItem.ko}</span>
                </button>
              );
            })}
          </div>

          <button
            type="button"
            onClick={toggleLabels}
            aria-pressed={showLabels}
            aria-label="이름표 표시"
            className={cx(
              "flex h-9 w-9 items-center justify-center rounded-full border backdrop-blur-xl transition-colors",
              showLabels
                ? "border-[#d9b779]/40 bg-[#d9b779]/10 text-[#e9c77c]"
                : "border-white/10 bg-[#0a0d11]/70 text-[#8d887e] hover:text-[#ddd4c2]",
            )}
          >
            {showLabels ? <Eye size={15} strokeWidth={1.7} /> : <EyeOff size={15} strokeWidth={1.7} />}
          </button>

          <button
            type="button"
            onClick={() => setPanelOpen((v) => !v)}
            aria-label="전각 목록"
            className="flex h-9 w-9 items-center justify-center rounded-full border border-white/10 bg-[#0a0d11]/70 text-[#d8cfbd] backdrop-blur-xl md:hidden"
          >
            <Menu size={16} strokeWidth={1.7} />
          </button>
        </div>
      </header>

      {/* left panel */}
      <aside
        className={cx(
          "pointer-events-auto absolute z-40 flex flex-col overflow-hidden rounded-2xl border border-white/[0.08] bg-[#0a0d11]/82 shadow-[0_30px_80px_rgba(0,0,0,0.55)] backdrop-blur-2xl",
          "inset-x-3 top-[4.75rem] bottom-32 md:inset-x-auto md:left-6 md:top-24 md:bottom-28 md:w-[336px]",
          panelOpen ? "flex" : "hidden md:flex",
        )}
      >
        <div className="flex items-center justify-between border-b border-white/[0.07] px-5 py-4">
          <div>
            <p className="text-[9px] tracking-[0.34em] text-[#c9b48c]/65">
              PALACE HALLS
            </p>
            <h2 className="mt-1 font-serif text-[17px] text-[#f1e8d6]">
              {selected ? "전각 상세" : "전각 十一"}
            </h2>
          </div>
          <button
            type="button"
            onClick={() => setPanelOpen(false)}
            aria-label="닫기"
            className="flex h-8 w-8 items-center justify-center rounded-full text-[#8d887e] transition-colors hover:bg-white/5 hover:text-[#e8dfcd] md:hidden"
          >
            <X size={16} strokeWidth={1.7} />
          </button>
        </div>

        <AnimatePresence mode="wait" initial={false}>
          {selected ? (
            <motion.div
              key={`detail-${selected.id}`}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }}
              transition={{ duration: 0.22, ease: "easeOut" }}
              className="panel-scroll min-h-0 flex-1 overflow-y-auto"
            >
              <div className="px-5 pb-4 pt-3">
                <button
                  type="button"
                  onClick={() => selectBuilding(null)}
                  className="flex items-center gap-1 text-[11px] text-[#a29c90] transition-colors hover:text-[#e8dfcd]"
                >
                  <ChevronLeft size={13} strokeWidth={1.8} />
                  전체 목록
                </button>

                <div className="mt-4 flex items-start justify-between gap-3">
                  <div>
                    <p className="text-[9px] tracking-[0.26em] text-[#c9b48c]/75">
                      {KIND_LABEL[selected.kind]} ·{" "}
                      {selected.tiers === 2 ? "중층" : "단층"} · {selected.year}
                    </p>
                    <h3 className="mt-2 font-serif text-[30px] leading-none text-[#f7eeda]">
                      {selected.ko}
                    </h3>
                    <p className="mt-2 font-serif text-[12px] tracking-[0.4em] text-[#b7a684]">
                      {selected.hanja}
                    </p>
                  </div>
                  <span className="select-none font-serif text-[44px] leading-none text-[#d9b779]/15">
                    {selected.hanja.slice(0, 1)}
                  </span>
                </div>

                <p className="mt-4 text-[12.5px] leading-[1.8] text-[#c2bcb0]">
                  {selected.description}
                </p>

                <dl className="mt-4 grid grid-cols-3 divide-x divide-white/[0.06] border-y border-white/[0.07] py-2.5">
                  {[
                    ["높이", `${selected.height.toFixed(1)} m`],
                    ["너비", `${selected.width.toFixed(1)} m`],
                    ["깊이", `${selected.depth.toFixed(1)} m`],
                  ].map(([label, value]) => (
                    <div key={label} className="px-3 first:pl-0 last:pr-0">
                      <dt className="text-[9px] tracking-[0.18em] text-[#8c877d]">
                        {label}
                      </dt>
                      <dd className="mt-1 font-mono text-[12px] text-[#e6dcc8]">
                        {value}
                      </dd>
                    </div>
                  ))}
                </dl>

                <div className="mt-4">
                  <div className="flex items-center justify-between">
                    <p className="text-[9px] tracking-[0.3em] text-[#c9b48c]/70">
                      {visibleLayers.length} PARTS · 부재
                    </p>
                    <button
                      type="button"
                      onClick={clearLayers}
                      className={cx(
                        "text-[10px] transition-colors",
                        isolated === null
                          ? "text-[#6f6a61]"
                          : "text-[#c9a86f] hover:text-[#f0dcb4]",
                      )}
                    >
                      전체 보기
                    </button>
                  </div>
                  <div className="mt-3 space-y-2.5">
                    {layerGroups.map(({ group, items }) => (
                      <div key={group}>
                        <p className="mb-1.5 flex items-baseline gap-2 text-[8.5px] tracking-[0.26em] text-[#8b816e]">
                          <span className="shrink-0">
                            {LAYER_GROUP_LABEL[group]}
                          </span>
                          <span className="h-px flex-1 bg-white/[0.07]" />
                          <span className="font-mono text-[8.5px] text-[#6f6a61]">
                            {items.length}
                          </span>
                        </p>
                        {group === "upper" && (
                          <p className="mb-1.5 text-[9px] leading-none text-[#6b665e]">
                            {LAYER_GROUP_HINT.upper}
                          </p>
                        )}
                        <ul className="grid grid-cols-2 gap-1.5">
                          {items.map((layer) => {
                            const active = isolated === layer.index;
                            return (
                              <li key={layer.key}>
                                <button
                                  type="button"
                                  onClick={() => toggleLayer(layer.index)}
                                  className={cx(
                                    "flex w-full items-center gap-1.5 rounded-lg border px-2 py-1.5 text-left transition-colors",
                                    active
                                      ? "border-[#d9b779]/45 bg-[#d9b779]/10"
                                      : "border-white/[0.05] bg-white/[0.015] hover:border-white/10 hover:bg-white/[0.04]",
                                  )}
                                >
                                  <span
                                    className={cx(
                                      "font-mono text-[9.5px]",
                                      active ? "text-[#e9c77c]" : "text-[#6f6a61]",
                                    )}
                                  >
                                    {partNo(displayNo.get(layer.index) ?? layer.index + 1)}
                                  </span>
                                  <span
                                    className={cx(
                                      "truncate text-[11.5px]",
                                      active ? "text-[#f5e9d4]" : "text-[#d2ccbf]",
                                    )}
                                  >
                                    {layer.ko}
                                  </span>
                                </button>
                              </li>
                            );
                          })}
                        </ul>
                      </div>
                    ))}
                  </div>
                  <p className="mt-2 min-h-[3.4em] rounded-lg border border-white/[0.04] bg-white/[0.015] px-2.5 py-1.5 text-[10.5px] leading-relaxed text-[#827d73]">
                    {missingLayer
                      ? `이 전각에는 ${missingLayer} 부재가 없습니다.`
                      : isolatedInfo
                        ? isolatedInfo.desc
                        : "부품을 누르면 해당 부재만 실제 형상으로 남기고 나머지는 구조선으로 보여 줍니다."}
                  </p>
                </div>
              </div>

              <div className="border-t border-white/[0.06] p-4">
                <button
                  type="button"
                  onClick={() => selectBuilding(null)}
                  className="flex w-full items-center justify-center gap-2 rounded-xl border border-white/10 bg-white/[0.03] py-2.5 text-[11.5px] text-[#d6cdbc] transition-colors hover:border-[#d9b779]/40 hover:bg-[#d9b779]/10 hover:text-[#f3e6cd]"
                >
                  <Boxes size={14} strokeWidth={1.6} />
                  궁궐 전체 보기
                </button>
              </div>
            </motion.div>
          ) : (
            <motion.div
              key="list"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }}
              transition={{ duration: 0.22, ease: "easeOut" }}
              className="flex min-h-0 flex-1 flex-col"
            >
              <div className="panel-scroll flex-1 overflow-y-auto py-2">
                {BUILDINGS.map((building) => {
                  const active = selectedId === building.id;
                  const hovered = hoveredId === building.id;
                  return (
                    <button
                      key={building.id}
                      type="button"
                      data-building-id={building.id}
                      onClick={() => selectBuilding(building.id)}
                      onMouseEnter={() => setHoveredId(building.id)}
                      onMouseLeave={() => setHoveredId(null)}
                      className={cx(
                        "group relative flex w-full items-center gap-3 border-l-2 px-5 py-2.5 text-left transition-colors",
                        active
                          ? "border-[#d9b779] bg-white/[0.06]"
                          : hovered
                            ? "border-[#d9b779]/40 bg-white/[0.035]"
                            : "border-transparent",
                      )}
                    >
                      <span
                        className={cx(
                          "w-6 shrink-0 font-serif text-[11px] transition-colors",
                          active || hovered ? "text-[#d9b779]" : "text-[#5f5b53]",
                        )}
                      >
                        {building.hanja.slice(0, 1)}
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="flex items-baseline justify-between gap-2">
                          <span className="font-serif text-[14.5px] text-[#eee5d3]">
                            {building.ko}
                          </span>
                          <span className="shrink-0 text-[9px] tracking-[0.16em] text-[#8a8478]">
                            {KIND_LABEL[building.kind]}
                          </span>
                        </span>
                        <span className="mt-0.5 flex items-center justify-between gap-2">
                          <span className="truncate text-[10.5px] text-[#7f7a70]">
                            {building.note ?? building.hanja}
                          </span>
                          <ChevronRight
                            size={12}
                            strokeWidth={1.8}
                            className="shrink-0 text-[#6d685f] transition-transform group-hover:translate-x-0.5"
                          />
                        </span>
                      </span>
                    </button>
                  );
                })}
              </div>
              <p className="border-t border-white/[0.06] px-5 py-3 text-[9.5px] leading-relaxed text-[#77726a]">
                실측 치수를 바탕으로 절차적으로 생성한 모델입니다. 전각을
                선택하면 부재 하나하나로 분해해 볼 수 있습니다.
              </p>
            </motion.div>
          )}
        </AnimatePresence>
      </aside>

      {/* part rail — only meaningful once a hall is picked */}
      {selected && (
      <div className="panel-scroll pointer-events-auto absolute right-6 top-24 z-30 hidden max-h-[calc(100dvh-12.5rem)] w-[172px] flex-col overflow-y-auto rounded-2xl border border-white/[0.08] bg-[#0a0d11]/70 p-2 shadow-[0_24px_60px_rgba(0,0,0,0.45)] backdrop-blur-2xl lg:flex">
        <div className="flex items-center justify-between px-2 pb-1.5 pt-1">
          <span className="flex items-center gap-1.5 text-[9px] tracking-[0.3em] text-[#c9b48c]/80">
            <Layers size={11} strokeWidth={1.7} />
            PARTS
          </span>
          <button
            type="button"
            data-layer-clear
            onClick={clearLayers}
            className={cx(
              "text-[9.5px] transition-colors",
              isolated === null
                ? "text-[#6f6a61]"
                : "text-[#c9a86f] hover:text-[#f0dcb4]",
            )}
          >
            전체
          </button>
        </div>
        {layerGroups.map(({ group, items }) => (
          <div key={group} className="mt-1 first:mt-0">
            <p className="flex items-center gap-2 px-2.5 pb-1 pt-1.5 text-[8px] tracking-[0.24em] text-[#7d7362]">
              <span>{LAYER_GROUP_LABEL[group]}</span>
              <span className="h-px flex-1 bg-white/[0.06]" />
              <span className="font-mono">{items.length}</span>
            </p>
            {items.map((layer) => {
              const active = isolated === layer.index;
              return (
                <button
                  key={layer.key}
                  type="button"
                  data-layer-index={layer.index}
                  onClick={() => toggleLayer(layer.index)}
                  className={cx(
                    "flex w-full items-center gap-2.5 rounded-lg px-2.5 py-[7px] text-left transition-colors",
                    active ? "bg-[#d9b779]/12" : "hover:bg-white/[0.05]",
                  )}
                >
                  <span
                    className={cx(
                      "font-mono text-[9.5px]",
                      active ? "text-[#e9c77c]" : "text-[#67635b]",
                    )}
                  >
                    {partNo(displayNo.get(layer.index) ?? layer.index + 1)}
                  </span>
                  <span
                    className={cx(
                      "truncate text-[11.5px]",
                      active ? "text-[#f5e9d4]" : "text-[#bcb6aa]",
                    )}
                  >
                    {layer.ko}
                  </span>
                  <span
                    className={cx(
                      "ml-auto h-1.5 w-1.5 shrink-0 rounded-full transition-colors",
                      active ? "bg-[#e9c77c]" : "bg-white/15",
                    )}
                  />
                </button>
              );
            })}
          </div>
        ))}
        <p className="px-2 pb-1 pt-2 text-[9.5px] leading-relaxed text-[#6f6a61]">
          {missingLayer
            ? `이 전각에는 ${missingLayer} 부재가 없습니다.`
            : isolatedInfo
              ? `${isolatedInfo.ko}만 실물로 표시하고 나머지는 구조선으로 처리합니다.`
              : "부품을 선택하면 해당 구조만 남습니다."}
        </p>
      </div>
      )}

      {/* explode control */}
      <div className="pointer-events-none absolute inset-x-4 bottom-4 z-30 flex justify-center md:bottom-5">
        <div className="pointer-events-auto w-full max-w-[540px] rounded-2xl border border-white/[0.08] bg-[#0a0d11]/82 px-4 py-3 shadow-[0_24px_60px_rgba(0,0,0,0.5)] backdrop-blur-2xl">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Sparkles size={12} strokeWidth={1.8} className="text-[#c9a86f]" />
              <span className="text-[9.5px] tracking-[0.3em] text-[#c9b48c]">
                부품 분해
              </span>
            </div>
            <span className="font-mono text-[10.5px] text-[#d9b779]">
              {String(Math.round(explode * 100)).padStart(3, "0")}%
            </span>
          </div>

          <div className="mt-2.5 flex items-center gap-3">
            <button
              type="button"
              onClick={() => applyExplode(0)}
              className={cx(
                "shrink-0 rounded-full border px-3 py-1.5 text-[11px] transition-colors",
                explode < 0.02
                  ? "border-[#d9b779]/45 bg-[#d9b779]/12 text-[#f0d9a7]"
                  : "border-white/10 text-[#a8a299] hover:border-white/20 hover:text-[#e8dfcd]",
              )}
            >
              조립
            </button>

            <input
              type="range"
              min={0}
              max={100}
              step={1}
              value={Math.round(explode * 100)}
              onChange={(event) => applyExplode(Number(event.target.value) / 100)}
              aria-label="부품 분해 정도"
              className="range-gold h-1.5 w-full flex-1 cursor-pointer appearance-none rounded-full"
              style={{
                background: `linear-gradient(to right, #d9b779 0%, #d9b779 ${
                  explode * 100
                }%, rgba(255,255,255,0.12) ${explode * 100}%, rgba(255,255,255,0.12) 100%)`,
              }}
            />

            <button
              type="button"
              onClick={() => applyExplode(1)}
              className={cx(
                "shrink-0 rounded-full border px-3 py-1.5 text-[11px] transition-colors",
                explode > 0.98
                  ? "border-[#d9b779]/45 bg-[#d9b779]/12 text-[#f0d9a7]"
                  : "border-white/10 text-[#a8a299] hover:border-white/20 hover:text-[#e8dfcd]",
              )}
            >
              분해
            </button>
          </div>
        </div>
      </div>

      {/* camera presets */}
      <div className="pointer-events-auto absolute bottom-5 right-6 z-30 hidden items-center gap-0.5 rounded-full border border-white/[0.08] bg-[#0a0d11]/75 p-1 shadow-[0_24px_60px_rgba(0,0,0,0.45)] backdrop-blur-2xl xl:flex">
        <button
          type="button"
          onClick={resetView}
          aria-label="기본 화면"
          className="flex h-7 w-7 items-center justify-center rounded-full text-[#9a958b] transition-colors hover:bg-white/5 hover:text-[#e8dfcd]"
        >
          <RotateCcw size={12.5} strokeWidth={1.8} />
        </button>
        <span className="mx-1 h-3.5 w-px bg-white/10" />
        {CAMERA_PRESETS.map((item) => (
          <button
            key={item.id}
            type="button"
            title={item.hint}
            onClick={() => applyPreset(item.id)}
            className={cx(
              "rounded-full px-2.5 py-1.5 text-[10.5px] transition-colors",
              preset === item.id
                ? "bg-[#d9b779]/14 text-[#f0d9a7]"
                : "text-[#a29d93] hover:text-[#ece3d2]",
            )}
          >
            {item.ko}
          </button>
        ))}
      </div>

      {/* hint */}
      <div className="pointer-events-none absolute bottom-[7.4rem] left-1/2 z-20 hidden -translate-x-1/2 xl:block">
        <AnimatePresence>
          {hintVisible && (
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }}
              transition={{ duration: 0.6 }}
              className="flex items-center gap-2 rounded-full border border-white/[0.07] bg-[#090c10]/60 px-3 py-1.5 text-[10.5px] text-[#a49e92] backdrop-blur-md"
            >
              <MousePointer2 size={12} strokeWidth={1.7} className="text-[#c9a86f]" />
              드래그로 회전 · 스크롤로 확대 · 전각을 클릭해 보세요
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      <div className="pointer-events-none absolute bottom-5 left-6 z-10 hidden items-center gap-2 text-[9px] tracking-[0.22em] text-[#5f5b54] xl:flex">
        <span className="h-px w-6 bg-[#d9b779]/30" />
        BLENDER · THREE.JS · 절차적 생성
      </div>

      {/* loading */}
      <AnimatePresence>
        {!ready && !failed && (
          <motion.div
            key="loading"
            initial={{ opacity: 1 }}
            exit={{ opacity: 0, transition: { duration: 0.9, ease: "easeInOut" } }}
            className="fixed inset-0 z-50 flex flex-col items-center justify-center bg-[#06080b]"
          >
            <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_50%_44%,rgba(217,183,121,0.10),transparent_58%)]" />
            <div className="relative flex flex-col items-center">
              <div className="flex h-16 w-16 items-center justify-center border border-[#d9b779]/35">
                <span className="font-serif text-[26px] text-[#e2c48c]">景</span>
              </div>
              <h2 className="mt-7 font-serif text-[26px] tracking-[0.5em] text-[#f2e8d6]">
                경복궁
              </h2>
              <p className="mt-2.5 text-[9px] tracking-[0.5em] text-[#8e8069]">
                景福宮 · GYEONGBOKGUNG
              </p>

              <div className="mt-10 h-px w-[248px] overflow-hidden bg-white/10">
                <div
                  className="h-full bg-[#d9b779] transition-[width] duration-300 ease-out"
                  style={{ width: `${Math.max(4, Math.round(progress * 100))}%` }}
                />
              </div>
              <div className="mt-3 flex w-[248px] items-center justify-between font-mono text-[9.5px] text-[#7b7569]">
                <span>전각을 짓는 중</span>
                <span>{String(Math.round(progress * 100)).padStart(3, "0")}%</span>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {failed && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-[#06080b] px-6">
          <div className="max-w-md text-center">
            <p className="font-serif text-2xl text-[#f2e8d6]">
              3D 모델을 불러오지 못했습니다
            </p>
            <p className="mt-3 text-[13px] leading-relaxed text-[#9a9488]">
              네트워크 상태를 확인한 뒤 페이지를 새로고침해 주세요.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
