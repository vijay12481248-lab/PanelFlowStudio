import { G } from "./grade";

// Same shader as ChronoFlow's monitor: the picture is drawn through the baked 3D LUT. The picture is flipped here, not with
// UNPACK_FLIP_Y_WEBGL: WebGL rejects that flag for an ImageBitmap (INVALID_OPERATION), which silently stopped every redraw.
const VS = "#version 300 es\nout vec2 uv; void main(){ vec2 p = vec2(float((gl_VertexID << 1) & 2), float(gl_VertexID & 2)); uv = p; gl_Position = vec4(p * 2.0 - 1.0, 0.0, 1.0); }";
const FS =
  "#version 300 es\nprecision highp float; precision highp sampler3D; in vec2 uv; out vec4 o; uniform sampler2D img; uniform sampler3D lut; uniform float n;\n" +
  "void main(){ vec3 c = clamp(texture(img, vec2(uv.x, 1.0 - uv.y)).rgb, 0.0, 1.0); vec3 p = c * ((n - 1.0) / n) + 0.5 / n; o = vec4(texture(lut, p).rgb, 1.0); }";

class LutRenderer {
  readonly gl: WebGL2RenderingContext;
  private prog: WebGLProgram;
  private imgTex: WebGLTexture;
  private lutTex: WebGLTexture;
  private uN: WebGLUniformLocation | null;
  private lutKey: Float32Array | null = null;

  constructor(canvas: HTMLCanvasElement) {
    const gl = canvas.getContext("webgl2", { alpha: false, antialias: false, preserveDrawingBuffer: true });
    if (!gl) throw new Error("WebGL2 is not available");
    this.gl = gl;
    const shader = (type: number, src: string) => {
      const s = gl.createShader(type)!;
      gl.shaderSource(s, src);
      gl.compileShader(s);
      if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s) || "shader error");
      return s;
    };
    const p = (this.prog = gl.createProgram()!);
    gl.attachShader(p, shader(gl.VERTEX_SHADER, VS));
    gl.attachShader(p, shader(gl.FRAGMENT_SHADER, FS));
    gl.linkProgram(p);
    gl.useProgram(p);
    gl.uniform1i(gl.getUniformLocation(p, "img"), 0);
    gl.uniform1i(gl.getUniformLocation(p, "lut"), 1);
    this.uN = gl.getUniformLocation(p, "n");
    const tex = (unit: number, target: number) => {
      const t = gl.createTexture()!;
      gl.activeTexture(gl.TEXTURE0 + unit);
      gl.bindTexture(target, t);
      gl.texParameteri(target, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
      gl.texParameteri(target, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
      [gl.TEXTURE_WRAP_S, gl.TEXTURE_WRAP_T, gl.TEXTURE_WRAP_R].forEach((w) => gl.texParameteri(target, w, gl.CLAMP_TO_EDGE));
      return t;
    };
    this.imgTex = tex(0, gl.TEXTURE_2D);
    this.lutTex = tex(1, gl.TEXTURE_3D);
  }

  maxTexture(): number {
    return this.gl.getParameter(this.gl.MAX_TEXTURE_SIZE) as number;
  }

  draw(bitmap: ImageBitmap, table: Float32Array, size: number, width: number, height: number) {
    const gl = this.gl;
    const canvas = gl.canvas as HTMLCanvasElement;
    if (canvas.width !== width || canvas.height !== height) {
      canvas.width = width;
      canvas.height = height;
    }
    gl.viewport(0, 0, width, height);
    gl.useProgram(this.prog);
    if (this.lutKey !== table) {
      const rgba = new Float32Array(size * size * size * 4);
      for (let i = 0, j = 0; i < table.length; i += 3, j += 4) {
        rgba[j] = table[i]; rgba[j + 1] = table[i + 1]; rgba[j + 2] = table[i + 2]; rgba[j + 3] = 1;
      }
      gl.activeTexture(gl.TEXTURE1);
      gl.bindTexture(gl.TEXTURE_3D, this.lutTex);
      gl.texImage3D(gl.TEXTURE_3D, 0, gl.RGBA16F, size, size, size, 0, gl.RGBA, gl.FLOAT, rgba);
      gl.uniform1f(this.uN, size);
      this.lutKey = table;
    }
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, this.imgTex);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, bitmap);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
  }
}

const renderers = new WeakMap<HTMLCanvasElement, LutRenderer | null>();

function rendererFor(canvas: HTMLCanvasElement): LutRenderer | null {
  if (!renderers.has(canvas)) {
    try {
      renderers.set(canvas, new LutRenderer(canvas));
    } catch {
      renderers.set(canvas, null); // no WebGL2: the CPU path below is used
    }
  }
  return renderers.get(canvas) ?? null;
}

/** CPU path: same table, same result, slower (about 4 megapixels in a few hundred ms). */
function drawOnCpu(canvas: HTMLCanvasElement, bitmap: ImageBitmap, table: Float32Array, size: number, width: number, height: number) {
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  if (!ctx) throw new Error("Canvas is not available");
  ctx.drawImage(bitmap, 0, 0, width, height);
  const img = ctx.getImageData(0, 0, width, height);
  G.applyToPixels(img.data, table, size);
  ctx.putImageData(img, 0, 0);
}

/** Draw `bitmap` through the baked table onto `canvas`, scaled so its long edge is at most `maxLongEdge`. */
export function drawGraded(canvas: HTMLCanvasElement, bitmap: ImageBitmap, table: Float32Array, size: number, maxLongEdge: number) {
  const scale = Math.min(1, maxLongEdge / Math.max(bitmap.width, bitmap.height));
  const width = Math.max(1, Math.round(bitmap.width * scale)), height = Math.max(1, Math.round(bitmap.height * scale));
  const gl = rendererFor(canvas);
  if (gl && Math.max(width, height) <= gl.maxTexture() && bitmap.width <= gl.maxTexture() && bitmap.height <= gl.maxTexture()) {
    gl.draw(bitmap, table, size, width, height);
  } else {
    drawOnCpu(canvas, bitmap, table, size, width, height);
  }
}

/** The graded picture at full size, encoded in the given format (JPG gets a white background, it has no transparency). */
export async function renderGradedBlob(bitmap: ImageBitmap, table: Float32Array, size: number, mime: string, quality = 0.92): Promise<Blob> {
  const canvas = document.createElement("canvas");
  drawGraded(canvas, bitmap, table, size, Number.MAX_SAFE_INTEGER);
  return new Promise<Blob>((resolve, reject) =>
    canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("Could not encode the graded picture."))), mime, quality),
  );
}
