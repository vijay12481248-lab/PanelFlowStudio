/* ChronoFlow Fusion Node Graph Model & Renderer.
   Represents a node-based compositing & VFX pipeline for DaVinci Resolve-style Fusion workflow.
   Supports node topological evaluation, 2D/WebGL rendering, preset templates, and FFmpeg filtergraph translation. */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    root.NLEFusionGraph = factory();
  }
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));

  const NODE_DEFS = {
    mediain: {
      type: 'mediain',
      name: 'MediaIn',
      category: 'io',
      icon: '📥',
      inputs: [],
      outputs: ['output'],
      defaultParams: () => ({ enabled: true }),
    },
    mediaout: {
      type: 'mediaout',
      name: 'MediaOut',
      category: 'io',
      icon: '📤',
      inputs: ['input'],
      outputs: [],
      defaultParams: () => ({ enabled: true }),
    },
    transform: {
      type: 'transform',
      name: 'Transform',
      category: 'transform',
      icon: '📐',
      inputs: ['input', 'mask'],
      outputs: ['output'],
      defaultParams: () => ({
        enabled: true,
        posX: 0,
        posY: 0,
        scale: 1.0,
        rotation: 0,
        pivotX: 0.5,
        pivotY: 0.5,
        flipH: false,
        flipV: false,
      }),
    },
    rectangle_mask: {
      type: 'rectangle_mask',
      name: 'RectangleMask',
      category: 'mask',
      icon: '🔲',
      inputs: [],
      outputs: ['mask'],
      defaultParams: () => ({
        enabled: true,
        x: 0.5,
        y: 0.5,
        width: 0.5,
        height: 0.4,
        cornerRadius: 0.05,
        feather: 0.08,
        invert: false,
      }),
    },
    ellipse_mask: {
      type: 'ellipse_mask',
      name: 'EllipseMask',
      category: 'mask',
      icon: '⭕',
      inputs: [],
      outputs: ['mask'],
      defaultParams: () => ({
        enabled: true,
        x: 0.5,
        y: 0.5,
        width: 0.45,
        height: 0.45,
        feather: 0.1,
        invert: false,
      }),
    },
    text_plus: {
      type: 'text_plus',
      name: 'Text+',
      category: 'generator',
      icon: '🔤',
      inputs: ['input', 'mask'],
      outputs: ['output'],
      defaultParams: () => ({
        enabled: true,
        text: 'TITLE',
        fontFamily: 'Inter',
        fontSize: 48,
        tracking: 2,
        lineSpacing: 1.2,
        color: '#ffffff',
        strokeColor: '#000000',
        strokeWidth: 2,
        glowColor: '#3b6bf5',
        glowSize: 10,
        posX: 0.5,
        posY: 0.85,
        align: 'center',
        box: false,
        boxColor: 'rgba(5, 8, 22, 0.7)',
      }),
    },
    blur: {
      type: 'blur',
      name: 'Blur',
      category: 'filter',
      icon: '💧',
      inputs: ['input', 'mask'],
      outputs: ['output'],
      defaultParams: () => ({
        enabled: true,
        blurType: 'gaussian',
        radius: 12,
        angle: 0,
      }),
    },
    glow: {
      type: 'glow',
      name: 'Glow',
      category: 'filter',
      icon: '✨',
      inputs: ['input', 'mask'],
      outputs: ['output'],
      defaultParams: () => ({
        enabled: true,
        threshold: 0.6,
        size: 20,
        color: '#ffffff',
        intensity: 1.5,
      }),
    },
    vignette: {
      type: 'vignette',
      name: 'Vignette',
      category: 'filter',
      icon: '🕶️',
      inputs: ['input', 'mask'],
      outputs: ['output'],
      defaultParams: () => ({
        enabled: true,
        radius: 0.75,
        softness: 0.45,
        aspect: 1.0,
        color: '#000000',
        opacity: 0.8,
      }),
    },
    film_grain: {
      type: 'film_grain',
      name: 'Film Grain',
      category: 'texture',
      icon: '🎞️',
      inputs: ['input', 'mask'],
      outputs: ['output'],
      defaultParams: () => ({
        enabled: true,
        intensity: 0.25,
        size: 1.5,
        roughness: 0.5,
        animated: true,
      }),
    },
    camera_shake: {
      type: 'camera_shake',
      name: 'Camera Shake',
      category: 'transform',
      icon: '📳',
      inputs: ['input', 'mask'],
      outputs: ['output'],
      defaultParams: () => ({
        enabled: true,
        frequency: 4.0,
        amplitude: 10,
        rotShake: 1.5,
        decay: 0.05,
      }),
    },
    chroma_keyer: {
      type: 'chroma_keyer',
      name: 'DeltaKeyer',
      category: 'matte',
      icon: '🟩',
      inputs: ['input', 'mask'],
      outputs: ['output'],
      defaultParams: () => ({
        enabled: true,
        keyColor: '#00ff00',
        tolerance: 0.28,
        softness: 0.12,
        despill: 0.7,
      }),
    },
    color_corrector: {
      type: 'color_corrector',
      name: 'ColorCorrect',
      category: 'color',
      icon: '🎨',
      inputs: ['input', 'mask'],
      outputs: ['output'],
      defaultParams: () => ({
        enabled: true,
        saturation: 1.0,
        contrast: 1.0,
        brightness: 0.0,
        hue: 0,
        tint: '#ffffff',
        tintStrength: 0.0,
      }),
    },
    merge: {
      type: 'merge',
      name: 'Merge',
      category: 'composite',
      icon: '🔀',
      inputs: ['bg', 'fg', 'mask'],
      outputs: ['output'],
      defaultParams: () => ({
        enabled: true,
        blendMode: 'source-over',
        mix: 1.0,
      }),
    },
  };

  let idCounter = 1;
  const genId = (prefix) => `${prefix}_${Date.now().toString(36)}_${(idCounter++).toString(36)}`;

  /** Creates a default Fusion graph for a clip: MediaIn -> MediaOut. */
  function newGraph() {
    return {
      version: 1,
      enabled: true,
      nodes: [
        {
          id: 'media_in',
          type: 'mediain',
          label: 'MediaIn1',
          pos: { x: 80, y: 140 },
          params: NODE_DEFS.mediain.defaultParams(),
        },
        {
          id: 'media_out',
          type: 'mediaout',
          label: 'MediaOut1',
          pos: { x: 520, y: 140 },
          params: NODE_DEFS.mediaout.defaultParams(),
        },
      ],
      connections: [
        {
          from: { nodeId: 'media_in', socket: 'output' },
          to: { nodeId: 'media_out', socket: 'input' },
        },
      ],
    };
  }

  /** Deep clone a Fusion graph */
  function cloneGraph(graph) {
    return JSON.parse(JSON.stringify(graph || newGraph()));
  }

  /** Checks if the graph is an identity pass-through (only MediaIn -> MediaOut with no active processing). */
  function isIdentity(graph) {
    if (!graph || graph.enabled === false) return true;
    const activeNodes = (graph.nodes || []).filter(
      (n) => n.type !== 'mediain' && n.type !== 'mediaout' && n.params && n.params.enabled !== false
    );
    return activeNodes.length === 0;
  }

  /** Adds a new node to the graph and returns it */
  function addNode(graph, type, options = {}) {
    const def = NODE_DEFS[type];
    if (!def) throw new Error(`Unknown node type: ${type}`);
    const count = (graph.nodes || []).filter((n) => n.type === type).length + 1;
    const node = {
      id: genId(type),
      type: type,
      label: options.label || `${def.name}${count}`,
      pos: options.pos || { x: 280, y: 140 },
      params: Object.assign(def.defaultParams(), options.params || {}),
    };
    graph.nodes.push(node);
    return node;
  }

  /** Removes a node and any connections linked to it */
  function removeNode(graph, nodeId) {
    if (nodeId === 'media_in' || nodeId === 'media_out') return false; // terminal nodes cannot be removed
    const idx = (graph.nodes || []).findIndex((n) => n.id === nodeId);
    if (idx < 0) return false;
    graph.nodes.splice(idx, 1);
    graph.connections = (graph.connections || []).filter(
      (c) => c.from.nodeId !== nodeId && c.to.nodeId !== nodeId
    );
    return true;
  }

  /** Connects two sockets. Validates against cycles and socket existence. */
  function connect(graph, fromNodeId, fromSocket, toNodeId, toSocket) {
    if (fromNodeId === toNodeId) return false;
    const fromNode = (graph.nodes || []).find((n) => n.id === fromNodeId);
    const toNode = (graph.nodes || []).find((n) => n.id === toNodeId);
    if (!fromNode || !toNode) return false;

    const fromDef = NODE_DEFS[fromNode.type];
    const toDef = NODE_DEFS[toNode.type];
    if (!fromDef || !toDef) return false;
    if (!fromDef.outputs.includes(fromSocket)) return false;
    if (!toDef.inputs.includes(toSocket)) return false;

    // Disconnect any existing connection to this target input socket (single input connection rule)
    disconnect(graph, toNodeId, toSocket);

    // Create prospective connection
    const newConn = {
      from: { nodeId: fromNodeId, socket: fromSocket },
      to: { nodeId: toNodeId, socket: toSocket },
    };
    graph.connections.push(newConn);

    // Validate cycle
    if (hasCycle(graph)) {
      // rollback
      disconnect(graph, toNodeId, toSocket);
      return false;
    }
    return true;
  }

  /** Disconnects any connection leading to target socket */
  function disconnect(graph, toNodeId, toSocket) {
    const beforeLen = graph.connections.length;
    graph.connections = (graph.connections || []).filter(
      (c) => !(c.to.nodeId === toNodeId && c.to.socket === toSocket)
    );
    return graph.connections.length < beforeLen;
  }

  /** Check for cycles in the directed connection graph */
  function hasCycle(graph) {
    const adj = {};
    (graph.nodes || []).forEach((n) => { adj[n.id] = []; });
    (graph.connections || []).forEach((c) => {
      if (adj[c.from.nodeId]) adj[c.from.nodeId].push(c.to.nodeId);
    });

    const visited = {};
    const recStack = {};

    function isCyclicUtil(v) {
      if (!visited[v]) {
        visited[v] = true;
        recStack[v] = true;
        for (const neighbour of adj[v] || []) {
          if (!visited[neighbour] && isCyclicUtil(neighbour)) return true;
          else if (recStack[neighbour]) return true;
        }
      }
      recStack[v] = false;
      return false;
    }

    for (const node of graph.nodes || []) {
      if (isCyclicUtil(node.id)) return true;
    }
    return false;
  }

  /** Returns node order sorted from inputs to outputs (topological order) */
  function topologicalSort(graph) {
    const adj = {};
    const inDegree = {};
    (graph.nodes || []).forEach((n) => {
      adj[n.id] = [];
      inDegree[n.id] = 0;
    });
    (graph.connections || []).forEach((c) => {
      if (adj[c.from.nodeId] && inDegree[c.to.nodeId] !== undefined) {
        adj[c.from.nodeId].push(c.to.nodeId);
        inDegree[c.to.nodeId]++;
      }
    });

    const queue = [];
    (graph.nodes || []).forEach((n) => {
      if (inDegree[n.id] === 0) queue.push(n.id);
    });

    const order = [];
    while (queue.length > 0) {
      const u = queue.shift();
      order.push(u);
      for (const v of adj[u] || []) {
        inDegree[v]--;
        if (inDegree[v] === 0) queue.push(v);
      }
    }
    return order.map((id) => graph.nodes.find((n) => n.id === id)).filter(Boolean);
  }

  /** Inserts a node in-line between two connected nodes */
  function insertNodeInLine(graph, type, options = {}) {
    const node = addNode(graph, type, options);
    // Find connection to MediaOut
    const outConn = (graph.connections || []).find((c) => c.to.nodeId === 'media_out');
    if (outConn) {
      const prevNodeId = outConn.from.nodeId;
      const prevSocket = outConn.from.socket;
      disconnect(graph, 'media_out', 'input');
      connect(graph, prevNodeId, prevSocket, node.id, 'input');
      connect(graph, node.id, 'output', 'media_out', 'input');
    } else {
      connect(graph, 'media_in', 'output', node.id, 'input');
      connect(graph, node.id, 'output', 'media_out', 'input');
    }
    return node;
  }

  /** Preset templates for common VFX and motion graphics workflows */
  const PRESETS = {
    cinematic_title: {
      name: 'Cinematic Title Glow',
      desc: 'Lower third title with bloom, anamorphic vignette, and subtle glow',
      build: (g) => {
        g.nodes = [
          { id: 'media_in', type: 'mediain', label: 'MediaIn1', pos: { x: 60, y: 140 }, params: NODE_DEFS.mediain.defaultParams() },
          { id: 'glow_1', type: 'glow', label: 'Glow1', pos: { x: 220, y: 140 }, params: { enabled: true, threshold: 0.65, size: 24, color: '#9ec2ff', intensity: 1.3 } },
          { id: 'vig_1', type: 'vignette', label: 'Vignette1', pos: { x: 380, y: 140 }, params: { enabled: true, radius: 0.8, softness: 0.5, aspect: 1.2, color: '#000000', opacity: 0.75 } },
          { id: 'txt_1', type: 'text_plus', label: 'Title+', pos: { x: 540, y: 140 }, params: { enabled: true, text: 'CHAPTER ONE', fontFamily: 'Inter', fontSize: 52, tracking: 4, lineSpacing: 1.2, color: '#ffffff', strokeColor: '#000000', strokeWidth: 3, glowColor: '#3b6bf5', glowSize: 16, posX: 0.5, posY: 0.82, align: 'center', box: true, boxColor: 'rgba(5, 8, 22, 0.6)' } },
          { id: 'media_out', type: 'mediaout', label: 'MediaOut1', pos: { x: 700, y: 140 }, params: NODE_DEFS.mediaout.defaultParams() },
        ];
        g.connections = [
          { from: { nodeId: 'media_in', socket: 'output' }, to: { nodeId: 'glow_1', socket: 'input' } },
          { from: { nodeId: 'glow_1', socket: 'output' }, to: { nodeId: 'vig_1', socket: 'input' } },
          { from: { nodeId: 'vig_1', socket: 'output' }, to: { nodeId: 'txt_1', socket: 'input' } },
          { from: { nodeId: 'txt_1', socket: 'output' }, to: { nodeId: 'media_out', socket: 'input' } },
        ];
      },
    },
    action_impact: {
      name: 'Action Shake & Impact Grain',
      desc: 'Dynamic camera shake with gritty 35mm film grain for visceral scenes',
      build: (g) => {
        g.nodes = [
          { id: 'media_in', type: 'mediain', label: 'MediaIn1', pos: { x: 60, y: 140 }, params: NODE_DEFS.mediain.defaultParams() },
          { id: 'shake_1', type: 'camera_shake', label: 'Shake1', pos: { x: 240, y: 140 }, params: { enabled: true, frequency: 6.0, amplitude: 14, rotShake: 2.5, decay: 0.05 } },
          { id: 'grain_1', type: 'film_grain', label: 'Grain1', pos: { x: 420, y: 140 }, params: { enabled: true, intensity: 0.35, size: 2.0, roughness: 0.6, animated: true } },
          { id: 'media_out', type: 'mediaout', label: 'MediaOut1', pos: { x: 600, y: 140 }, params: NODE_DEFS.mediaout.defaultParams() },
        ];
        g.connections = [
          { from: { nodeId: 'media_in', socket: 'output' }, to: { nodeId: 'shake_1', socket: 'input' } },
          { from: { nodeId: 'shake_1', socket: 'output' }, to: { nodeId: 'grain_1', socket: 'input' } },
          { from: { nodeId: 'grain_1', socket: 'output' }, to: { nodeId: 'media_out', socket: 'input' } },
        ];
      },
    },
    dreamy_bloom: {
      name: 'Dreamy Lens Bloom & Vignette',
      desc: 'Soft ethereal glow with boosted saturation and warm vignette',
      build: (g) => {
        g.nodes = [
          { id: 'media_in', type: 'mediain', label: 'MediaIn1', pos: { x: 60, y: 140 }, params: NODE_DEFS.mediain.defaultParams() },
          { id: 'cc_1', type: 'color_corrector', label: 'WarmCC1', pos: { x: 220, y: 140 }, params: { enabled: true, saturation: 1.15, contrast: 1.05, brightness: 0.04, hue: 0, tint: '#ffe4cc', tintStrength: 0.15 } },
          { id: 'glow_1', type: 'glow', label: 'Bloom1', pos: { x: 380, y: 140 }, params: { enabled: true, threshold: 0.55, size: 28, color: '#fff3e0', intensity: 1.4 } },
          { id: 'vig_1', type: 'vignette', label: 'Vignette1', pos: { x: 540, y: 140 }, params: { enabled: true, radius: 0.7, softness: 0.5, aspect: 1.0, color: '#090d20', opacity: 0.7 } },
          { id: 'media_out', type: 'mediaout', label: 'MediaOut1', pos: { x: 700, y: 140 }, params: NODE_DEFS.mediaout.defaultParams() },
        ];
        g.connections = [
          { from: { nodeId: 'media_in', socket: 'output' }, to: { nodeId: 'cc_1', socket: 'input' } },
          { from: { nodeId: 'cc_1', socket: 'output' }, to: { nodeId: 'glow_1', socket: 'input' } },
          { from: { nodeId: 'glow_1', socket: 'output' }, to: { nodeId: 'vig_1', socket: 'input' } },
          { from: { nodeId: 'vig_1', socket: 'output' }, to: { nodeId: 'media_out', socket: 'input' } },
        ];
      },
    },
    anamorphic_vignette: {
      name: 'Anamorphic Letterbox & Vignette',
      desc: 'Widescreen 2.39:1 aspect framing with corner falloff',
      build: (g) => {
        g.nodes = [
          { id: 'media_in', type: 'mediain', label: 'MediaIn1', pos: { x: 60, y: 140 }, params: NODE_DEFS.mediain.defaultParams() },
          { id: 'xf_1', type: 'transform', label: 'AnamorphicCrop', pos: { x: 240, y: 140 }, params: { enabled: true, posX: 0, posY: 0, scale: 1.08, rotation: 0, pivotX: 0.5, pivotY: 0.5, flipH: false, flipV: false } },
          { id: 'vig_1', type: 'vignette', label: 'Vignette1', pos: { x: 420, y: 140 }, params: { enabled: true, radius: 0.82, softness: 0.4, aspect: 1.4, color: '#000000', opacity: 0.85 } },
          { id: 'media_out', type: 'mediaout', label: 'MediaOut1', pos: { x: 600, y: 140 }, params: NODE_DEFS.mediaout.defaultParams() },
        ];
        g.connections = [
          { from: { nodeId: 'media_in', socket: 'output' }, to: { nodeId: 'xf_1', socket: 'input' } },
          { from: { nodeId: 'xf_1', socket: 'output' }, to: { nodeId: 'vig_1', socket: 'input' } },
          { from: { nodeId: 'vig_1', socket: 'output' }, to: { nodeId: 'media_out', socket: 'input' } },
        ];
      },
    },
    chroma_key: {
      name: 'Green Screen Keyer',
      desc: 'Clean background keying with spill suppression',
      build: (g) => {
        g.nodes = [
          { id: 'media_in', type: 'mediain', label: 'MediaIn1', pos: { x: 60, y: 140 }, params: NODE_DEFS.mediain.defaultParams() },
          { id: 'key_1', type: 'chroma_keyer', label: 'DeltaKeyer1', pos: { x: 300, y: 140 }, params: { enabled: true, keyColor: '#00ff00', tolerance: 0.3, softness: 0.15, despill: 0.8 } },
          { id: 'media_out', type: 'mediaout', label: 'MediaOut1', pos: { x: 540, y: 140 }, params: NODE_DEFS.mediaout.defaultParams() },
        ];
        g.connections = [
          { from: { nodeId: 'media_in', socket: 'output' }, to: { nodeId: 'key_1', socket: 'input' } },
          { from: { nodeId: 'key_1', socket: 'output' }, to: { nodeId: 'media_out', socket: 'input' } },
        ];
      },
    },
    face_blur: {
      name: 'Targeted Face / Region Blur',
      desc: 'Gaussian blur isolated within a feathered ellipse mask',
      build: (g) => {
        g.nodes = [
          { id: 'media_in', type: 'mediain', label: 'MediaIn1', pos: { x: 60, y: 140 }, params: NODE_DEFS.mediain.defaultParams() },
          { id: 'mask_1', type: 'ellipse_mask', label: 'FaceMask1', pos: { x: 260, y: 40 }, params: { enabled: true, x: 0.5, y: 0.45, width: 0.35, height: 0.45, feather: 0.12, invert: false } },
          { id: 'blur_1', type: 'blur', label: 'Blur1', pos: { x: 260, y: 170 }, params: { enabled: true, blurType: 'gaussian', radius: 24, angle: 0 } },
          { id: 'media_out', type: 'mediaout', label: 'MediaOut1', pos: { x: 500, y: 170 }, params: NODE_DEFS.mediaout.defaultParams() },
        ];
        g.connections = [
          { from: { nodeId: 'media_in', socket: 'output' }, to: { nodeId: 'blur_1', socket: 'input' } },
          { from: { nodeId: 'mask_1', socket: 'mask' }, to: { nodeId: 'blur_1', socket: 'mask' } },
          { from: { nodeId: 'blur_1', socket: 'output' }, to: { nodeId: 'media_out', socket: 'input' } },
        ];
      },
    },
  };

  /** Applies a preset by key to a graph */
  function applyPreset(graph, presetKey) {
    const p = PRESETS[presetKey];
    if (!p) throw new Error(`Unknown preset: ${presetKey}`);
    p.build(graph);
    return graph;
  }

  // -------------------------------------------------------------
  // RENDER PIPELINE: Evaluate nodes on 2D / Canvas context
  // -------------------------------------------------------------

  /** Evaluates a single node transformation from source canvas to target canvas */
  function processNode(node, srcCanvas, dstCanvas, time = 0) {
    const w = srcCanvas.width, h = srcCanvas.height;
    if (dstCanvas.width !== w || dstCanvas.height !== h) {
      dstCanvas.width = w;
      dstCanvas.height = h;
    }
    const ctx = dstCanvas.getContext('2d');
    ctx.clearRect(0, 0, w, h);

    if (!node.params || node.params.enabled === false) {
      ctx.drawImage(srcCanvas, 0, 0);
      return;
    }

    const p = node.params;
    switch (node.type) {
      case 'transform': {
        ctx.save();
        const px = w * (p.pivotX != null ? p.pivotX : 0.5);
        const py = h * (p.pivotY != null ? p.pivotY : 0.5);
        const dx = (p.posX || 0) * w;
        const dy = (p.posY || 0) * h;
        ctx.translate(px + dx, py + dy);
        if (p.rotation) ctx.rotate((p.rotation * Math.PI) / 180);
        const sx = (p.scale || 1.0) * (p.flipH ? -1 : 1);
        const sy = (p.scale || 1.0) * (p.flipV ? -1 : 1);
        ctx.scale(sx, sy);
        ctx.drawImage(srcCanvas, -px, -py);
        ctx.restore();
        break;
      }
      case 'blur': {
        ctx.save();
        const r = clamp(p.radius || 0, 0, 80);
        if (r > 0) {
          ctx.filter = `blur(${r}px)`;
        }
        ctx.drawImage(srcCanvas, 0, 0);
        ctx.restore();
        break;
      }
      case 'glow': {
        ctx.save();
        ctx.drawImage(srcCanvas, 0, 0);
        const size = clamp(p.size || 15, 1, 60);
        const intensity = clamp(p.intensity || 1.0, 0.1, 3.0);
        ctx.globalCompositeOperation = 'screen';
        ctx.filter = `brightness(${intensity}) blur(${size}px)`;
        ctx.drawImage(srcCanvas, 0, 0);
        ctx.restore();
        break;
      }
      case 'vignette': {
        ctx.save();
        ctx.drawImage(srcCanvas, 0, 0);
        const rad = clamp(p.radius || 0.75, 0.1, 1.5) * Math.max(w, h) * 0.5;
        const soft = clamp(p.softness || 0.45, 0.05, 1.0);
        const grad = ctx.createRadialGradient(w / 2, h / 2, Math.max(0, rad * (1 - soft)), w / 2, h / 2, rad);
        grad.addColorStop(0, 'rgba(0,0,0,0)');
        const col = p.color || '#000000';
        const op = clamp(p.opacity != null ? p.opacity : 0.8, 0, 1);
        grad.addColorStop(1, hexToRgba(col, op));
        ctx.fillStyle = grad;
        ctx.fillRect(0, 0, w, h);
        ctx.restore();
        break;
      }
      case 'film_grain': {
        ctx.save();
        ctx.drawImage(srcCanvas, 0, 0);
        const amount = clamp(p.intensity || 0.25, 0, 1);
        if (amount > 0.01) {
          const img = ctx.getImageData(0, 0, w, h);
          const d = img.data;
          const seed = p.animated ? Math.floor(time * 30) % 100 : 42;
          let rnd = (seed * 1103515245 + 12345) & 0x7fffffff;
          const scale = amount * 128;
          for (let i = 0; i < d.length; i += 4) {
            rnd = (rnd * 1103515245 + 12345) & 0x7fffffff;
            const noise = ((rnd & 0xff) / 255 - 0.5) * scale;
            d[i] = clamp(d[i] + noise, 0, 255);
            d[i + 1] = clamp(d[i + 1] + noise, 0, 255);
            d[i + 2] = clamp(d[i + 2] + noise, 0, 255);
          }
          ctx.putImageData(img, 0, 0);
        }
        ctx.restore();
        break;
      }
      case 'camera_shake': {
        ctx.save();
        const freq = clamp(p.frequency || 4.0, 0.5, 30.0);
        const amp = clamp(p.amplitude || 10, 0, 60);
        const rShake = clamp(p.rotShake || 1.5, 0, 10);
        const t = time * freq;
        const ox = Math.sin(t * 1.3) * Math.cos(t * 0.9) * amp;
        const oy = Math.cos(t * 1.1) * Math.sin(t * 0.7) * amp;
        const rot = Math.sin(t * 1.7) * rShake * (Math.PI / 180);
        ctx.translate(w / 2 + ox, h / 2 + oy);
        ctx.rotate(rot);
        ctx.drawImage(srcCanvas, -w / 2, -h / 2);
        ctx.restore();
        break;
      }
      case 'chroma_keyer': {
        ctx.save();
        const img = ctx.getImageData(0, 0, w, h);
        const d = img.data;
        const keyRgb = hexToRgb(p.keyColor || '#00ff00');
        const tol = clamp(p.tolerance || 0.28, 0.05, 0.9) * 255;
        const soft = clamp(p.softness || 0.12, 0.01, 0.5) * 255;
        const despill = clamp(p.despill != null ? p.despill : 0.7, 0, 1);

        for (let i = 0; i < d.length; i += 4) {
          const r = d[i], g = d[i + 1], b = d[i + 2];
          const dist = Math.hypot(r - keyRgb.r, g - keyRgb.g, b - keyRgb.b);
          if (dist < tol) {
            d[i + 3] = 0;
          } else if (dist < tol + soft) {
            d[i + 3] = Math.round(((dist - tol) / soft) * 255);
          }
          // despill
          if (despill > 0 && keyRgb.g > keyRgb.r && keyRgb.g > keyRgb.b) {
            const maxRb = Math.max(r, b);
            if (g > maxRb) d[i + 1] = Math.round(g * (1 - despill) + maxRb * despill);
          }
        }
        ctx.putImageData(img, 0, 0);
        ctx.restore();
        break;
      }
      case 'color_corrector': {
        ctx.save();
        const sat = clamp(p.saturation != null ? p.saturation : 1.0, 0, 3);
        const con = clamp(p.contrast != null ? p.contrast : 1.0, 0.1, 3);
        const br = clamp(p.brightness || 0.0, -1, 1);
        const hue = clamp(p.hue || 0, -180, 180);
        const filterStr = `saturate(${sat * 100}%) contrast(${con * 100}%) brightness(${100 + br * 100}%) hue-rotate(${hue}deg)`;
        ctx.filter = filterStr;
        ctx.drawImage(srcCanvas, 0, 0);
        if (p.tint && p.tintStrength > 0) {
          ctx.globalCompositeOperation = 'color';
          ctx.fillStyle = hexToRgba(p.tint, p.tintStrength);
          ctx.fillRect(0, 0, w, h);
        }
        ctx.restore();
        break;
      }
      case 'text_plus': {
        ctx.save();
        ctx.drawImage(srcCanvas, 0, 0);
        const text = p.text || '';
        if (text) {
          const fontSize = Math.round((p.fontSize || 48) * (h / 720));
          ctx.font = `bold ${fontSize}px ${p.fontFamily || 'Inter'}, sans-serif`;
          ctx.textAlign = p.align || 'center';
          ctx.textBaseline = 'middle';

          const x = (p.posX != null ? p.posX : 0.5) * w;
          const y = (p.posY != null ? p.posY : 0.85) * h;
          const lines = text.split('\n');
          const lineH = fontSize * (p.lineSpacing || 1.2);

          lines.forEach((line, idx) => {
            const ly = y + (idx - (lines.length - 1) / 2) * lineH;

            // Background box
            if (p.box) {
              const metrics = ctx.measureText(line);
              const padX = fontSize * 0.4, padY = fontSize * 0.2;
              let bx = x - padX;
              if (ctx.textAlign === 'center') bx = x - metrics.width / 2 - padX;
              else if (ctx.textAlign === 'right') bx = x - metrics.width - padX;
              ctx.fillStyle = p.boxColor || 'rgba(0,0,0,0.6)';
              ctx.fillRect(bx, ly - fontSize / 2 - padY, metrics.width + padX * 2, fontSize + padY * 2);
            }

            // Glow / shadow
            if (p.glowSize > 0) {
              ctx.shadowColor = p.glowColor || '#3b6bf5';
              ctx.shadowBlur = p.glowSize;
              ctx.shadowOffsetX = 0;
              ctx.shadowOffsetY = 0;
            }

            // Stroke
            if (p.strokeWidth > 0) {
              ctx.strokeStyle = p.strokeColor || '#000000';
              ctx.lineWidth = p.strokeWidth * (h / 720);
              ctx.strokeText(line, x, ly);
            }

            // Fill
            ctx.fillStyle = p.color || '#ffffff';
            ctx.fillText(line, x, ly);
          });
        }
        ctx.restore();
        break;
      }
      case 'rectangle_mask': {
        ctx.save();
        const mx = (p.x != null ? p.x : 0.5) * w;
        const my = (p.y != null ? p.y : 0.5) * h;
        const mw = (p.width != null ? p.width : 0.5) * w;
        const mh = (p.height != null ? p.height : 0.4) * h;
        const f = clamp(p.feather != null ? p.feather : 0.08, 0, 0.4) * Math.min(w, h);
        const inv = !!p.invert;

        ctx.fillStyle = inv ? '#ffffff' : '#000000';
        ctx.fillRect(0, 0, w, h);

        if (f > 1) ctx.filter = `blur(${Math.round(f)}px)`;
        ctx.fillStyle = inv ? '#000000' : '#ffffff';
        const rx = mx - mw / 2, ry = my - mh / 2;
        const rad = (p.cornerRadius || 0.05) * Math.min(mw, mh);
        if (ctx.roundRect) {
          ctx.beginPath();
          ctx.roundRect(rx, ry, mw, mh, rad);
          ctx.fill();
        } else {
          ctx.fillRect(rx, ry, mw, mh);
        }
        ctx.restore();
        break;
      }
      case 'ellipse_mask': {
        ctx.save();
        const mx = (p.x != null ? p.x : 0.5) * w;
        const my = (p.y != null ? p.y : 0.5) * h;
        const mw = (p.width != null ? p.width : 0.45) * w * 0.5;
        const mh = (p.height != null ? p.height : 0.45) * h * 0.5;
        const f = clamp(p.feather != null ? p.feather : 0.1, 0, 0.4) * Math.min(w, h);
        const inv = !!p.invert;

        ctx.fillStyle = inv ? '#ffffff' : '#000000';
        ctx.fillRect(0, 0, w, h);

        if (f > 1) ctx.filter = `blur(${Math.round(f)}px)`;
        ctx.fillStyle = inv ? '#000000' : '#ffffff';
        ctx.beginPath();
        if (ctx.ellipse) {
          ctx.ellipse(mx, my, Math.max(1, mw), Math.max(1, mh), 0, 0, Math.PI * 2);
        } else {
          ctx.arc(mx, my, Math.max(1, mw), 0, Math.PI * 2);
        }
        ctx.fill();
        ctx.restore();
        break;
      }
      default:
        ctx.drawImage(srcCanvas, 0, 0);
        break;
    }
  }

  function processNodeWithMask(node, srcCanvas, dstCanvas, time = 0, maskCanvas = null) {
    if (!maskCanvas) {
      processNode(node, srcCanvas, dstCanvas, time);
      return;
    }
    const w = srcCanvas.width, h = srcCanvas.height;
    const effCanvas = createCanvas(w, h);
    processNode(node, srcCanvas, effCanvas, time);

    if (dstCanvas.width !== w || dstCanvas.height !== h) {
      dstCanvas.width = w;
      dstCanvas.height = h;
    }
    const ctx = dstCanvas.getContext('2d');
    ctx.clearRect(0, 0, w, h);
    ctx.drawImage(srcCanvas, 0, 0);

    const maskEffCanvas = createCanvas(w, h);
    const mCtx = maskEffCanvas.getContext('2d');
    mCtx.drawImage(effCanvas, 0, 0);
    mCtx.globalCompositeOperation = 'destination-in';
    mCtx.drawImage(maskCanvas, 0, 0);

    ctx.drawImage(maskEffCanvas, 0, 0);
  }

  /** Evaluates full graph from source image/canvas to destination canvas */
  function evaluate(graph, sourceCanvas, destCanvas, currentTime = 0, targetViewNodeId = null) {
    if (!graph || graph.enabled === false || isIdentity(graph)) {
      const ctx = destCanvas.getContext('2d');
      if (destCanvas.width !== sourceCanvas.width || destCanvas.height !== sourceCanvas.height) {
        destCanvas.width = sourceCanvas.width;
        destCanvas.height = sourceCanvas.height;
      }
      ctx.clearRect(0, 0, destCanvas.width, destCanvas.height);
      ctx.drawImage(sourceCanvas, 0, 0);
      return destCanvas;
    }

    const sorted = topologicalSort(graph);
    const w = sourceCanvas.width, h = sourceCanvas.height;

    // Ping-pong buffers
    const bufferA = createCanvas(w, h);
    const bufferB = createCanvas(w, h);
    bufferA.getContext('2d').drawImage(sourceCanvas, 0, 0);

    const nodeOutputs = { media_in: bufferA };
    let currentSrc = bufferA;

    for (const node of sorted) {
      if (node.type === 'mediain') continue;
      if (node.type === 'mediaout') {
        const inConn = (graph.connections || []).find((c) => c.to.nodeId === 'media_out');
        const finalSrc = (inConn && nodeOutputs[inConn.from.nodeId]) ? nodeOutputs[inConn.from.nodeId] : currentSrc;
        const targetSrc = (targetViewNodeId && nodeOutputs[targetViewNodeId]) ? nodeOutputs[targetViewNodeId] : finalSrc;
        const ctx = destCanvas.getContext('2d');
        if (destCanvas.width !== w || destCanvas.height !== h) {
          destCanvas.width = w;
          destCanvas.height = h;
        }
        ctx.clearRect(0, 0, w, h);
        ctx.drawImage(targetSrc, 0, 0);
        return destCanvas;
      }

      // Find input source for this node
      const inConn = (graph.connections || []).find((c) => c.to.nodeId === node.id && c.to.socket === 'input');
      const inputBuffer = (inConn && nodeOutputs[inConn.from.nodeId]) ? nodeOutputs[inConn.from.nodeId] : currentSrc;

      // Find mask source if any
      const maskConn = (graph.connections || []).find((c) => c.to.nodeId === node.id && c.to.socket === 'mask');
      const maskBuffer = maskConn ? nodeOutputs[maskConn.from.nodeId] : null;

      const outBuffer = createCanvas(w, h);
      processNodeWithMask(node, inputBuffer, outBuffer, currentTime, maskBuffer);
      nodeOutputs[node.id] = outBuffer;
      currentSrc = outBuffer;

      if (targetViewNodeId === node.id) {
        const ctx = destCanvas.getContext('2d');
        if (destCanvas.width !== w || destCanvas.height !== h) {
          destCanvas.width = w;
          destCanvas.height = h;
        }
        ctx.clearRect(0, 0, w, h);
        ctx.drawImage(outBuffer, 0, 0);
        return destCanvas;
      }
    }

    const ctx = destCanvas.getContext('2d');
    ctx.clearRect(0, 0, w, h);
    ctx.drawImage(currentSrc, 0, 0);
    return destCanvas;
  }

  // -------------------------------------------------------------
  // FFMPEG FILTERGRAPH TRANSLATION (for timeline EDL export)
  // -------------------------------------------------------------

  /** Translates an active Fusion graph into FFmpeg video filter chain expressions */
  function toFfmpegFilter(graph, width = 1920, height = 1080) {
    if (!graph || graph.enabled === false || isIdentity(graph)) return '';
    const sorted = topologicalSort(graph);
    const filters = [];

    for (const node of sorted) {
      if (!node.params || node.params.enabled === false) continue;
      const p = node.params;
      switch (node.type) {
        case 'transform': {
          const scale = p.scale || 1.0;
          const rot = p.rotation ? (p.rotation * Math.PI) / 180 : 0;
          if (scale !== 1.0) {
            filters.push(`scale=iw*${scale.toFixed(3)}:ih*${scale.toFixed(3)}:flags=bicubic,crop=${width}:${height}`);
          }
          if (rot !== 0) {
            filters.push(`rotate=${rot.toFixed(4)}:ow=${width}:oh=${height}`);
          }
          if (p.flipH) filters.push('hflip');
          if (p.flipV) filters.push('vflip');
          break;
        }
        case 'blur': {
          const r = clamp(p.radius || 12, 1, 60);
          filters.push(`gblur=sigma=${(r * 0.5).toFixed(2)}:steps=2`);
          break;
        }
        case 'vignette': {
          const angle = clamp(p.radius || 0.75, 0.2, 1.5) * (Math.PI / 4);
          filters.push(`vignette=angle=${angle.toFixed(3)}:aspect=${(p.aspect || 1.0).toFixed(2)}`);
          break;
        }
        case 'film_grain': {
          const strength = clamp(p.intensity || 0.25, 0.05, 1.0) * 40;
          filters.push(`noise=alls=${strength.toFixed(1)}:allf=t+u`);
          break;
        }
        case 'color_corrector': {
          const sat = clamp(p.saturation != null ? p.saturation : 1.0, 0, 3);
          const con = clamp(p.contrast != null ? p.contrast : 1.0, 0.1, 3);
          const br = clamp(p.brightness || 0.0, -1, 1);
          filters.push(`eq=saturation=${sat.toFixed(2)}:contrast=${con.toFixed(2)}:brightness=${br.toFixed(2)}`);
          break;
        }
        case 'text_plus': {
          if (p.text) {
            const cleanText = p.text.replace(/[:\\']/g, '\\$&').replace(/\n/g, ' ');
            const fontSize = Math.round((p.fontSize || 48) * (height / 720));
            const fontColor = p.color ? p.color.replace('#', '0x') : 'white';
            const x = Math.round((p.posX != null ? p.posX : 0.5) * width);
            const y = Math.round((p.posY != null ? p.posY : 0.85) * height);
            const xExpr = p.align === 'center' ? `(w-text_w)/2` : (p.align === 'right' ? `w-text_w-20` : `${x}`);
            const borderW = p.strokeWidth || 2;
            const borderCol = p.strokeColor ? p.strokeColor.replace('#', '0x') : 'black';
            let txtF = `drawtext=text='${cleanText}':fontsize=${fontSize}:fontcolor=${fontColor}:x=${xExpr}:y=${y}:borderw=${borderW}:bordercolor=${borderCol}`;
            if (p.box) {
              txtF += `:box=1:boxcolor=black@0.6:boxborderw=10`;
            }
            filters.push(txtF);
          }
          break;
        }
      }
    }
    return filters.join(',');
  }

  // -------------------------------------------------------------
  // HELPERS
  // -------------------------------------------------------------

  function createCanvas(w, h) {
    if (typeof document !== 'undefined') {
      const c = document.createElement('canvas');
      c.width = w; c.height = h;
      return c;
    }
    // Node.js fallback mock canvas for tests
    return {
      width: w,
      height: h,
      getContext: () => ({
        clearRect: () => {},
        drawImage: () => {},
        save: () => {},
        restore: () => {},
        translate: () => {},
        rotate: () => {},
        scale: () => {},
        fillRect: () => {},
        fillText: () => {},
        strokeText: () => {},
        measureText: (txt) => ({ width: txt.length * 10 }),
        createRadialGradient: () => ({ addColorStop: () => {} }),
        getImageData: (x, y, w, h) => ({ data: new Uint8ClampedArray(w * h * 4) }),
        putImageData: () => {},
      }),
    };
  }

  function hexToRgb(hex) {
    const c = (hex || '#000000').replace('#', '');
    const num = parseInt(c.length === 3 ? c.split('').map((x) => x + x).join('') : c, 16);
    return { r: (num >> 16) & 255, g: (num >> 8) & 255, b: num & 255 };
  }

  function hexToRgba(hex, alpha = 1) {
    const rgb = hexToRgb(hex);
    return `rgba(${rgb.r}, ${rgb.g}, ${rgb.b}, ${alpha})`;
  }

  return {
    NODE_DEFS,
    PRESETS,
    newGraph,
    cloneGraph,
    isIdentity,
    addNode,
    removeNode,
    connect,
    disconnect,
    hasCycle,
    topologicalSort,
    insertNodeInLine,
    applyPreset,
    processNode,
    evaluate,
    toFfmpegFilter,
    hexToRgb,
    hexToRgba,
  };
});
