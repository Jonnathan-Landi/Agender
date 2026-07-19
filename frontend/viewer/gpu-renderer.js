const CACHE_KEY = "agender.viewer.graphics-capabilities.v1";
const CACHE_MAX_AGE_MS = 30 * 24 * 60 * 60 * 1000;

const SHADER = `
struct VertexOut {
  @builtin(position) position: vec4f,
  @location(0) local: vec2f,
  @location(1) color: vec4f,
}

struct Viewport {
  size: vec2f,
  point_size: f32,
  _padding: f32,
}

@group(0) @binding(0) var<uniform> viewport: Viewport;

@vertex
fn vertex_main(
  @builtin(vertex_index) vertex_index: u32,
  @location(0) center: vec2f,
  @location(1) color: vec4f,
) -> VertexOut {
  var corners = array<vec2f, 6>(
    vec2f(-1.0, -1.0), vec2f(1.0, -1.0), vec2f(-1.0, 1.0),
    vec2f(-1.0, 1.0), vec2f(1.0, -1.0), vec2f(1.0, 1.0),
  );
  let corner = corners[vertex_index];
  let offset = corner * vec2f(
    viewport.point_size * 2.0 / viewport.size.x,
    viewport.point_size * 2.0 / viewport.size.y,
  );
  var output: VertexOut;
  output.position = vec4f(center + offset, 0.0, 1.0);
  output.local = corner;
  output.color = color;
  return output;
}

@fragment
fn fragment_main(input: VertexOut) -> @location(0) vec4f {
  if (dot(input.local, input.local) > 1.0) {
    discard;
  }
  return input.color;
}
`;

function readCachedCapabilities() {
  try {
    const cached = JSON.parse(localStorage.getItem(CACHE_KEY) || "null");
    if (!cached || Date.now() - cached.checkedAt > CACHE_MAX_AGE_MS) return null;
    return cached;
  } catch {
    return null;
  }
}

function writeCachedCapabilities(capabilities) {
  try {
    localStorage.setItem(CACHE_KEY, JSON.stringify({ ...capabilities, checkedAt: Date.now() }));
  } catch {
    // Capability caching is an optimization; rendering must work without it.
  }
}

function withTimeout(promise, timeoutMs = 2500) {
  return Promise.race([
    promise,
    new Promise((_, reject) => {
      setTimeout(() => reject(new Error("Graphics capability check timed out")), timeoutMs);
    }),
  ]);
}

function parseColor(color, opacity = 0.82) {
  const value = String(color || "#0067c0").trim();
  const hex = value.match(/^#([\da-f]{6})$/i);
  if (hex) {
    const number = Number.parseInt(hex[1], 16);
    return [
      ((number >> 16) & 255) / 255,
      ((number >> 8) & 255) / 255,
      (number & 255) / 255,
      opacity,
    ];
  }
  return [0, 0.404, 0.753, opacity];
}

function supportsWebGLContext() {
  const canvas = document.createElement("canvas");
  try {
    const context = canvas.getContext("webgl2")
      || canvas.getContext("webgl")
      || canvas.getContext("experimental-webgl");
    return Boolean(context && !context.isContextLost());
  } catch {
    return false;
  }
}

export class AdaptiveGpuRenderer {
  constructor(chart, onWebGpuFailure) {
    this.chart = chart;
    this.onWebGpuFailure = onWebGpuFailure;
    this.engine = "svg";
    this.device = null;
    this.context = null;
    this.canvas = null;
    this.pipeline = null;
    this.bindGroup = null;
    this.uniformBuffer = null;
    this.vertexBuffer = null;
    this.vertexCapacity = 0;
    this.pointCount = 0;
    this.traces = [];
    this.failed = false;
    this.resizeObserver = new ResizeObserver(() => this.redraw());
  }

  async detect() {
    const cached = readCachedCapabilities();
    const webgl = supportsWebGLContext();
    if (!navigator.gpu) {
      this.engine = webgl ? "webgl" : "svg";
      writeCachedCapabilities({ webgpu: false, webgl, engine: this.engine });
      return { engine: this.engine, cached };
    }

    try {
      const adapter = await withTimeout(
        navigator.gpu.requestAdapter({ powerPreference: "high-performance" }),
      );
      if (!adapter) throw new Error("No WebGPU adapter");
      const device = await withTimeout(adapter.requestDevice());
      await this.initializeWebGpu(device);
      this.engine = "webgpu";
      writeCachedCapabilities({ webgpu: true, webgl, engine: this.engine });
    } catch {
      this.disposeWebGpu();
      this.engine = webgl ? "webgl" : "svg";
      writeCachedCapabilities({ webgpu: false, webgl, engine: this.engine });
    }
    return { engine: this.engine, cached };
  }

  async initializeWebGpu(device) {
    this.device = device;
    this.canvas = document.createElement("canvas");
    this.canvas.className = "webgpu-series-layer";
    this.canvas.setAttribute("aria-hidden", "true");
    this.context = this.canvas.getContext("webgpu");
    if (!this.context) throw new Error("WebGPU canvas context unavailable");

    const format = navigator.gpu.getPreferredCanvasFormat();
    this.context.configure({ device, format, alphaMode: "premultiplied" });
    device.pushErrorScope("validation");
    const module = device.createShaderModule({ code: SHADER });
    this.uniformBuffer = device.createBuffer({
      size: 16,
      usage: GPUBufferUsage.UNIFORM | GPUBufferUsage.COPY_DST,
    });
    const bindGroupLayout = device.createBindGroupLayout({
      entries: [{
        binding: 0,
        visibility: GPUShaderStage.VERTEX,
        buffer: { type: "uniform" },
      }],
    });
    this.bindGroup = device.createBindGroup({
      layout: bindGroupLayout,
      entries: [{ binding: 0, resource: { buffer: this.uniformBuffer } }],
    });
    this.pipeline = device.createRenderPipeline({
      layout: device.createPipelineLayout({ bindGroupLayouts: [bindGroupLayout] }),
      vertex: {
        module,
        entryPoint: "vertex_main",
        buffers: [{
          arrayStride: 24,
          stepMode: "instance",
          attributes: [
            { shaderLocation: 0, offset: 0, format: "float32x2" },
            { shaderLocation: 1, offset: 8, format: "float32x4" },
          ],
        }],
      },
      fragment: {
        module,
        entryPoint: "fragment_main",
        targets: [{
          format,
          blend: {
            color: { srcFactor: "src-alpha", dstFactor: "one-minus-src-alpha", operation: "add" },
            alpha: { srcFactor: "one", dstFactor: "one-minus-src-alpha", operation: "add" },
          },
        }],
      },
      primitive: { topology: "triangle-list" },
    });
    const validationError = await device.popErrorScope();
    if (validationError) throw new Error(validationError.message);

    device.lost.then(() => this.failWebGpu());
    this.resizeObserver.observe(this.chart);
  }

  attachCanvas() {
    if (!this.canvas || this.canvas.parentElement === this.chart) return;
    this.chart.appendChild(this.canvas);
  }

  render(traces) {
    if (this.engine !== "webgpu") return;
    this.traces = traces;
    this.attachCanvas();
    this.redraw();
  }

  redraw() {
    if (this.engine !== "webgpu" || !this.device || !this.canvas || !this.chart._fullLayout) return;
    try {
      this.attachCanvas();
      const width = Math.max(1, this.chart.clientWidth);
      const height = Math.max(1, this.chart.clientHeight);
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      const pixelWidth = Math.max(1, Math.round(width * ratio));
      const pixelHeight = Math.max(1, Math.round(height * ratio));
      if (this.canvas.width !== pixelWidth || this.canvas.height !== pixelHeight) {
        this.canvas.width = pixelWidth;
        this.canvas.height = pixelHeight;
      }

      const layout = this.chart._fullLayout;
      const plot = layout._size;
      const xaxis = layout.xaxis;
      const yaxis = layout.yaxis;
      const maximumPoints = this.traces.reduce((total, trace) => total + trace.x.length, 0);
      const vertices = new Float32Array(maximumPoints * 6);
      let offset = 0;
      this.traces.forEach((trace) => {
        const color = parseColor(trace.marker?.color, trace.marker?.opacity);
        trace.x.forEach((xValue, index) => {
          const yValue = trace.y[index];
          if (yValue === null || yValue === undefined || !Number.isFinite(Number(yValue))) return;
          const xPixel = plot.l + xaxis.d2p(xValue);
          const yPixel = plot.t + yaxis.d2p(yValue);
          if (
            xPixel < plot.l || xPixel > plot.l + plot.w
            || yPixel < plot.t || yPixel > plot.t + plot.h
          ) return;
          vertices[offset] = xPixel / width * 2 - 1;
          vertices[offset + 1] = 1 - yPixel / height * 2;
          vertices.set(color, offset + 2);
          offset += 6;
        });
      });

      const visibleVertices = vertices.subarray(0, offset);
      this.pointCount = visibleVertices.length / 6;
      if (visibleVertices.byteLength > this.vertexCapacity) {
        this.vertexBuffer?.destroy();
        this.vertexCapacity = Math.max(visibleVertices.byteLength, Math.ceil(this.vertexCapacity * 1.5), 24);
        this.vertexBuffer = this.device.createBuffer({
          size: this.vertexCapacity,
          usage: GPUBufferUsage.VERTEX | GPUBufferUsage.COPY_DST,
        });
      }
      if (visibleVertices.byteLength) this.device.queue.writeBuffer(this.vertexBuffer, 0, visibleVertices);
      this.device.queue.writeBuffer(
        this.uniformBuffer,
        0,
        new Float32Array([pixelWidth, pixelHeight, 2.5 * ratio, 0]),
      );

      const encoder = this.device.createCommandEncoder();
      const pass = encoder.beginRenderPass({
        colorAttachments: [{
          view: this.context.getCurrentTexture().createView(),
          clearValue: { r: 0, g: 0, b: 0, a: 0 },
          loadOp: "clear",
          storeOp: "store",
        }],
      });
      pass.setPipeline(this.pipeline);
      pass.setBindGroup(0, this.bindGroup);
      if (this.pointCount) {
        pass.setVertexBuffer(0, this.vertexBuffer);
        pass.draw(6, this.pointCount);
      }
      pass.end();
      this.device.queue.submit([encoder.finish()]);
    } catch {
      this.failWebGpu();
    }
  }

  failWebGpu() {
    if (this.failed || this.engine !== "webgpu") return;
    this.failed = true;
    this.engine = supportsWebGLContext() ? "webgl" : "svg";
    writeCachedCapabilities({ webgpu: false, webgl: this.engine === "webgl", engine: this.engine });
    this.disposeWebGpu();
    this.onWebGpuFailure?.(this.engine);
  }

  disposeWebGpu() {
    this.resizeObserver.disconnect();
    this.vertexBuffer?.destroy();
    this.uniformBuffer?.destroy();
    this.canvas?.remove();
    this.vertexBuffer = null;
    this.uniformBuffer = null;
    this.canvas = null;
    this.device = null;
  }

  dispose() {
    this.disposeWebGpu();
    this.traces = [];
  }
}
