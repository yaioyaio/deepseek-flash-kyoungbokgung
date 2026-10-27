export type LayerKey =
  | "base"
  | "floor"
  | "plinth"
  | "column"
  | "wall"
  | "door"
  | "lintel"
  | "frame"
  | "bracket"
  | "purlin"
  | "rafter"
  | "eave"
  | "hip"
  | "roof"
  | "tile"
  | "maksae"
  | "upper_floor"
  | "upper_column"
  | "upper_wall"
  | "upper_door"
  | "upper_lintel"
  | "upper_bracket"
  | "upper_purlin"
  | "upper_rafter"
  | "upper_eave"
  | "upper_hip"
  | "upper_roof"
  | "upper_tile"
  | "upper_maksae"
  | "ridge";

/** which tier of the building a member belongs to */
export type LayerGroup = "lower" | "upper" | "cap";

export interface LayerInfo {
  index: number;
  key: LayerKey;
  ko: string;
  hanja: string;
  en: string;
  desc: string;
  group: LayerGroup;
}

export type BuildingKind = "gate" | "hall" | "pavilion";

export interface Building {
  id: string;
  ko: string;
  hanja: string;
  kind: BuildingKind;
  year: string;
  /** number of storeys: 2 for 광화문 · 근정전 · 경회루 · 향원정 */
  tiers: 1 | 2;
  /** Blender X (east) — same axis in three.js */
  x: number;
  /** Blender Y (north) — becomes -z in three.js */
  y: number;
  height: number;
  width: number;
  depth: number;
  note?: string;
  description: string;
}

export type TimeKey = "day" | "sunset" | "night";

export interface LabelPosition {
  id: string;
  x: number;
  y: number;
  visible: boolean;
  depth: number;
}

export interface CameraPreset {
  id: string;
  ko: string;
  hint: string;
  position: [number, number, number];
  target: [number, number, number];
  fov?: number;
}
