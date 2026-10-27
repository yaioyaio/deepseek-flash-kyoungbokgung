import * as THREE from "three";

/* ------------------------------------------------------------------ */
/* distant mountain rings                                              */
/* ------------------------------------------------------------------ */

const RIDGE_VERT = /* glsl */ `
  varying float vH;
  void main() {
    vH = uv.y;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`;

const RIDGE_FRAG = /* glsl */ `
  uniform vec3 uRock;
  uniform vec3 uHaze;
  varying float vH;
  void main() {
    float k = smoothstep(0.0, 0.78, vH);
    vec3 col = mix(uHaze, uRock, k);
    gl_FragColor = vec4(col, 1.0);
    #include <tonemapping_fragment>
    #include <colorspace_fragment>
  }
`;

function ridgeGeometry(radius: number, base: number, amp: number, seed: number) {
  const N = 320;
  const pos: number[] = [];
  const uv: number[] = [];
  const idx: number[] = [];

  const heightAt = (a: number) => {
    let h = 0.45;
    h += 0.3 * Math.sin(a * 3.1 + seed);
    h += 0.16 * Math.sin(a * 7.7 + seed * 2.3);
    h += 0.09 * Math.sin(a * 15.3 + seed * 4.1);
    h += 0.05 * Math.sin(a * 29.0 + seed * 1.7);
    h = Math.pow(Math.max(0.08, h), 1.45);
    // Bugaksan rises behind the palace (north = -z => a = PI)
    const d = Math.atan2(Math.sin(a - Math.PI), Math.cos(a - Math.PI));
    const boost = 0.9 * Math.exp(-Math.pow(d / 0.7, 2));
    return base + amp * (h + boost);
  };

  for (let i = 0; i <= N; i++) {
    const a = (i / N) * Math.PI * 2;
    const x = Math.sin(a) * radius;
    const z = Math.cos(a) * radius;
    const h = heightAt(a);
    pos.push(x, -90, z);
    pos.push(x, h, z);
    uv.push(i / N, 0);
    uv.push(i / N, 1);
  }
  for (let i = 0; i < N; i++) {
    const b0 = i * 2;
    const t0 = i * 2 + 1;
    const b1 = (i + 1) * 2;
    const t1 = (i + 1) * 2 + 1;
    idx.push(b0, b1, t1, b0, t1, t0);
  }

  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  geo.setAttribute("uv", new THREE.Float32BufferAttribute(uv, 2));
  geo.setIndex(idx);
  geo.computeBoundingSphere();
  return geo;
}

export class Mountains {
  readonly group = new THREE.Group();
  private rings: {
    mesh: THREE.Mesh;
    mat: THREE.ShaderMaterial;
    mix: number;
  }[];

  constructor() {
    const specs: [number, number, number, number, number][] = [
      // radius, base height, amplitude, seed, fog mix
      [900, 24, 44, 1.3, 0.55],
      [1180, 42, 66, 4.7, 0.7],
      [1560, 64, 96, 8.1, 0.84],
    ];
    this.rings = specs.map(([radius, base, amp, seed, mix], i) => {
      const mat = new THREE.ShaderMaterial({
        uniforms: {
          uRock: { value: new THREE.Color(0x4c5d68) },
          uHaze: { value: new THREE.Color(0xc4cccd) },
        },
        vertexShader: RIDGE_VERT,
        fragmentShader: RIDGE_FRAG,
        side: THREE.DoubleSide,
        fog: false,
        depthWrite: true,
      });
      const mesh = new THREE.Mesh(ridgeGeometry(radius, base, amp, seed), mat);
      mesh.renderOrder = -800 + i;
      mesh.name = `ridge-${i}`;
      this.group.add(mesh);
      return { mesh, mat, mix };
    });
  }

  apply(fog: THREE.Color, night: number) {
    const rock = new THREE.Color(0x465a68).multiplyScalar(1 - night * 0.86);
    for (const { mat, mix } of this.rings) {
      const rockU = mat.uniforms.uRock.value as THREE.Color;
      const hazeU = mat.uniforms.uHaze.value as THREE.Color;
      rockU.copy(rock);
      hazeU.copy(fog).lerp(rock, 1 - mix);
    }
  }

  dispose() {
    for (const { mesh, mat } of this.rings) {
      mesh.geometry.dispose();
      mat.dispose();
    }
  }
}

/* ------------------------------------------------------------------ */
/* drifting petals                                                     */
/* ------------------------------------------------------------------ */

function petalTexture() {
  const s = 64;
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = s;
  const ctx = canvas.getContext("2d")!;
  ctx.translate(s / 2, s / 2);
  ctx.rotate(-0.45);
  const g = ctx.createLinearGradient(0, -16, 0, 16);
  g.addColorStop(0, "rgba(255,244,246,0.98)");
  g.addColorStop(0.55, "rgba(255,214,224,0.9)");
  g.addColorStop(1, "rgba(246,178,196,0.6)");
  ctx.fillStyle = g;
  ctx.beginPath();
  ctx.ellipse(0, 0, 9, 17, 0, 0, Math.PI * 2);
  ctx.fill();
  const tex = new THREE.CanvasTexture(canvas);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

export class Petals {
  readonly points: THREE.Points;
  private mat: THREE.PointsMaterial;
  private positions: Float32Array;
  private speed: Float32Array;
  private phase: Float32Array;
  private count: number;
  private bounds = { x: 210, y: 62, z: 230 };
  private baseOpacity = 0.85;

  constructor(count = 420) {
    this.count = count;
    this.positions = new Float32Array(count * 3);
    this.speed = new Float32Array(count);
    this.phase = new Float32Array(count);
    for (let i = 0; i < count; i++) {
      this.positions[i * 3] = (Math.random() * 2 - 1) * this.bounds.x;
      this.positions[i * 3 + 1] = Math.random() * this.bounds.y;
      this.positions[i * 3 + 2] = (Math.random() * 2 - 1) * this.bounds.z - 10;
      this.speed[i] = 0.8 + Math.random() * 1.6;
      this.phase[i] = Math.random() * Math.PI * 2;
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(this.positions, 3));

    this.mat = new THREE.PointsMaterial({
      size: 0.62,
      map: petalTexture(),
      transparent: true,
      depthWrite: false,
      opacity: this.baseOpacity,
      color: 0xffe6ec,
      alphaTest: 0.02,
      sizeAttenuation: true,
      fog: false,
    });
    this.points = new THREE.Points(geo, this.mat);
    this.points.frustumCulled = false;
    this.points.name = "petals";
  }

  update(dt: number, time: number, night: number) {
    const p = this.positions;
    const { x, y, z } = this.bounds;
    for (let i = 0; i < this.count; i++) {
      const k = i * 3;
      p[k + 1] -= this.speed[i] * dt;
      p[k] += Math.sin(time * 0.55 + this.phase[i]) * 0.55 * dt + 0.25 * dt;
      p[k + 2] += Math.cos(time * 0.42 + this.phase[i]) * 0.5 * dt;
      if (p[k + 1] < -1) {
        p[k + 1] = y;
        p[k] = (Math.random() * 2 - 1) * x;
        p[k + 2] = (Math.random() * 2 - 1) * z - 10;
      }
      if (p[k] > x) p[k] = -x;
      if (p[k + 2] > z) p[k + 2] = -z;
      if (p[k + 2] < -z) p[k + 2] = z;
    }
    (this.points.geometry.getAttribute("position") as THREE.BufferAttribute).needsUpdate =
      true;
    this.mat.opacity = this.baseOpacity * (1 - night * 0.75);
  }

  dispose() {
    this.points.geometry.dispose();
    this.mat.map?.dispose();
    this.mat.dispose();
  }
}

/* ------------------------------------------------------------------ */
/* water                                                               */
/* ------------------------------------------------------------------ */

export function createWaterMaterial(normalMap: THREE.Texture) {
  const map = normalMap.clone();
  map.wrapS = map.wrapT = THREE.RepeatWrapping;
  map.repeat.set(10, 10);
  map.needsUpdate = true;

  return new THREE.MeshStandardMaterial({
    color: 0x17383e,
    roughness: 0.07,
    metalness: 0.32,
    normalMap: map,
    normalScale: new THREE.Vector2(0.42, 0.42),
    transparent: true,
    opacity: 0.93,
    envMapIntensity: 1.7,
  });
}

export class GroundSkirt {
  readonly mesh: THREE.Mesh;
  private mat: THREE.MeshStandardMaterial;

  constructor() {
    this.mat = new THREE.MeshStandardMaterial({
      color: 0x7d8463,
      roughness: 1,
      metalness: 0,
    });
    const geo = new THREE.CircleGeometry(4200, 96);
    geo.rotateX(-Math.PI / 2);
    this.mesh = new THREE.Mesh(geo, this.mat);
    this.mesh.position.y = -0.45;
    this.mesh.renderOrder = -850;
    this.mesh.name = "ground-skirt";
  }

  /** borrow the terrain texture from the loaded palace so the fields match */
  setMap(map: THREE.Texture | null) {
    if (!map) return;
    const tex = map.clone();
    tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
    // match the terrain tiling of the palace ground plane (7 m per tile)
    tex.repeat.set(1200, 1200);
    tex.anisotropy = 8;
    tex.needsUpdate = true;
    this.mat.map = tex;
    this.mat.color.setHex(0xffffff);
    this.mat.needsUpdate = true;
  }

  apply(fog: THREE.Color, night: number) {
    // the skirt relies on scene fog; only the albedo is dimmed at night
    this.mat.color.setHex(0xffffff).multiplyScalar(1 - night * 0.55);
    void fog;
  }

  dispose() {
    this.mesh.geometry.dispose();
    this.mat.map?.dispose();
    this.mat.dispose();
  }
}
