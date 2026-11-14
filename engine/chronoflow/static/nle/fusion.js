/* ChronoFlow Fusion page - DaVinci Resolve-style node-based VFX & compositing.
   Each timeline clip carries `clip.fusion` = { nodes: [...], connections: [...] } (see fusion-graph.js).
   This file implements the UI and live preview:
   - Program monitor overlaid with real-time Fusion canvas renderer
   - Right Inspector panel showing active node parameters
   - Bottom Node Flow editor with draggable node cards, SVG cables, and quick-add toolbar. */
(function () {
  'use strict';
  const G = window.NLEFusionGraph;
  const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));

  const S = {
    open: false,
    selectedNodeId: 'media_out',
    viewedNodeId: null, // Node currently inspected on viewer (Resolve '1'/'2' dot)
    draggingNode: null,
    dragOffset: { x: 0, y: 0 },
    connectingSocket: null, // { nodeId, socket, type: 'in' | 'out', x, y }
    mousePos: { x: 0, y: 0 },
    bypassAll: false,
    clipboard: null,
  };

  let N = null, wrap = null, el = {};
  let persistTimer = 0;

  const h = (tag, attrs, ...kids) => {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (k === 'class') e.className = v;
      else if (k === 'style') e.style.cssText = v;
      else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
      else if (v !== false && v != null) e.setAttribute(k, v === true ? '' : v);
    }
    for (const c of kids.flat()) if (c != null) e.append(c.nodeType ? c : document.createTextNode(String(c)));
    return e;
  };

  const say = (m) => { if (N) N.status(m); };

  // Current clip & fusion graph
  const clip = () => { const hit = N && N.clipAtPlayhead(); return hit ? hit.clip : null; };
  const graphOf = () => {
    const c = clip();
    if (!c) return null;
    if (!c.fusion) c.fusion = G.newGraph();
    return c.fusion;
  };
  const selectedNode = () => {
    const g = graphOf();
    if (!g) return null;
    let node = (g.nodes || []).find((n) => n.id === S.selectedNodeId);
    if (!node && g.nodes && g.nodes.length) {
      node = g.nodes[g.nodes.length - 1];
      S.selectedNodeId = node.id;
    }
    return node;
  };

  function commit(checkpoint = true) {
    if (!N) return;
    if (checkpoint) N.checkpoint();
    clearTimeout(persistTimer);
    persistTimer = setTimeout(() => N.persist(), 250);
    renderGraph();
    renderInspector();
  }

  // Monitor preview canvas
  class FusionView {
    constructor(video) {
      this.v = video;
      this.cv = h('canvas', { class: 'cf-fusion-canvas' });
      video.parentNode.appendChild(this.cv);
      this.key = '';
    }
    hide() { this.cv.style.display = 'none'; this.key = ''; }
    show() { this.cv.style.display = 'block'; }
    draw(graph) {
      const v = this.v;
      if (v.readyState < 2 || !v.videoWidth) return;
      const key = `${v.currentTime}|${v.videoWidth}|${S.viewedNodeId}|${JSON.stringify(graph)}`;
      if (key === this.key && v.paused) return;
      this.key = key;

      const w = Math.min(v.videoWidth, 1920);
      const hgt = Math.round((w / v.videoWidth) * v.videoHeight);
      if (this.cv.width !== w || this.cv.height !== hgt) {
        this.cv.width = w;
        this.cv.height = hgt;
      }

      // Draw active frame through fusion graph (with optional intermediate node inspection)
      G.evaluate(graph, v, this.cv, v.currentTime, S.viewedNodeId);
    }
  }

  const views = [];
  function monitorTick() {
    requestAnimationFrame(monitorTick);
    if (!N || !N.root.screen || !N.root.screen.offsetParent) return;

    N.decks().forEach((d, i) => {
      const view = views[i] || (views[i] = new FusionView(d.el));
      const c = d.clipId && N.tl.clips.find((x) => x.id === d.clipId);
      const g = c && c.fusion && !S.bypassAll ? c.fusion : null;

      if (!g || G.isIdentity(g) || !S.open) {
        view.hide();
        return;
      }
      view.show();
      view.draw(g);
    });
  }

  // -------------------------------------------------------------
  // INSPECTOR RENDERING
  // -------------------------------------------------------------
  function renderInspector() {
    if (!el.inspBody) return;
    el.inspBody.innerHTML = '';
    const node = selectedNode();
    if (!node) {
      el.inspBody.append(h('div', { class: 'cf-hint' }, 'Select a node in the Flow Editor to inspect and edit its parameters.'));
      return;
    }

    const def = G.NODE_DEFS[node.type];
    const p = node.params || {};

    const sec = (title) => h('div', { class: 'cf-insp-sec-title' }, title);
    const row = (lbl, inputEl, valEl) => h('div', { class: 'cf-insp-row' }, h('label', {}, lbl), inputEl, valEl || h('span'));

    const slider = (lbl, key, min, max, step = 0.01, unit = '') => {
      const valText = h('input', {
        type: 'number',
        class: 'cf-insp-num',
        min, max, step,
        value: p[key] != null ? p[key] : 0,
        onchange: (e) => {
          p[key] = parseFloat(e.target.value) || 0;
          rng.value = p[key];
          commit(false);
        },
      });
      const rng = h('input', {
        type: 'range',
        min, max, step,
        value: p[key] != null ? p[key] : 0,
        oninput: (e) => {
          p[key] = parseFloat(e.target.value);
          valText.value = p[key];
          commit(false);
        },
      });
      return row(lbl, rng, valText);
    };

    const colorPicker = (lbl, key) => {
      const cInput = h('input', {
        type: 'color',
        value: p[key] || '#ffffff',
        oninput: (e) => {
          p[key] = e.target.value;
          commit(false);
        },
      });
      return row(lbl, cInput);
    };

    const textInput = (lbl, key) => {
      const tInput = h('input', {
        type: 'text',
        value: p[key] || '',
        oninput: (e) => {
          p[key] = e.target.value;
          commit(false);
        },
      });
      return row(lbl, tInput);
    };

    const checkbox = (lbl, key) => {
      const chk = h('input', {
        type: 'checkbox',
        checked: !!p[key],
        onchange: (e) => {
          p[key] = e.target.checked;
          commit(true);
        },
      });
      return row(lbl, chk);
    };

    // Node header in inspector
    el.inspNodeTitle.textContent = `${def ? def.icon : ''} ${node.label} (${def ? def.name : node.type})`;
    el.inspNodeBadge.textContent = node.params && node.params.enabled !== false ? 'ACTIVE' : 'BYPASSED';
    el.inspNodeBadge.style.color = node.params && node.params.enabled !== false ? '#46d6a3' : '#f2667a';

    const pSec = h('div', { class: 'cf-insp-sec' });
    pSec.append(checkbox('Enabled', 'enabled'));

    switch (node.type) {
      case 'transform':
        pSec.append(
          sec('Position & Scale'),
          slider('Scale', 'scale', 0.1, 4.0, 0.05),
          slider('Position X', 'posX', -1.0, 1.0, 0.01),
          slider('Position Y', 'posY', -1.0, 1.0, 0.01),
          slider('Rotation', 'rotation', -180, 180, 1),
          sec('Anchor & Flip'),
          slider('Pivot X', 'pivotX', 0, 1.0, 0.05),
          slider('Pivot Y', 'pivotY', 0, 1.0, 0.05),
          checkbox('Flip Horizontal', 'flipH'),
          checkbox('Flip Vertical', 'flipV')
        );
        break;

      case 'text_plus': {
        const txtArea = h('textarea', {
          rows: 2,
          oninput: (e) => {
            p.text = e.target.value;
            commit(false);
          },
        }, p.text || '');
        const fontSel = h('select', {
          onchange: (e) => {
            p.fontFamily = e.target.value;
            commit(true);
          },
        }, ['Inter', 'Impact', 'Georgia', 'Courier New', 'Arial'].map((f) => {
          const opt = h('option', { value: f }, f);
          if (p.fontFamily === f) opt.selected = true;
          return opt;
        }));
        const alignSel = h('select', {
          onchange: (e) => {
            p.align = e.target.value;
            commit(true);
          },
        }, ['center', 'left', 'right'].map((a) => {
          const opt = h('option', { value: a }, a.toUpperCase());
          if (p.align === a) opt.selected = true;
          return opt;
        }));

        pSec.append(
          sec('Title Text'),
          h('div', { style: 'margin-bottom:6px' }, txtArea),
          row('Font Family', fontSel),
          row('Alignment', alignSel),
          slider('Font Size', 'fontSize', 14, 160, 2),
          slider('Tracking', 'tracking', -5, 30, 1),
          colorPicker('Fill Color', 'color'),
          sec('Outline & Glow'),
          colorPicker('Stroke Color', 'strokeColor'),
          slider('Stroke Width', 'strokeWidth', 0, 16, 1),
          colorPicker('Glow Color', 'glowColor'),
          slider('Glow Size', 'glowSize', 0, 40, 1),
          sec('Position & Box'),
          slider('Position X', 'posX', 0, 1.0, 0.02),
          slider('Position Y', 'posY', 0, 1.0, 0.02),
          checkbox('Background Box', 'box')
        );
        break;
      }

      case 'blur':
        pSec.append(
          sec('Blur Settings'),
          slider('Radius', 'radius', 0, 60, 1),
          slider('Angle', 'angle', 0, 360, 5)
        );
        break;

      case 'glow':
        pSec.append(
          sec('Bloom & Glow'),
          slider('Threshold', 'threshold', 0.1, 0.95, 0.05),
          slider('Glow Size', 'size', 2, 60, 1),
          slider('Intensity', 'intensity', 0.2, 3.0, 0.1),
          colorPicker('Glow Tint', 'color')
        );
        break;

      case 'vignette':
        pSec.append(
          sec('Vignette Falloff'),
          slider('Radius', 'radius', 0.2, 1.5, 0.05),
          slider('Softness', 'softness', 0.05, 1.0, 0.05),
          slider('Aspect Ratio', 'aspect', 0.5, 2.0, 0.1),
          slider('Opacity', 'opacity', 0, 1.0, 0.05),
          colorPicker('Color', 'color')
        );
        break;

      case 'film_grain':
        pSec.append(
          sec('Grain Texture'),
          slider('Intensity', 'intensity', 0.02, 1.0, 0.02),
          slider('Grain Size', 'size', 0.5, 4.0, 0.1),
          checkbox('Animated Grain', 'animated')
        );
        break;

      case 'camera_shake':
        pSec.append(
          sec('Camera Dynamics'),
          slider('Frequency', 'frequency', 0.5, 20.0, 0.5),
          slider('Amplitude', 'amplitude', 1, 40, 1),
          slider('Rotational Shake', 'rotShake', 0, 8.0, 0.2)
        );
        break;

      case 'chroma_keyer':
        pSec.append(
          sec('DeltaKeyer Matte'),
          colorPicker('Key Color', 'keyColor'),
          slider('Tolerance', 'tolerance', 0.05, 0.8, 0.02),
          slider('Softness', 'softness', 0.01, 0.4, 0.01),
          slider('Despill', 'despill', 0, 1.0, 0.05)
        );
        break;

      case 'color_corrector':
        pSec.append(
          sec('Color Correction'),
          slider('Saturation', 'saturation', 0, 3.0, 0.05),
          slider('Contrast', 'contrast', 0.2, 3.0, 0.05),
          slider('Brightness', 'brightness', -0.5, 0.5, 0.02),
          slider('Hue Rotate', 'hue', -180, 180, 5),
          sec('Tint Overlay'),
          colorPicker('Tint Color', 'tint'),
          slider('Tint Strength', 'tintStrength', 0, 1.0, 0.05)
        );
        break;

      case 'rectangle_mask':
        pSec.append(
          sec('Rectangle Geometry'),
          slider('Center X', 'x', 0, 1.0, 0.02),
          slider('Center Y', 'y', 0, 1.0, 0.02),
          slider('Width', 'width', 0.05, 1.0, 0.02),
          slider('Height', 'height', 0.05, 1.0, 0.02),
          slider('Corner Radius', 'cornerRadius', 0, 0.5, 0.02),
          slider('Feather Edge', 'feather', 0, 0.5, 0.02),
          checkbox('Invert Mask', 'invert')
        );
        break;

      case 'ellipse_mask':
        pSec.append(
          sec('Ellipse Geometry'),
          slider('Center X', 'x', 0, 1.0, 0.02),
          slider('Center Y', 'y', 0, 1.0, 0.02),
          slider('Width', 'width', 0.05, 1.0, 0.02),
          slider('Height', 'height', 0.05, 1.0, 0.02),
          slider('Feather Edge', 'feather', 0, 0.5, 0.02),
          checkbox('Invert Mask', 'invert')
        );
        break;

      case 'mediain':
      case 'mediaout':
        pSec.append(
          h('div', { class: 'cf-hint' }, `Terminal node: ${node.type === 'mediain' ? 'Timeline clip video stream input.' : 'Final rendered composite output to master timeline.'}`)
        );
        break;
    }

    el.inspBody.append(pSec);
  }

  // -------------------------------------------------------------
  // NODE FLOW GRAPH RENDERING & INTERACTION
  // -------------------------------------------------------------
  function renderGraph() {
    if (!el.flowViewport) return;
    const g = graphOf();
    if (!g) return;

    // Clear previous node cards and SVG wires
    el.flowViewport.querySelectorAll('.cf-fnode').forEach((n) => n.remove());
    el.svgWires.innerHTML = '';

    // Draw connection cables (SVG Bezier curves)
    (g.connections || []).forEach((c) => {
      const fromNode = g.nodes.find((n) => n.id === c.from.nodeId);
      const toNode = g.nodes.find((n) => n.id === c.to.nodeId);
      if (!fromNode || !toNode) return;

      const p1 = getSocketCoords(fromNode, c.from.socket, 'out');
      const p2 = getSocketCoords(toNode, c.to.socket, 'in');

      const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      path.setAttribute('d', bezierPath(p1.x, p1.y, p2.x, p2.y));
      path.setAttribute('class', 'cf-wire');
      el.svgWires.appendChild(path);
    });

    // Draw active connecting wire if user is dragging cable
    if (S.connectingSocket) {
      const p1 = S.connectingSocket;
      const p2 = S.mousePos;
      const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      path.setAttribute('d', bezierPath(p1.x, p1.y, p2.x, p2.y));
      path.setAttribute('class', 'cf-wire-drag');
      el.svgWires.appendChild(path);
    }

    // Draw node cards
    (g.nodes || []).forEach((node) => {
      const def = G.NODE_DEFS[node.type];
      const card = h('div', {
        class: `cf-fnode ${node.id === S.selectedNodeId ? 'sel' : ''} ${node.params && node.params.enabled === false ? 'bypassed' : ''}`,
        style: `left: ${node.pos.x}px; top: ${node.pos.y}px;`,
        onpointerdown: (e) => onNodePointerDown(e, node),
      });

      // Node title bar
      const eyeBtn = h('button', {
        type: 'button',
        class: 'cf-fnode-eye',
        title: 'Bypass node (Ctrl+D)',
        onclick: (e) => {
          e.stopPropagation();
          node.params.enabled = !node.params.enabled;
          commit(true);
        },
      }, node.params.enabled !== false ? '👁️' : '🚫');

      // Dual Viewer dots ("1" and "2")
      const v1Btn = h('button', {
        type: 'button',
        class: `cf-fviewer-dot ${S.viewedNodeId === node.id ? 'active' : ''}`,
        title: 'View this node output on monitor (1)',
        onclick: (e) => {
          e.stopPropagation();
          S.viewedNodeId = S.viewedNodeId === node.id ? null : node.id;
          renderGraph();
        },
      }, '1');

      const v2Btn = h('button', {
        type: 'button',
        class: `cf-fviewer-dot ${(!S.viewedNodeId && node.id === 'media_out') || S.viewedNodeId === 'media_out' ? 'active' : ''}`,
        title: 'View final master output (2)',
        onclick: (e) => {
          e.stopPropagation();
          S.viewedNodeId = 'media_out';
          renderGraph();
        },
      }, '2');

      const viewerDots = h('div', { class: 'cf-fviewer-dots' }, v1Btn, v2Btn);

      const titleBar = h('div', { class: 'cf-fnode-bar' },
        h('span', { class: 'cf-fnode-title' }, `${def ? def.icon : ''} ${node.label}`),
        h('div', { style: 'display:flex;align-items:center;' }, viewerDots, eyeBtn)
      );

      // Sockets
      const inSockets = (def ? def.inputs : []).map((s) => {
        return h('div', {
          class: `cf-fsocket in ${s}`,
          title: `Input: ${s}`,
          onpointerdown: (e) => onSocketPointerDown(e, node, s, 'in'),
          onpointerup: (e) => onSocketPointerUp(e, node, s, 'in'),
        });
      });

      const outSockets = (def ? def.outputs : []).map((s) => {
        return h('div', {
          class: `cf-fsocket out ${s}`,
          title: `Output: ${s}`,
          onpointerdown: (e) => onSocketPointerDown(e, node, s, 'out'),
        });
      });

      const socketRow = h('div', { class: 'cf-fnode-sockets' },
        h('div', { style: 'display:flex;gap:4px;' }, inSockets),
        h('div', { style: 'display:flex;gap:4px;' }, outSockets)
      );

      const body = h('div', { class: 'cf-fnode-body' },
        h('span', {}, def ? def.category.toUpperCase() : 'FX'),
        socketRow
      );

      card.append(titleBar, body);
      el.flowViewport.appendChild(card);
    });

    // Update clip label
    const c = clip();
    if (el.clipLabel) el.clipLabel.textContent = c ? (c.label || 'Timeline Clip') : 'No Clip Selected';
  }

  function getSocketCoords(node, socketName, dir) {
    const w = 136, h = 60;
    if (dir === 'out') {
      return { x: node.pos.x + w, y: node.pos.y + h - 12 };
    } else {
      return { x: node.pos.x, y: node.pos.y + h - 12 };
    }
  }

  function bezierPath(x1, y1, x2, y2) {
    const dx = Math.abs(x2 - x1) * 0.5;
    return `M ${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}`;
  }

  // -------------------------------------------------------------
  // MOUSE & DRAG HANDLERS
  // -------------------------------------------------------------
  function onNodePointerDown(e, node) {
    if (e.target.closest('.cf-fsocket') || e.target.closest('.cf-fnode-eye')) return;
    S.selectedNodeId = node.id;
    S.draggingNode = node;
    const vpRect = el.flowViewport.getBoundingClientRect();
    S.dragOffset = {
      x: e.clientX - vpRect.left - node.pos.x,
      y: e.clientY - vpRect.top - node.pos.y,
    };
    renderGraph();
    renderInspector();
    window.addEventListener('pointermove', onPointerMove);
    window.addEventListener('pointerup', onPointerUp);
  }

  function onSocketPointerDown(e, node, socketName, dir) {
    e.stopPropagation();
    const vpRect = el.flowViewport.getBoundingClientRect();
    const pt = getSocketCoords(node, socketName, dir);
    S.connectingSocket = {
      nodeId: node.id,
      socket: socketName,
      type: dir,
      x: pt.x,
      y: pt.y,
    };
    window.addEventListener('pointermove', onPointerMove);
    window.addEventListener('pointerup', onPointerUp);
  }

  function onSocketPointerUp(e, node, socketName, dir) {
    e.stopPropagation();
    if (S.connectingSocket && S.connectingSocket.type === 'out' && dir === 'in') {
      const g = graphOf();
      if (g) {
        G.connect(g, S.connectingSocket.nodeId, S.connectingSocket.socket, node.id, socketName);
        commit(true);
      }
    }
    S.connectingSocket = null;
    renderGraph();
  }

  function onPointerMove(e) {
    const vpRect = el.flowViewport.getBoundingClientRect();
    S.mousePos = {
      x: e.clientX - vpRect.left,
      y: e.clientY - vpRect.top,
    };

    if (S.draggingNode) {
      S.draggingNode.pos.x = Math.max(10, Math.min(vpRect.width - 150, S.mousePos.x - S.dragOffset.x));
      S.draggingNode.pos.y = Math.max(10, Math.min(vpRect.height - 70, S.mousePos.y - S.dragOffset.y));
      renderGraph();
    } else if (S.connectingSocket) {
      renderGraph();
    }
  }

  function onPointerUp() {
    S.draggingNode = null;
    S.connectingSocket = null;
    window.removeEventListener('pointermove', onPointerMove);
    window.removeEventListener('pointerup', onPointerUp);
    renderGraph();
  }

  // -------------------------------------------------------------
  // ACTIONS & TOOLBAR
  // -------------------------------------------------------------
  const actions = {
    insert: (type) => {
      const g = graphOf();
      if (!g) return;
      G.insertNodeInLine(g, type);
      commit(true);
      say(`Added Fusion ${type} node.`);
    },
    deleteSelected: () => {
      const g = graphOf();
      if (!g || !S.selectedNodeId) return;
      if (G.removeNode(g, S.selectedNodeId)) {
        S.selectedNodeId = 'media_out';
        commit(true);
        say('Node deleted.');
      }
    },
    resetGraph: () => {
      const c = clip();
      if (!c) return;
      c.fusion = G.newGraph();
      S.selectedNodeId = 'media_out';
      commit(true);
      say('Fusion graph reset to default.');
    },
    preset: (key) => {
      const g = graphOf();
      if (!g) return;
      G.applyPreset(g, key);
      S.selectedNodeId = 'media_out';
      commit(true);
      say(`Applied Fusion preset: ${G.PRESETS[key].name}`);
    },
    toggleBypassAll: () => {
      S.bypassAll = !S.bypassAll;
      if (el.bypassBtn) el.bypassBtn.classList.toggle('on', S.bypassAll);
      renderGraph();
      say(S.bypassAll ? 'Fusion bypassed.' : 'Fusion active.');
    },
  };

  // -------------------------------------------------------------
  // MOUNT & LIFECYCLE
  // -------------------------------------------------------------
  function mount() {
    N = window.NLE;
    if (!N || el.mounted) return;
    wrap = document.querySelector('.davinci-nle-wrapper');
    if (!wrap) return;

    // Ensure Inspector container exists
    let insp = document.getElementById('fusionInspector');
    if (!insp) {
      insp = h('div', { class: 'fusion-inspector', id: 'fusionInspector' });
      const topRow = wrap.querySelector('.davinci-top-row') || wrap;
      topRow.appendChild(insp);
    }
    el.inspector = insp;

    // Ensure Panel container exists
    let pnl = document.getElementById('fusionPanel');
    if (!pnl) {
      pnl = h('div', { class: 'fusion-panel', id: 'fusionPanel' });
      wrap.appendChild(pnl);
    }
    el.panel = pnl;

    // Build Inspector
    el.inspNodeTitle = h('span', {}, 'Fusion Inspector');
    el.inspNodeBadge = h('span', { class: 'cf-ftitle-badge' }, 'READY');
    const inspHead = h('div', { class: 'cf-fhead' }, el.inspNodeTitle, el.inspNodeBadge);
    el.inspBody = h('div', { class: 'cf-insp-body' });
    el.inspector.append(inspHead, el.inspBody);

    // Build Toolbar buttons
    const btn = (label, act, icon = '') => h('button', {
      type: 'button',
      class: 'cf-fbtn',
      onclick: act,
    }, icon ? `${icon} ${label}` : label);

    const presetSel = h('select', {
      class: 'cf-insp-num',
      style: 'width:140px;background:#101a3d;color:#d5dcf5;padding:3px 6px;text-align:left;',
      onchange: (e) => {
        if (e.target.value) actions.preset(e.target.value);
        e.target.value = '';
      },
    },
      h('option', { value: '' }, '⚡ Quick Presets…'),
      ...Object.entries(G.PRESETS).map(([k, p]) => h('option', { value: k }, p.name))
    );

    el.clipLabel = h('span', { style: 'font-weight:700;color:#eef1ff;margin-left:4px;font-size:0.75rem;' }, 'Clip');
    el.bypassBtn = btn('Bypass All', actions.toggleBypassAll, '🚫');

    const toolbar = h('div', { class: 'cf-fbar' },
      h('span', { style: 'font-weight:800;color:#7aa2ff;font-size:0.76rem;margin-right:4px;' }, 'FUSION FX:'),
      btn('+ Transform', () => actions.insert('transform')),
      btn('+ Text+', () => actions.insert('text_plus'), '🔤'),
      btn('+ Blur', () => actions.insert('blur'), '💧'),
      btn('+ Glow', () => actions.insert('glow'), '✨'),
      btn('+ Vignette', () => actions.insert('vignette'), '🕶️'),
      btn('+ Grain', () => actions.insert('film_grain'), '🎞️'),
      btn('+ Shake', () => actions.insert('camera_shake'), '📳'),
      btn('+ DeltaKeyer', () => actions.insert('chroma_keyer'), '🟩'),
      btn('+ Color CC', () => actions.insert('color_corrector'), '🎨'),
      btn('+ Rect Mask', () => actions.insert('rectangle_mask'), '🔲'),
      btn('+ Ellipse Mask', () => actions.insert('ellipse_mask'), '⭕'),
      h('span', { class: 'cf-fsep' }),
      presetSel,
      h('span', { class: 'cf-fgrow' }),
      el.clipLabel,
      h('span', { class: 'cf-fsep' }),
      el.bypassBtn,
      btn('Delete Node', actions.deleteSelected, '🗑️'),
      btn('Reset FX', actions.resetGraph, '↺')
    );

    // Build SVG Flow Viewport
    el.flowViewport = h('div', { class: 'cf-flow-viewport' });
    el.svgWires = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    el.svgWires.setAttribute('class', 'cf-flow-svg');
    el.flowViewport.appendChild(el.svgWires);

    el.panel.append(toolbar, el.flowViewport);

    // Keyboard shortcuts
    document.addEventListener('keydown', (e) => {
      if (!S.open) return;
      if (e.key === 'Delete' || e.key === 'Backspace') {
        if (!e.target.matches('input, textarea, select')) {
          e.preventDefault();
          actions.deleteSelected();
        }
      }
    });

    el.mounted = true;
    requestAnimationFrame(monitorTick);
  }

  function open() {
    if (!el.mounted) mount();
    if (!wrap) return;
    S.open = true;
    wrap.classList.add('is-fusion');
    renderGraph();
    renderInspector();
    say(clip() ? 'Fusion: node effects pipeline active.' : 'Fusion: select a clip on the timeline to composite.');
  }

  function close() {
    if (!wrap || !S.open) return;
    S.open = false;
    wrap.classList.remove('is-fusion');
  }

  function graphFor(c) {
    return c && c.fusion && !G.isIdentity(c.fusion) ? c.fusion : null;
  }

  function hasFusion(c) {
    return !!(c && c.fusion && !G.isIdentity(c.fusion));
  }

  window.NLEFusion = {
    mount,
    open,
    close,
    graphFor,
    hasFusion,
    get state() { return S; },
  };
})();
