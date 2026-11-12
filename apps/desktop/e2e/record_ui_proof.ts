import { chromium } from "@playwright/test";
import fs from "fs";
import path from "path";
import { spawn } from "child_process";

const ARTIFACT_DIR = process.env.PANELFLOW_PROOF_DIR || path.resolve(__dirname, "../../../output/ui-proof");
const SCREENSHOT_DIR = path.join(ARTIFACT_DIR, "screenshots");
const VIDEO_DIR = path.join(ARTIFACT_DIR, "videos");

if (!fs.existsSync(SCREENSHOT_DIR)) fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
if (!fs.existsSync(VIDEO_DIR)) fs.mkdirSync(VIDEO_DIR, { recursive: true });

function generatePanelSvg(title: string, subtitle: string, accentColor: string): Buffer {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="1344" height="768" viewBox="0 0 1344 768">
    <defs>
      <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%" stop-color="#090a0f"/>
        <stop offset="50%" stop-color="#121826"/>
        <stop offset="100%" stop-color="#0a0515"/>
      </linearGradient>
      <linearGradient id="neon" x1="0%" y1="0%" x2="100%" y2="0%">
        <stop offset="0%" stop-color="${accentColor}"/>
        <stop offset="100%" stop-color="#ec4899"/>
      </linearGradient>
      <filter id="glow" x="-20%" y="-20%" width="140%" height="140%">
        <feGaussianBlur stdDeviation="15" result="blur"/>
        <feComposite in="SourceGraphic" in2="blur" operator="over"/>
      </filter>
    </defs>
    <rect width="1344" height="768" fill="url(#bg)"/>
    <circle cx="950" cy="380" r="280" fill="${accentColor}" opacity="0.15" filter="url(#glow)"/>
    <circle cx="400" cy="500" r="200" fill="#ec4899" opacity="0.10" filter="url(#glow)"/>
    <path d="M 0,600 Q 400,520 800,620 T 1344,580 L 1344,768 L 0,768 Z" fill="#05070d" opacity="0.9"/>
    
    <path d="M 680,220 C 650,220 630,245 630,280 C 630,310 650,335 675,340 C 620,360 590,410 580,500 L 620,720 L 740,720 L 780,500 C 770,410 740,360 685,340 C 710,335 730,310 730,280 C 730,245 710,220 680,220 Z" fill="#1e293b" stroke="${accentColor}" stroke-width="3"/>
    <line x1="720" y1="420" x2="880" y2="240" stroke="url(#neon)" stroke-width="8" filter="url(#glow)"/>
    <line x1="720" y1="420" x2="880" y2="240" stroke="#ffffff" stroke-width="3"/>

    <text x="60" y="100" font-family="system-ui, sans-serif" font-size="34" font-weight="800" fill="#ffffff">
      ${title}
    </text>
    <text x="60" y="145" font-family="system-ui, sans-serif" font-size="18" fill="#94a3b8">
      ${subtitle}
    </text>
    <rect x="60" y="165" width="220" height="4" fill="url(#neon)" rx="2"/>

    <rect x="1100" y="50" width="180" height="40" rx="8" fill="#000000" opacity="0.7" stroke="#334155"/>
    <text x="1190" y="75" font-family="monospace" font-size="14" fill="${accentColor}" text-anchor="middle" font-weight="bold">
      1344 × 768 • QWEN 2.1
    </text>
  </svg>`;
  return Buffer.from(svg);
}

async function run() {
  console.log("Starting Vite dev server...");
  const viteProcess = spawn("cmd.exe", ["/c", "npx", "vite", "--host", "127.0.0.1", "--port", "5173"], {
    cwd: path.resolve(__dirname, ".."),
    stdio: "pipe",
  });

  viteProcess.stdout?.on("data", (d) => process.stdout.write(`[Vite] ${d}`));
  viteProcess.stderr?.on("data", (d) => process.stderr.write(`[Vite ERR] ${d}`));

  // Wait 4s for Vite
  await new Promise((r) => setTimeout(r, 4500));

  console.log("Launching Chrome via Playwright...");
  const browser = await chromium.launch({
    channel: "chrome",
    headless: true,
  });

  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    recordVideo: {
      dir: VIDEO_DIR,
      size: { width: 1440, height: 900 },
    },
  });

  const page = await context.newPage();

  // Mock API routes
  await page.route("**/api/health", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ status: "healthy", app: "PanelFlow Studio", version: "1.0.0-beta.2" }),
    });
  });

  await page.route("**/api/system/resources", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ram: { total_gb: 32, available_gb: 24, used_percent: 25, sufficient_for_inference: true },
        gpu: { available: true, device_name: "NVIDIA GeForce RTX 5060 Ti", total_mb: 16384, free_mb: 11000, used_mb: 5384, used_percent: 33, headroom_mb: 11000 },
        ollama: { online: true, loaded_models_count: 1, total_ollama_vram_mb: 7000, models: [] },
      }),
    });
  });

  await page.route("**/api/original/series", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          slug: "cyber_valkyrie",
          title: "Cyber Valkyrie Chronicles",
          genre: "cyberpunk_action",
          episodes_count: 1,
          created_at: "2026-11-09T20:00:00Z",
        },
      ]),
    });
  });

  await page.route("**/api/original/channels", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([]) });
  });

  await page.route("**/api/original/jobs", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([]) });
  });

  await page.route("**/api/youtube/status", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ connected: false, pending: false }) });
  });

  const mockWorkbenchData = {
    slug: "cyber_valkyrie",
    episode: "ep01",
    title: "Cyber Valkyrie Chronicles — Episode 1: Neon Awakening",
    beats: [
      {
        panel_id: "p001",
        order: 1,
        shot: "widescreen",
        angle: "cinematic",
        action: "Valkyrie unit boots up atop Neo-Tokyo tower overlooking torrential rain.",
        caption: "Rain hissed against the reinforced visor as neural links locked into place.",
        status: "accept",
        score: 0.94,
        audio_duration: 3.8,
        candidate_count: 1,
        selected_candidate: 1,
        iterations: [
          { n: 1, file: "panels/p001.png", kind: "generate", score: 0.94 },
        ],
      },
      {
        panel_id: "p002",
        order: 2,
        shot: "medium",
        angle: "eye_level",
        action: "Valkyrie draws her crystalline high-frequency katana, cyan plasma sparking.",
        caption: "She drew the edge; ethereal cyan plasma severed the humid gloom.",
        status: "needs_review",
        score: 0.68,
        audio_duration: 4.5,
        candidate_count: 3,
        selected_candidate: 1,
        iterations: [
          { n: 1, file: "panels/p002.png", kind: "generate", score: 0.68, bbox: [0.35, 0.25, 0.65, 0.65] },
          { n: 2, file: "panels/p002_c002.png", kind: "generate", score: 0.76, bbox: [0.38, 0.28, 0.62, 0.58] },
          { n: 3, file: "panels/p002_c003.png", kind: "generate", score: 0.88 },
        ],
      },
      {
        panel_id: "p003",
        order: 3,
        shot: "close_up",
        angle: "low_angle",
        action: "Close-up on her reflective ocular implant tracking rogue drone targets.",
        caption: "Target locks cascaded across her retinas in rapid hexadecimal pulses.",
        status: "repaired",
        score: 0.92,
        audio_duration: 3.1,
        candidate_count: 2,
        selected_candidate: 2,
        iterations: [
          { n: 1, file: "panels/p003.png", kind: "generate", score: 0.70 },
          { n: 2, file: "panels/p003_c002.png", kind: "inpaint", score: 0.92 },
        ],
      },
    ],
  };

  await page.route("**/api/original/story/cyber_valkyrie/workbench**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(mockWorkbenchData),
    });
  });

  await page.route("**/api/original/story/**/panel/**", async (route) => {
    const url = route.request().url();
    let title = "Panel 001 - Cinematic Wide";
    let sub = "Widescreen Shot (16:9) • Accept";
    let color = "#10b981"; // emerald

    if (url.includes("p002")) {
      title = "Panel 002 - Katana Draw";
      sub = "Medium Shot • Needs Review (3 Candidates)";
      color = "#f43f5e"; // rose
    } else if (url.includes("p003")) {
      title = "Panel 003 - Ocular Reticle";
      sub = "Close-up Shot • Repaired Inpaint";
      color = "#a855f7"; // purple
    }

    const svgBuf = generatePanelSvg(title, sub, color);
    await route.fulfill({
      status: 200,
      contentType: "image/svg+xml",
      body: svgBuf,
    });
  });

  console.log("Navigating to Original Stories Screen...");
  await page.goto("http://127.0.0.1:5173/#/create/stories", { waitUntil: "networkidle" });
  await page.waitForTimeout(2500);

  // Trigger workbench load if button visible
  const openWb = page.getByRole("button", { name: /Storyboard/i }).first();
  if (await openWb.isVisible()) {
    await openWb.click();
    await page.waitForTimeout(1500);
  }

  // 1. Capture Storyboard Workbench Grid
  console.log("Capturing Step 1: Storyboard Workbench Grid...");
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, "01_storyboard_workbench_grid.png") });
  await page.waitForTimeout(1000);

  // 2. Focus on Beat cards
  console.log("Capturing Step 2: Workbench Cards...");
  const beat2 = page.locator("text=#2 (p002)").first();
  if (await beat2.isVisible()) {
    await beat2.scrollIntoViewIfNeeded();
    await page.waitForTimeout(800);
  }
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, "02_workbench_card_focused.png") });
  await page.waitForTimeout(1000);

  // 3. Click Inspect on Beat #2 (p002)
  console.log("Capturing Step 3: Opening Candidate Inspector Drawer...");
  const inspectBtn = page.getByTitle("Inspect candidate iterations & defect bboxes").nth(1);
  if (await inspectBtn.isVisible()) {
    await inspectBtn.click();
    await page.waitForTimeout(1500);
  }
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, "03_candidate_inspector_drawer.png") });
  await page.waitForTimeout(1500);

  // 4. Click Candidate 2 in Candidate Inspector
  console.log("Capturing Step 4: Switching candidate iteration...");
  const cand2Btn = page.getByText("Candidate #2").first();
  if (await cand2Btn.isVisible()) {
    await cand2Btn.click();
    await page.waitForTimeout(1000);
  }
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, "04_candidate_switching_iteration.png") });
  await page.waitForTimeout(1500);

  // 5. Click Inpaint button inside Candidate Inspector
  console.log("Capturing Step 5: Opening Inpainting Editor Modal...");
  const inpaintBtn = page.getByRole("button", { name: /Inpaint defect region|Inpaint/i }).first();
  if (await inpaintBtn.isVisible()) {
    await inpaintBtn.click();
    await page.waitForTimeout(2000);
  }
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, "05_inpaint_canvas_modal.png") });
  await page.waitForTimeout(1000);

  // 6. Draw on mask canvas
  console.log("Capturing Step 6: Drawing mask on canvas...");
  const canvas = page.locator("canvas").first();
  if (await canvas.isVisible()) {
    const box = await canvas.boundingBox();
    if (box) {
      await page.mouse.move(box.x + box.width * 0.45, box.y + box.height * 0.4);
      await page.mouse.down();
      await page.mouse.move(box.x + box.width * 0.55, box.y + box.height * 0.45, { steps: 5 });
      await page.mouse.move(box.x + box.width * 0.5, box.y + box.height * 0.55, { steps: 5 });
      await page.mouse.up();
      await page.waitForTimeout(1000);
    }
  }
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, "06_inpaint_mask_drawn.png") });
  await page.waitForTimeout(1000);

  // 7. Click preset "Fix Hands & Fingers"
  console.log("Capturing Step 7: Selecting Inpaint Preset...");
  const presetBtn = page.getByText("Fix Hands & Fingers").first();
  if (await presetBtn.isVisible()) {
    await presetBtn.click();
    await page.waitForTimeout(1000);
  }
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, "07_inpaint_preset_active.png") });
  await page.waitForTimeout(2000);

  console.log("Closing page & saving video...");
  const video = page.video();
  await page.close();
  await context.close();
  await browser.close();

  if (video) {
    const videoPath = await video.path();
    const finalVideoPath = path.join(VIDEO_DIR, "ui_walkthrough_proof.webm");
    fs.copyFileSync(videoPath, finalVideoPath);
    console.log(`Video saved to: ${finalVideoPath}`);
  }

  viteProcess.kill();
  console.log("UI proof capture finished successfully!");
}

run().catch((e) => {
  console.error("Execution failed:", e);
  process.exit(1);
});
