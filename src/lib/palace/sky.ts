import * as THREE from "three";
import type { TimeKey } from "./types";

export interface TimeState {
  sunDir: THREE.Vector3;
  sunColor: THREE.Color;
  sunIntensity: number;
  skyTop: THREE.Color;
  skyHorizon: THREE.Color;
  skyGround: THREE.Color;
  fog: THREE.Color;
  fogDensity: number;
  hemiSky: THREE.Color;
  hemiGround: THREE.Color;
  hemiIntensity: number;
  ambient: number;
  exposure: number;
  /** 0 = full day, 1 = deep night */
  night: number;
  sunGlow: number;
}

function state(s: {
  sunDir: [number, number, number];
  sunColor: number;
  sunIntensity: number;
  skyTop: number;
  skyHorizon: number;
  skyGround: number;
  fog: number;
  fogDensity: number;
  hemiSky: number;
  hemiGround: number;
  hemiIntensity: number;
  ambient: number;
  exposure: number;
  night: number;
  sunGlow: number;
}): TimeState {
  return {
    sunDir: new THREE.Vector3(...s.sunDir).normalize(),
    sunColor: new THREE.Color(s.sunColor),
    sunIntensity: s.sunIntensity,
    skyTop: new THREE.Color(s.skyTop),
    skyHorizon: new THREE.Color(s.skyHorizon),
    skyGround: new THREE.Color(s.skyGround),
    fog: new THREE.Color(s.fog),
    fogDensity: s.fogDensity,
    hemiSky: new THREE.Color(s.hemiSky),
    hemiGround: new THREE.Color(s.hemiGround),
    hemiIntensity: s.hemiIntensity,
    ambient: s.ambient,
    exposure: s.exposure,
    night: s.night,
    sunGlow: s.sunGlow,
  };
}

export const TIME_STATES: Record<TimeKey, TimeState> = {
  day: state({
    sunDir: [-0.4, 0.74, 0.54],
    sunColor: 0xfff1d8,
    sunIntensity: 2.45,
    skyTop: 0x1f5ea8,
    skyHorizon: 0xc3d7de,
    skyGround: 0xa9b3ac,
    fog: 0xc6cecd,
    fogDensity: 0.00085,
    hemiSky: 0xbdd2e6,
    hemiGround: 0x625f48,
    hemiIntensity: 0.42,
    ambient: 0.07,
    exposure: 1.0,
    night: 0,
    sunGlow: 1,
  }),
  sunset: state({
    sunDir: [-0.74, 0.15, 0.66],
    sunColor: 0xffa464,
    sunIntensity: 2.3,
    skyTop: 0x2c4a75,
    skyHorizon: 0xf3a264,
    skyGround: 0x6b584c,
    fog: 0xb08a70,
    fogDensity: 0.0008,
    hemiSky: 0xffc08e,
    hemiGround: 0x4c3c34,
    hemiIntensity: 0.3,
    ambient: 0.08,
    exposure: 1.06,
    night: 0.18,
    sunGlow: 1.35,
  }),
  night: state({
    sunDir: [0.36, 0.52, -0.78],
    sunColor: 0x9fb7e8,
    sunIntensity: 1.35,
    skyTop: 0x060a14,
    skyHorizon: 0x14203a,
    skyGround: 0x070a10,
    fog: 0x0c1626,
    fogDensity: 0.0016,
    hemiSky: 0x35496b,
    hemiGround: 0x0a0d12,
    hemiIntensity: 0.6,
    ambient: 0.08,
    exposure: 1.22,
    night: 1,
    sunGlow: 0.18,
  }),
};

/* ------------------------------------------------------------------ */
/* sky dome                                                            */
/* ------------------------------------------------------------------ */

const SKY_VERT = /* glsl */ `
  varying vec3 vDir;
  void main() {
    vDir = position;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`;

const SKY_FRAG = /* glsl */ `
  uniform vec3 uTop;
  uniform vec3 uHorizon;
  uniform vec3 uGround;
  uniform vec3 uSunColor;
  uniform vec3 uSunDir;
  uniform float uNight;
  uniform float uGlow;
  varying vec3 vDir;

  void main() {
    vec3 d = normalize(vDir);
    float y = d.y;

    float t = pow(clamp(y, 0.0, 1.0), 0.32);
    vec3 col = mix(uHorizon, uTop, t);

    // below the horizon fades into the fog / ground tone
    col = mix(col, uGround, smoothstep(0.015, -0.16, y));

    float sd = max(dot(d, uSunDir), 0.0);

    // soft halo around the sun
    col += uSunColor * pow(sd, 5.0) * 0.1 * uGlow;
    // disc
    col += uSunColor * pow(sd, 1100.0) * 5.0 * mix(0.25, 1.0, uGlow);
    // warm horizon band on the sun side
    float band = pow(1.0 - abs(y), 7.0) * pow(sd * 0.5 + 0.5, 2.5);
    col += uSunColor * band * 0.12 * uGlow;

    gl_FragColor = vec4(col, 1.0);

    #include <tonemapping_fragment>
    #include <colorspace_fragment>
  }
`;

export class Sky {
  readonly mesh: THREE.Mesh;
  readonly material: THREE.ShaderMaterial;
  private uniformCache: Record<string, THREE.IUniform>;

  constructor() {
    const geo = new THREE.SphereGeometry(2600, 40, 28);
    this.uniformCache = {
      uTop: { value: new THREE.Color(0x4a7fbe) },
      uHorizon: { value: new THREE.Color(0xdfe7e8) },
      uGround: { value: new THREE.Color(0xb6bfb6) },
      uSunColor: { value: new THREE.Color(0xfff1d8) },
      uSunDir: { value: new THREE.Vector3(-0.4, 0.74, 0.54).normalize() },
      uNight: { value: 0 },
      uGlow: { value: 1 },
    };
    this.material = new THREE.ShaderMaterial({
      uniforms: this.uniformCache,
      vertexShader: SKY_VERT,
      fragmentShader: SKY_FRAG,
      side: THREE.BackSide,
      depthWrite: false,
      depthTest: false,
      fog: false,
    });
    this.mesh = new THREE.Mesh(geo, this.material);
    this.mesh.frustumCulled = false;
    this.mesh.renderOrder = -1000;
    this.mesh.name = "sky-dome";
  }

  apply(s: TimeState) {
    const u = this.uniformCache;
    (u.uTop.value as THREE.Color).copy(s.skyTop);
    (u.uHorizon.value as THREE.Color).copy(s.skyHorizon);
    (u.uGround.value as THREE.Color).copy(s.skyGround);
    (u.uSunColor.value as THREE.Color).copy(s.sunColor);
    (u.uSunDir.value as THREE.Vector3).copy(s.sunDir);
    u.uNight.value = s.night;
    u.uGlow.value = s.sunGlow;
  }

  follow(camera: THREE.Camera) {
    this.mesh.position.copy(camera.position);
  }

  dispose() {
    this.mesh.geometry.dispose();
    this.material.dispose();
  }
}

/* ------------------------------------------------------------------ */
/* stars + moon                                                        */
/* ------------------------------------------------------------------ */

function radialTexture(
  size: number,
  stops: [number, string][],
  core?: { r: number; color: string },
) {
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = size;
  const ctx = canvas.getContext("2d")!;
  const g = ctx.createRadialGradient(
    size / 2,
    size / 2,
    0,
    size / 2,
    size / 2,
    size / 2,
  );
  for (const [o, c] of stops) g.addColorStop(o, c);
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, size, size);
  if (core) {
    ctx.beginPath();
    ctx.arc(size / 2, size / 2, core.r * size, 0, Math.PI * 2);
    ctx.fillStyle = core.color;
    ctx.fill();
  }
  const tex = new THREE.CanvasTexture(canvas);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

export class NightSky {
  readonly group = new THREE.Group();
  readonly stars: THREE.Points;
  readonly moon: THREE.Sprite;
  private starMat: THREE.PointsMaterial;
  private moonMat: THREE.SpriteMaterial;

  constructor() {
    const count = 1500;
    const positions = new Float32Array(count * 3);
    const sizes = new Float32Array(count);
    for (let i = 0; i < count; i++) {
      // bias toward the upper hemisphere
      const u = Math.random();
      const v = Math.random() * 0.94 + 0.02;
      const theta = Math.PI * 2 * u;
      const y = Math.pow(v, 0.7);
      const r = Math.sqrt(1 - y * y);
      const radius = 2200;
      positions[i * 3] = Math.cos(theta) * r * radius;
      positions[i * 3 + 1] = y * radius;
      positions[i * 3 + 2] = Math.sin(theta) * r * radius;
      sizes[i] = 0.6 + Math.random() * 1.6;
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    geo.setAttribute("aSize", new THREE.BufferAttribute(sizes, 1));

    this.starMat = new THREE.PointsMaterial({
      size: 2.4,
      sizeAttenuation: false,
      map: radialTexture(64, [
        [0, "rgba(255,255,255,1)"],
        [0.35, "rgba(220,232,255,0.55)"],
        [1, "rgba(180,200,255,0)"],
      ]),
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      fog: false,
      opacity: 0,
      color: 0xdfe8ff,
    });
    this.stars = new THREE.Points(geo, this.starMat);
    this.stars.frustumCulled = false;
    this.stars.renderOrder = -900;

    this.moonMat = new THREE.SpriteMaterial({
      map: radialTexture(
        256,
        [
          [0, "rgba(255,252,240,1)"],
          [0.16, "rgba(255,250,232,0.95)"],
          [0.22, "rgba(220,230,255,0.28)"],
          [0.55, "rgba(180,200,255,0.06)"],
          [1, "rgba(160,190,255,0)"],
        ],
        { r: 0.13, color: "rgba(255,253,244,0.95)" },
      ),
      transparent: true,
      depthWrite: false,
      depthTest: false,
      blending: THREE.AdditiveBlending,
      fog: false,
      opacity: 0,
    });
    this.moon = new THREE.Sprite(this.moonMat);
    this.moon.scale.setScalar(210);
    this.moon.renderOrder = -880;

    this.group.add(this.stars, this.moon);
    this.group.frustumCulled = false;
  }

  apply(s: TimeState, camera: THREE.Camera) {
    this.starMat.opacity = Math.max(0, s.night - 0.15) * 1.05;
    this.moonMat.opacity = Math.max(0, s.night - 0.35) * 1.5;
    this.group.position.copy(camera.position);
    this.moon.position.copy(s.sunDir).multiplyScalar(2000);
  }

  dispose() {
    this.stars.geometry.dispose();
    this.starMat.map?.dispose();
    this.starMat.dispose();
    this.moonMat.map?.dispose();
    this.moonMat.dispose();
  }
}
