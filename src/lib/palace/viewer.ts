import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { BUILDINGS, CAMERA_PRESETS } from "./data";
import type { CameraPreset, LabelPosition, TimeKey } from "./types";
import { GroundSkirt, Mountains, Petals, createWaterMaterial } from "./scenery";
import { NightSky, Sky, TIME_STATES, type TimeState } from "./sky";

/** MeshStandardMaterial exposes wireframe, but Material does not */
type WireMaterial = THREE.Material & { wireframe?: boolean };

export interface ViewerCallbacks {
  onProgress?: (ratio: number) => void;
  onReady?: () => void;
  onError?: (error: unknown) => void;
  onHover?: (id: string | null) => void;
  onSelect?: (id: string | null) => void;
  onLabels?: (labels: LabelPosition[]) => void;
}

interface BuildingNode {
  id: string;
  root: THREE.Object3D;
  layers: THREE.Object3D[];
  meshes: THREE.Mesh[];
  height: number;
  width: number;
  depth: number;
  center: THREE.Vector3;
  radius: number;
  baseBox: THREE.Box3;
  /** rest-pose world bounds of each layer, used to stack them without overlap */
  layerBoxes: THREE.Box3[];
  /** lift of each layer in metres at explode = 1 */
  lifts: number[];
}

/** vertical separation of the parts, relative to building height */
function explodeStep(i: number, count: number) {
  if (i === 0 || count < 2) return 0;
  return 1.05 * (i / (count - 1));
}

const DEFAULT_FOV = 42;

const OVERVIEW = CAMERA_PRESETS[0];

function cloneState(s: TimeState): TimeState {
  return {
    sunDir: s.sunDir.clone(),
    sunColor: s.sunColor.clone(),
    sunIntensity: s.sunIntensity,
    skyTop: s.skyTop.clone(),
    skyHorizon: s.skyHorizon.clone(),
    skyGround: s.skyGround.clone(),
    fog: s.fog.clone(),
    fogDensity: s.fogDensity,
    hemiSky: s.hemiSky.clone(),
    hemiGround: s.hemiGround.clone(),
    hemiIntensity: s.hemiIntensity,
    ambient: s.ambient,
    exposure: s.exposure,
    night: s.night,
    sunGlow: s.sunGlow,
  };
}

function lerpState(a: TimeState, b: TimeState, t: number, out: TimeState) {
  out.sunDir.copy(a.sunDir).lerp(b.sunDir, t).normalize();
  out.sunColor.copy(a.sunColor).lerp(b.sunColor, t);
  out.sunIntensity = THREE.MathUtils.lerp(a.sunIntensity, b.sunIntensity, t);
  out.skyTop.copy(a.skyTop).lerp(b.skyTop, t);
  out.skyHorizon.copy(a.skyHorizon).lerp(b.skyHorizon, t);
  out.skyGround.copy(a.skyGround).lerp(b.skyGround, t);
  out.fog.copy(a.fog).lerp(b.fog, t);
  out.fogDensity = THREE.MathUtils.lerp(a.fogDensity, b.fogDensity, t);
  out.hemiSky.copy(a.hemiSky).lerp(b.hemiSky, t);
  out.hemiGround.copy(a.hemiGround).lerp(b.hemiGround, t);
  out.hemiIntensity = THREE.MathUtils.lerp(a.hemiIntensity, b.hemiIntensity, t);
  out.ambient = THREE.MathUtils.lerp(a.ambient, b.ambient, t);
  out.exposure = THREE.MathUtils.lerp(a.exposure, b.exposure, t);
  out.night = THREE.MathUtils.lerp(a.night, b.night, t);
  out.sunGlow = THREE.MathUtils.lerp(a.sunGlow, b.sunGlow, t);
}

function easeInOut(t: number) {
  return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
}

function footprintTexture() {
  const size = 256;
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = size;
  const ctx = canvas.getContext("2d")!;
  const pad = 16;
  ctx.strokeStyle = "rgba(240, 208, 140, 0.26)";
  ctx.lineWidth = 2;
  ctx.strokeRect(pad, pad, size - pad * 2, size - pad * 2);

  ctx.strokeStyle = "rgba(246, 216, 150, 0.95)";
  ctx.lineWidth = 6;
  ctx.lineCap = "square";
  const arm = 54;
  const corners: [number, number, number, number][] = [
    [pad, pad, 1, 1],
    [size - pad, pad, -1, 1],
    [pad, size - pad, 1, -1],
    [size - pad, size - pad, -1, -1],
  ];
  for (const [x, y, sx, sy] of corners) {
    ctx.beginPath();
    ctx.moveTo(x + sx * arm, y);
    ctx.lineTo(x, y);
    ctx.lineTo(x, y + sy * arm);
    ctx.stroke();
  }

  const tex = new THREE.CanvasTexture(canvas);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 4;
  return tex;
}

export class PalaceViewer {
  private canvas: HTMLCanvasElement;
  private cb: ViewerCallbacks;

  private renderer: THREE.WebGLRenderer;
  private scene: THREE.Scene;
  private camera: THREE.PerspectiveCamera;
  private controls: OrbitControls;
  private lastFrame = performance.now();
  private elapsed = 0;

  private sun: THREE.DirectionalLight;
  private hemi: THREE.HemisphereLight;
  private ambient: THREE.AmbientLight;
  private lanterns: THREE.PointLight[] = [];

  private sky: Sky;
  private nightSky: NightSky;
  private mountains: Mountains;
  private groundSkirt: GroundSkirt;
  private petals: Petals;
  private waterMaterial: THREE.MeshStandardMaterial | null = null;

  private pmrem: THREE.PMREMGenerator;
  private envScene = new THREE.Scene();
  private envTarget: THREE.WebGLRenderTarget | null = null;

  private buildings = new Map<string, BuildingNode>();
  private pickMeshes: THREE.Mesh[] = [];
  private latticeMats: THREE.MeshStandardMaterial[] = [];
  private lanternMats: THREE.MeshStandardMaterial[] = [];

  private current: TimeState = cloneState(TIME_STATES.day);
  private timeFrom: TimeState = cloneState(TIME_STATES.day);
  private timeTo: TimeState = cloneState(TIME_STATES.day);
  private timeT = 1;
  private timeStart = 0;
  private timeDuration = 0.95;
  private timeKey: TimeKey = "day";

  private explode = 0;
  private explodeTarget = 0;
  private isolated: number | null = null;
  /** context buildings are faded while the selected one is exploded */
  private dimmed = false;
  private static readonly DIM_OPACITY = 0.17;
  /** everything except the isolated part fades to this */
  private static readonly ISOLATED_GHOST = 0.08;

  private selected: string | null = null;
  private hovered: string | null = null;
  private selectedBox = new THREE.Box3();
  private boxHelper: THREE.Box3Helper;
  private hoverFoot: THREE.Mesh;
  private selectFoot: THREE.Mesh;

  private userAdjusted = false;
  private lastRefit = 0;

  private tween: {
    fromPos: THREE.Vector3;
    toPos: THREE.Vector3;
    fromTarget: THREE.Vector3;
    toTarget: THREE.Vector3;
    fromFov: number;
    toFov: number;
    start: number;
    duration: number;
  } | null = null;

  private pointer = new THREE.Vector2(-10, -10);
  private raycaster = new THREE.Raycaster();
  private pointerDown = { x: 0, y: 0, t: 0 };
  private lastHoverTest = 0;
  private labelsEnabled = true;
  private labelClock = 0;

  private raf = 0;
  private disposed = false;
  private ready = false;

  constructor(canvas: HTMLCanvasElement, callbacks: ViewerCallbacks = {}) {
    this.canvas = canvas;
    this.cb = callbacks;

    this.renderer = new THREE.WebGLRenderer({
      canvas,
      antialias: true,
      alpha: false,
      powerPreference: "high-performance",
    });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1;
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFShadowMap;

    this.scene = new THREE.Scene();
    this.scene.fog = new THREE.FogExp2(0xd6dddd, 0.0024);
    this.scene.environmentIntensity = 0.52;

    this.camera = new THREE.PerspectiveCamera(42, 1, 0.5, 7000);
    this.camera.position.set(0, 340, 500);

    this.controls = new OrbitControls(this.camera, canvas);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.065;
    this.controls.rotateSpeed = 0.6;
    this.controls.zoomSpeed = 0.8;
    this.controls.panSpeed = 0.7;
    this.controls.minDistance = 8;
    this.controls.maxDistance = 1100;
    this.controls.maxPolarAngle = Math.PI * 0.497;
    this.controls.target.set(0, 6, 0);
    this.controls.update();

    this.sun = new THREE.DirectionalLight(0xfff1d8, 3);
    this.sun.castShadow = true;
    this.sun.shadow.mapSize.set(2048, 2048);
    this.sun.shadow.camera.near = 20;
    this.sun.shadow.camera.far = 900;
    this.sun.shadow.camera.left = -200;
    this.sun.shadow.camera.right = 200;
    this.sun.shadow.camera.top = 215;
    this.sun.shadow.camera.bottom = -195;
    this.sun.shadow.bias = -0.0003;
    this.sun.shadow.normalBias = 0.8;
    this.scene.add(this.sun, this.sun.target);

    this.hemi = new THREE.HemisphereLight(0xc3d8ec, 0x6a6a52, 0.7);
    this.ambient = new THREE.AmbientLight(0xffffff, 0.16);
    this.scene.add(this.hemi, this.ambient);

    const lanternSpots: [number, number, number][] = [
      [0, 24, 30],
      [0, 22, -8],
      [-78, 16, -20],
      [56, 12, -144],
      [0, 20, -118],
      [-46, 15, -224],
      [54, 15, -224],
      [-84, 14, -96],
      [92, 16, -168],
    ];
    for (const [x, y, z] of lanternSpots) {
      const light = new THREE.PointLight(0xffb063, 0, 130, 2);
      light.position.set(x, y, z);
      this.scene.add(light);
      this.lanterns.push(light);
    }

    this.sky = new Sky();
    this.scene.add(this.sky.mesh);
    this.nightSky = new NightSky();
    this.scene.add(this.nightSky.group);
    this.mountains = new Mountains();
    this.scene.add(this.mountains.group);
    this.groundSkirt = new GroundSkirt();
    this.scene.add(this.groundSkirt.mesh);
    this.petals = new Petals();
    this.scene.add(this.petals.points);

    const texLoader = new THREE.TextureLoader();
    texLoader.load("/textures/water_normal.jpg", (tex) => {
      if (this.waterMaterial) return;
      tex.colorSpace = THREE.NoColorSpace;
      this.waterMaterial = createWaterMaterial(tex);
      this.applyWaterMaterial();
    });

    this.boxHelper = new THREE.Box3Helper(this.selectedBox, 0xe9c77c);
    const boxMat = this.boxHelper.material as THREE.LineBasicMaterial;
    boxMat.transparent = true;
    boxMat.opacity = 0.7;
    boxMat.depthWrite = false;
    this.boxHelper.visible = false;
    this.scene.add(this.boxHelper);

    const footTex = footprintTexture();
    this.hoverFoot = new THREE.Mesh(
      new THREE.PlaneGeometry(1, 1).rotateX(-Math.PI / 2),
      new THREE.MeshBasicMaterial({
        map: footTex,
        transparent: true,
        depthWrite: false,
        opacity: 0.32,
        color: 0xcfe0ff,
      }),
    );
    this.selectFoot = new THREE.Mesh(
      new THREE.PlaneGeometry(1, 1).rotateX(-Math.PI / 2),
      new THREE.MeshBasicMaterial({
        map: footTex,
        transparent: true,
        depthWrite: false,
        opacity: 0.9,
        color: 0xffdca0,
      }),
    );
    this.hoverFoot.visible = false;
    this.selectFoot.visible = false;
    this.hoverFoot.renderOrder = 3;
    this.selectFoot.renderOrder = 3;
    this.scene.add(this.hoverFoot, this.selectFoot);

    this.current = cloneState(TIME_STATES.day);
    this.applyTime();

    this.pmrem = new THREE.PMREMGenerator(this.renderer);
    this.bakeEnvironment();

    this.resize();
    this.bindEvents();
    if (process.env.NODE_ENV !== "production") {
      (window as unknown as { __palaceViewer?: PalaceViewer }).__palaceViewer = this;
    }
    this.raf = requestAnimationFrame(this.tick);
  }

  /* ---------------------------------------------------------------- */
  /* loading                                                          */
  /* ---------------------------------------------------------------- */

  async load(url = "/models/gyeongbokgung.glb") {
    try {
      const response = await fetch(url, { cache: "no-store" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const total = Number(response.headers.get("content-length")) || 0;
      const reader = response.body?.getReader();
      if (!reader) throw new Error("streaming unsupported");

      const chunks: Uint8Array[] = [];
      let received = 0;
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        if (!value) continue;
        chunks.push(value);
        received += value.byteLength;
        const ratio =
          total > 0 ? received / total : 1 - Math.exp(-received / 7_000_000);
        this.cb.onProgress?.(Math.min(0.92, ratio * 0.92));
      }

      const bytes = new Uint8Array(received);
      let offset = 0;
      for (const chunk of chunks) {
        bytes.set(chunk, offset);
        offset += chunk.byteLength;
      }
      this.cb.onProgress?.(0.94);

      const loader = new GLTFLoader();
      loader.parse(
        bytes.buffer,
        "",
        (gltf) => {
          try {
            this.attachModel(gltf.scene);
            this.cb.onProgress?.(1);
            this.flyTo(
              OVERVIEW.position,
              OVERVIEW.target,
              3.2,
              OVERVIEW.fov,
            );
            this.ready = true;
          } catch (error) {
            console.error(error);
            this.cb.onError?.(error);
          }
        },
        (error) => {
          console.error(error);
          this.cb.onError?.(error);
        },
      );
    } catch (error) {
      console.error(error);
      this.cb.onError?.(error);
    }
  }

  private attachModel(root: THREE.Object3D) {
    root.traverse((obj) => {
      const mesh = obj as THREE.Mesh;
      if (!mesh.isMesh) return;
      const mats = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
      const matNames = mats.map((m) => m.name);
      const groundLike =
        matNames.includes("ground") ||
        matNames.includes("paving") ||
        matNames.includes("water");
      mesh.castShadow = !groundLike;
      mesh.receiveShadow = true;
      for (const m of mats) {
        const std = m as THREE.MeshStandardMaterial;
        if (std.map) std.map.anisotropy = 8;
        if (std.normalMap) std.normalMap.anisotropy = 8;
      }
      const cloned = mats.map((m) => {
        const c = m.clone();
        c.shadowSide = THREE.FrontSide;
        return c;
      });
      mesh.material = Array.isArray(mesh.material) ? cloned : cloned[0];
      for (const m of cloned) {
        const std = m as THREE.MeshStandardMaterial;
        if (std.isMeshStandardMaterial) {
          if (std.name === "lattice") {
            std.emissive = new THREE.Color(0xffffff);
            std.emissiveIntensity = 0;
            this.latticeMats.push(std);
          }
          if (std.name === "lantern_paper") {
            std.emissive = new THREE.Color(0xffa552);
            std.emissiveIntensity = 0;
            this.lanternMats.push(std);
          }
        }
      }
      mesh.userData.baseMaterialState = cloned.map((m) => ({
        transparent: m.transparent,
        opacity: m.opacity,
        depthWrite: m.depthWrite,
        wireframe: (m as WireMaterial).wireframe ?? false,
      }));
    });

    for (const meta of BUILDINGS) {
      const node = root.getObjectByName(`B_${meta.id}`);
      if (!node) continue;
      const layers: THREE.Object3D[] = [];
      const rides: number[] = [];
      node.children.forEach((child) => {
        const index = child.userData?.layer;
        if (typeof index !== "number") return;
        layers[index] = child;
        const ride = child.userData?.layer_ride;
        if (typeof ride === "number") rides[index] = ride;
      });
      const meshes: THREE.Mesh[] = [];
      for (const layer of layers) {
        if (!layer) continue;
        layer.traverse((obj) => {
          const mesh = obj as THREE.Mesh;
          if (mesh.isMesh) {
            mesh.userData.buildingId = meta.id;
            meshes.push(mesh);
          }
        });
      }
      const center = new THREE.Vector3(
        meta.x,
        meta.height * 0.44,
        -meta.y,
      );

      // Layers interlock in the assembled state (walls reach into the beam
      // band, brackets into the eave).  Derive the lift per layer so the
      // exploded stack separates with a real air gap instead of using a
      // fixed fraction that lets tall layers pass through each other.
      //
      // Empty slots (the upper storey of single-storey halls) would otherwise
      // compress the parts that do exist, so the vertical rhythm is ranked
      // over the layers that actually hold geometry.
      const layerBoxes = Array.from({ length: layers.length }, (_, i) => {
        const box = new THREE.Box3();
        const layer = layers[i];
        if (layer) box.setFromObject(layer);
        return box;
      });
      const rankOf = new Map<number, number>();
      let filled = 0;
      for (let i = 0; i < layerBoxes.length; i++) {
        if (layerBoxes[i].isEmpty()) continue;
        rankOf.set(i, filled);
        filled += 1;
      }
      const gap = meta.height * 0.03;
      const lifts = new Array(layers.length).fill(0);
      let prevTop: number | null = null;
      for (let i = 0; i < layers.length; i++) {
        const box = layerBoxes[i];
        const want = explodeStep(rankOf.get(i) ?? 0, filled) * meta.height;
        if (box.isEmpty()) {
          lifts[i] = want;
          continue;
        }
        // Parts that ride on another layer (막새 on 기와) sit at the eave, far
        // below the apex of the layer above them, so the `need` rule would
        // fling them up to the tile ridge.  They just follow their host.
        const ride = rides[i];
        if (typeof ride === "number") {
          lifts[i] = lifts[ride] + gap * 0.6;
          continue;
        }
        const need = prevTop === null ? -Infinity : prevTop + gap - box.min.y;
        lifts[i] = Math.max(want, need);
        prevTop = box.max.y + lifts[i];
      }

      this.buildings.set(meta.id, {
        id: meta.id,
        root: node,
        layers,
        meshes,
        height: meta.height,
        width: meta.width,
        depth: meta.depth,
        center,
        radius: Math.max(meta.width, meta.depth, meta.height) * 0.5,
        baseBox: new THREE.Box3().setFromObject(node),
        layerBoxes,
        lifts,
      });
      this.pickMeshes.push(...meshes);
    }

    const groundMats: THREE.MeshStandardMaterial[] = [];
    root.traverse((obj) => {
      const mesh = obj as THREE.Mesh;
      if (!mesh.isMesh) return;
      const list = Array.isArray(mesh.material)
        ? mesh.material
        : [mesh.material];
      for (const m of list) {
        const std = m as THREE.MeshStandardMaterial;
        if (std.name === "ground" && std.map) groundMats.push(std);
      }
    });
    this.groundSkirt.setMap(groundMats[0]?.map ?? null);

    this.scene.add(root);
    this.applyWaterMaterial();
    this.applyTime();
    this.applyExplode(true);
  }

  private applyWaterMaterial() {
    const water = this.ensureWaterMaterial();
    this.scene.traverse((obj) => {
      const mesh = obj as THREE.Mesh;
      if (!mesh.isMesh) return;
      const mats = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
      if (mats.some((m) => m.name === "water")) {
        mesh.material = water;
        mesh.receiveShadow = true;
        mesh.castShadow = false;
      }
    });
  }

  private ensureWaterMaterial() {
    if (!this.waterMaterial) {
      const tex = new THREE.TextureLoader().load("/textures/water_normal.jpg");
      tex.colorSpace = THREE.NoColorSpace;
      this.waterMaterial = createWaterMaterial(tex);
    }
    return this.waterMaterial;
  }

  /* ---------------------------------------------------------------- */
  /* time of day                                                      */
  /* ---------------------------------------------------------------- */

  setTime(key: TimeKey) {
    if (key === this.timeKey && this.timeT >= 1) return;
    const target = TIME_STATES[key];
    const from = cloneState(this.current);
    // from the current blended state, not from a named preset
    this.timeFrom = from;
    this.timeTo = cloneState(target);
    this.timeKey = key;
    this.timeT = 0;
    this.timeStart = performance.now();
  }

  getTimeKey() {
    return this.timeKey;
  }

  private applyTime() {
    const s = this.current;
    this.sun.position.copy(s.sunDir).multiplyScalar(360);
    this.sun.color.copy(s.sunColor);
    this.sun.intensity = s.sunIntensity;

    this.hemi.color.copy(s.hemiSky);
    this.hemi.groundColor.copy(s.hemiGround);
    this.hemi.intensity = s.hemiIntensity;
    this.ambient.intensity = s.ambient;

    for (const light of this.lanterns) {
      light.intensity = s.night * 480;
    }

    this.renderer.toneMappingExposure = s.exposure;
    const fog = this.scene.fog as THREE.FogExp2;
    fog.color.copy(s.fog);
    fog.density = s.fogDensity;
    this.renderer.setClearColor(s.fog);

    this.sky.apply(s);
    this.nightSky.apply(s, this.camera);
    this.mountains.apply(s.fog, s.night);
    this.groundSkirt.apply(s.fog, s.night);

    const latticeGlow = 0.03 + s.night * 0.82;
    for (const m of this.latticeMats) m.emissiveIntensity = latticeGlow;
    const lanternGlow = 0.06 + s.night * 1.15;
    for (const m of this.lanternMats) m.emissiveIntensity = lanternGlow;
  }

  private bakeEnvironment() {
    const prev = this.sky.mesh.position.clone();
    this.sky.mesh.position.set(0, 0, 0);
    this.envScene.add(this.sky.mesh);
    const target = this.pmrem.fromScene(this.envScene, 0.03, 0.1, 8000);
    this.scene.add(this.sky.mesh);
    this.sky.mesh.position.copy(prev);
    const old = this.envTarget;
    this.envTarget = target;
    this.scene.environment = target.texture;
    old?.dispose();
  }

  /* ---------------------------------------------------------------- */
  /* explode + layer isolation                                        */
  /* ---------------------------------------------------------------- */

  setExplode(value: number) {
    const next = THREE.MathUtils.clamp(value, 0, 1);
    if (Math.abs(next - this.explodeTarget) < 0.0001) return;
    this.explodeTarget = next;
    const b = this.selected ? this.buildings.get(this.selected) : null;
    if (b && !this.userAdjusted) {
      const now = performance.now();
      if (now - this.lastRefit > 140) {
        this.lastRefit = now;
        this.frameSelected(b, 0.75, next);
      }
    }
  }

  private applyExplode(force = false) {
    const e = this.explode;
    for (const b of this.buildings.values()) {
      for (let i = 0; i < b.layers.length; i++) {
        const layer = b.layers[i];
        if (!layer) continue;
        const y = (b.lifts[i] ?? 0) * e;
        if (force || Math.abs(layer.position.y - y) > 0.0005) {
          layer.position.y = y;
        }
      }
    }
    const dim = this.selected !== null && e > 0.18;
    if (dim !== this.dimmed) this.refreshGhosts();
  }

  setIsolatedLayer(index: number | null) {
    if (this.isolated === index) return true;
    if (index !== null) {
      const b = this.selected ? this.buildings.get(this.selected) : null;
      const box = b?.layerBoxes[index];
      // this building may simply have no such member (an open pavilion has
      // no walls, for instance) — leave the view untouched in that case
      if (!box || box.isEmpty()) return false;
    }
    this.isolated = index;
    this.refreshGhosts();
    if (this.selected) {
      this.updateSelectionVisuals(0);
      const b = this.buildings.get(this.selected);
      if (b) this.frameSelected(b, 0.9, this.explode);
    }
    return true;
  }

  /** fade level: 1 = solid, small = ghosted (isolated out), DIM = context */
  private setGhost(mesh: THREE.Mesh, level: number) {
    const mats = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
    const base = mesh.userData.baseMaterialState as
      | {
          transparent: boolean;
          opacity: number;
          depthWrite: boolean;
          wireframe: boolean;
        }[]
      | undefined;
    const faded = level < 1;
    // below this level the part is "isolated out": draw it as drafting lines so
    // fifteen stacked layers stay readable instead of turning into white haze
    const skeleton = level < 0.15;
    mats.forEach((mat, i) => {
      if (!base || !base[i]) return;
      const wire = mat as WireMaterial;
      if (faded) {
        mat.transparent = true;
        wire.wireframe = skeleton;
        mat.opacity = skeleton ? Math.min(base[i].opacity, 0.4) : Math.min(base[i].opacity, level);
        mat.depthWrite = false;
      } else {
        mat.transparent = base[i].transparent;
        mat.opacity = base[i].opacity;
        mat.depthWrite = base[i].depthWrite;
        wire.wireframe = base[i].wireframe;
      }
    });
    mesh.castShadow = level > 0.6;
    mesh.userData.ghosted = faded;
  }

  /**
   * Recompute per-part opacity: the isolated layer stays solid, parts of the
   * selected building stay solid, and while it is exploded the rest of the
   * palace fades back so the stack reads against a quiet context.
   */
  private refreshGhosts() {
    const isolate = this.isolated;
    const dim = this.selected !== null && this.explode > 0.18;
    this.dimmed = dim;
    for (const [id, b] of this.buildings) {
      b.layers.forEach((layer, i) => {
        if (!layer) return;
        const isolatedOut = isolate !== null && i !== isolate;
        const contextOut = dim && id !== this.selected;
        const level = isolatedOut
          ? PalaceViewer.ISOLATED_GHOST
          : contextOut
            ? PalaceViewer.DIM_OPACITY
            : 1;
        layer.traverse((obj) => {
          const mesh = obj as THREE.Mesh;
          if (!mesh.isMesh) return;
          this.setGhost(mesh, level);
        });
      });
    }
  }

  /* ---------------------------------------------------------------- */
  /* selection                                                        */
  /* ---------------------------------------------------------------- */

  select(id: string | null, focus = false) {
    // an isolated part only makes sense within the building it belongs to
    if (this.selected !== id) this.isolated = null;
    this.selected = id;
    this.refreshGhosts();
    if (!id) {
      this.boxHelper.visible = false;
      this.selectFoot.visible = false;
      if (focus) {
        this.flyTo(OVERVIEW.position, OVERVIEW.target, 1.8, OVERVIEW.fov);
      }
      return;
    }
    const b = this.buildings.get(id);
    if (!b) return;
    this.boxHelper.visible = true;
    this.selectFoot.visible = true;
    this.selectFoot.position.set(b.center.x, 0.45, b.center.z);
    this.selectFoot.scale.set(b.width * 1.5, 1, b.depth * 1.75);
    this.updateSelectionVisuals(0);
    if (focus) this.focusBuilding(id);
  }

  getSelected() {
    return this.selected;
  }

  private updateSelectionVisuals(time: number) {
    const b = this.selected ? this.buildings.get(this.selected) : null;
    if (!b) return;
    this.selectedBox.setFromObject(b.root);
    const mat = this.boxHelper.material as THREE.LineBasicMaterial;
    mat.opacity = 0.5 + 0.22 * Math.sin(time * 2.1);
  }

  focusBuilding(id: string, duration = 1.7) {
    const b = this.buildings.get(id);
    if (!b) return;
    this.userAdjusted = false;
    this.frameSelected(b, duration);
  }

  /** frame the selected hall for the current explode amount */
  private frameSelected(b: BuildingNode, duration: number, e = this.explode) {
    // Always frame the whole stack, even while one member is isolated: the
    // highlighted member then keeps its place in the structure instead of the
    // camera diving at a flat ring of purlins from an arbitrary angle.
    const box = this.explodedBox(b, e);
    const size = box.getSize(new THREE.Vector3());
    // a tall exploded stack reads better from a lower, more side-on angle:
    // the parts then rise against the sky instead of the halls behind.
    const tall = size.y > b.height * 1.45;
    const { pos, target } = this.frameBox(
      box,
      new THREE.Vector3(0.4, tall ? 0.3 : 0.5, 1).normalize(),
      tall ? 1.16 : 1.06,
    );
    this.flyTo(pos.toArray(), target.toArray(), duration);
  }

  /** world bounds of a building with its layers lifted by `e` */
  private explodedBox(b: BuildingNode, e: number) {
    const box = new THREE.Box3();
    b.layerBoxes.forEach((lb, i) => {
      if (lb.isEmpty()) return;
      const shifted = lb.clone();
      const lift = (b.lifts[i] ?? 0) * e;
      shifted.min.y += lift;
      shifted.max.y += lift;
      box.union(shifted);
    });
    return box;
  }

  /** camera placement that fits a world-space box without cropping it */
  private frameBox(box: THREE.Box3, dir: THREE.Vector3, margin = 1.06) {
    const center = box.getCenter(new THREE.Vector3());
    const f = dir.clone().negate();
    const right = new THREE.Vector3()
      .crossVectors(f, new THREE.Vector3(0, 1, 0))
      .normalize();
    const up = new THREE.Vector3().crossVectors(right, f).normalize();
    const tanV =
      Math.tan(THREE.MathUtils.degToRad(this.camera.fov) / 2) *
      (this.camera.aspect < 1 ? 1.3 : 1);
    const tanH = tanV * this.camera.aspect;
    let distance = 12;
    const v = new THREE.Vector3();
    for (let i = 0; i < 8; i++) {
      v.set(
        i & 1 ? box.max.x : box.min.x,
        i & 2 ? box.max.y : box.min.y,
        i & 4 ? box.max.z : box.min.z,
      ).sub(center);
      distance = Math.max(
        distance,
        v.dot(dir) +
          Math.max(Math.abs(v.dot(right)) / tanH, Math.abs(v.dot(up)) / tanV),
      );
    }
    distance *= margin;
    // nudge the subject right of screen centre so the side panel doesn't cover it
    const target = center
      .clone()
      .addScaledVector(right, -0.075 * distance * tanH);
    const pos = target.clone().addScaledVector(dir, distance);
    return { pos, target };
  }

  /* ---------------------------------------------------------------- */
  /* camera                                                           */
  /* ---------------------------------------------------------------- */

  applyCamera(preset: CameraPreset) {
    this.flyTo(preset.position, preset.target, 1.6, preset.fov);
  }

  flyTo(
    position: [number, number, number] | number[],
    target: [number, number, number] | number[],
    duration = 1.5,
    fov?: number,
  ) {
    this.tween = {
      fromPos: this.camera.position.clone(),
      toPos: new THREE.Vector3(position[0], position[1], position[2]),
      fromTarget: this.controls.target.clone(),
      toTarget: new THREE.Vector3(target[0], target[1], target[2]),
      fromFov: this.camera.fov,
      toFov: fov ?? DEFAULT_FOV,
      start: performance.now(),
      duration,
    };
    this.controls.enabled = false;
  }

  /* ---------------------------------------------------------------- */
  /* labels                                                           */
  /* ---------------------------------------------------------------- */

  setShowLabels(value: boolean) {
    this.labelsEnabled = value;
    if (!value) this.cb.onLabels?.([]);
  }

  private updateLabels() {
    if (!this.cb.onLabels || !this.labelsEnabled) return;
    const w = this.canvas.clientWidth;
    const h = this.canvas.clientHeight;
    const out: LabelPosition[] = [];
    for (const b of this.buildings.values()) {
      if (this.dimmed && b.id !== this.selected) continue;
      const p = new THREE.Vector3(
        b.center.x,
        b.height * 1.02 + 3,
        b.center.z,
      ).project(this.camera);
      if (p.z > 1) continue;
      if (p.x < -1.15 || p.x > 1.15 || p.y < -1.15 || p.y > 1.15) continue;
      out.push({
        id: b.id,
        x: (p.x * 0.5 + 0.5) * w,
        y: (-p.y * 0.5 + 0.5) * h,
        visible: true,
        depth: p.z,
      });
    }
    out.sort((a, b) => a.depth - b.depth);
    if (this.selected) {
      const i = out.findIndex((l) => l.id === this.selected);
      if (i > 0) out.unshift(out.splice(i, 1)[0]);
    }
    // greedy declutter: drop labels that would collide on screen
    const kept: LabelPosition[] = [];
    for (const label of out) {
      const y = label.y - 11;
      const clash = kept.some(
        (k) => Math.abs(k.x - label.x) < 78 && Math.abs(k.y - 11 - y) < 24,
      );
      if (!clash) kept.push(label);
    }
    this.cb.onLabels(kept);
  }

  /* ---------------------------------------------------------------- */
  /* events                                                           */
  /* ---------------------------------------------------------------- */

  private onResize = () => {
    this.resize();
  };

  private resize() {
    const w = this.canvas.clientWidth || window.innerWidth;
    const h = this.canvas.clientHeight || window.innerHeight;
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
  }

  private bindEvents() {
    this.controls.addEventListener("start", () => {
      this.userAdjusted = true;
    });
    window.addEventListener("resize", this.onResize);
    this.canvas.addEventListener("pointermove", this.onPointerMove);
    this.canvas.addEventListener("pointerdown", this.onPointerDown);
    this.canvas.addEventListener("pointerup", this.onPointerUp);
    this.canvas.addEventListener("pointerleave", this.onPointerLeave);
  }

  private setPointer(event: PointerEvent) {
    const rect = this.canvas.getBoundingClientRect();
    this.pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
    this.pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
  }

  private pick(): string | null {
    this.raycaster.setFromCamera(this.pointer, this.camera);
    const hits = this.raycaster.intersectObjects(this.pickMeshes, false);
    for (const hit of hits) {
      const id = hit.object.userData.buildingId as string | undefined;
      if (id) return id;
    }
    return null;
  }

  private onPointerMove = (event: PointerEvent) => {
    this.setPointer(event);
    const now = performance.now();
    if (now - this.lastHoverTest < 45) return;
    this.lastHoverTest = now;
    if (this.tween) return;
    const id = this.pick();
    if (id !== this.hovered) {
      this.hovered = id;
      this.canvas.style.cursor = id ? "pointer" : "grab";
      if (id) {
        const b = this.buildings.get(id);
        if (b) {
          this.hoverFoot.position.set(b.center.x, 0.4, b.center.z);
          this.hoverFoot.scale.set(b.width * 1.35, 1, b.depth * 1.5);
          this.hoverFoot.visible = id !== this.selected;
        }
      } else {
        this.hoverFoot.visible = false;
      }
      this.cb.onHover?.(id);
    }
  };

  private onPointerDown = (event: PointerEvent) => {
    this.pointerDown = { x: event.clientX, y: event.clientY, t: performance.now() };
  };

  private onPointerUp = (event: PointerEvent) => {
    const dx = event.clientX - this.pointerDown.x;
    const dy = event.clientY - this.pointerDown.y;
    const dist = Math.hypot(dx, dy);
    if (dist > 6 || performance.now() - this.pointerDown.t > 700) return;
    this.setPointer(event);
    const id = this.pick();
    this.cb.onSelect?.(id);
  };

  private onPointerLeave = () => {
    if (this.hovered !== null) {
      this.hovered = null;
      this.hoverFoot.visible = false;
      this.canvas.style.cursor = "grab";
      this.cb.onHover?.(null);
    }
  };

  /* ---------------------------------------------------------------- */
  /* loop                                                             */
  /* ---------------------------------------------------------------- */

  private tick = () => {
    if (this.disposed) return;
    this.raf = requestAnimationFrame(this.tick);
    const now = performance.now();
    const dt = Math.min((now - this.lastFrame) / 1000, 0.06);
    this.lastFrame = now;
    this.elapsed += dt;
    const time = this.elapsed;

    if (this.timeT < 1) {
      this.timeT = Math.min(
        1,
        (now - this.timeStart) / 1000 / this.timeDuration,
      );
      const k = easeInOut(this.timeT);
      lerpState(this.timeFrom, this.timeTo, k, this.current);
      this.applyTime();
      if (this.timeT >= 1) {
        this.current = cloneState(TIME_STATES[this.timeKey]);
        this.applyTime();
        this.bakeEnvironment();
      }
    }

    if (Math.abs(this.explodeTarget - this.explode) > 0.0004) {
      this.explode += (this.explodeTarget - this.explode) * (1 - Math.exp(-9 * dt));
      this.applyExplode();
    } else if (this.explode !== this.explodeTarget) {
      this.explode = this.explodeTarget;
      this.applyExplode(true);
    }

    if (this.tween) {
      const progress = Math.min(
        1,
        (now - this.tween.start) / 1000 / this.tween.duration,
      );
      const k = easeInOut(progress);
      this.camera.position.lerpVectors(this.tween.fromPos, this.tween.toPos, k);
      this.controls.target.lerpVectors(
        this.tween.fromTarget,
        this.tween.toTarget,
        k,
      );
      const fov = THREE.MathUtils.lerp(this.tween.fromFov, this.tween.toFov, k);
      if (Math.abs(fov - this.camera.fov) > 0.001) {
        this.camera.fov = fov;
        this.camera.updateProjectionMatrix();
      }
      if (progress >= 1) {
        this.tween = null;
        this.controls.enabled = true;
      }
    }

    this.controls.update();

    this.sky.follow(this.camera);
    this.nightSky.apply(this.current, this.camera);
    this.petals.update(dt, time, this.current.night);

    if (this.waterMaterial) {
      const map = this.waterMaterial.normalMap;
      if (map) {
        map.offset.x += dt * 0.006;
        map.offset.y += dt * 0.004;
      }
    }

    if (this.selected) this.updateSelectionVisuals(time);
    if (this.hoverFoot.visible) {
      (this.hoverFoot.material as THREE.MeshBasicMaterial).opacity =
        0.22 + 0.1 * Math.sin(time * 2.4);
    }
    if (this.selectFoot.visible) {
      (this.selectFoot.material as THREE.MeshBasicMaterial).opacity =
        0.72 + 0.16 * Math.sin(time * 2.1);
    }

    this.renderer.render(this.scene, this.camera);

    this.labelClock += dt;
    if (this.labelClock > 0.06) {
      this.labelClock = 0;
      this.updateLabels();
    }

    if (this.ready) {
      this.ready = false;
      this.cb.onReady?.();
    }
  };

  /* ---------------------------------------------------------------- */
  /* teardown                                                         */
  /* ---------------------------------------------------------------- */

  dispose() {
    this.disposed = true;
    cancelAnimationFrame(this.raf);
    window.removeEventListener("resize", this.onResize);
    this.canvas.removeEventListener("pointermove", this.onPointerMove);
    this.canvas.removeEventListener("pointerdown", this.onPointerDown);
    this.canvas.removeEventListener("pointerup", this.onPointerUp);
    this.canvas.removeEventListener("pointerleave", this.onPointerLeave);
    this.controls.dispose();
    this.sky.dispose();
    this.nightSky.dispose();
    this.mountains.dispose();
    this.groundSkirt.dispose();
    this.petals.dispose();
    this.envTarget?.dispose();
    this.pmrem.dispose();
    this.scene.traverse((obj) => {
      const mesh = obj as THREE.Mesh;
      if (!mesh.isMesh) return;
      mesh.geometry?.dispose();
      const mats = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
      for (const m of mats) {
        (m as THREE.MeshStandardMaterial).dispose?.();
      }
    });
    this.renderer.dispose();
  }
}
