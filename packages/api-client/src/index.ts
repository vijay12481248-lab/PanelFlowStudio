import type {
  Project,
  Page,
  Panel,
  Job,
  SourceInspection,
  AcquisitionManifest,
  RightsStatus,
  SourceType,
  OCRRecord,
  OCREngineInfo,
  OCRRegion,
  TextRegion,
  CanonicalExportContract,
  NarrativeDocument,
  CharacterEntity,
  SceneEntity,
  StoryBeatEntity,
  VideoScript,
  ScriptSegment,
  ScriptValidationReport,
  LLMProviderInfo,
  AdaptationProfile,
  AudioTimelineResponse,
  MasterAudioTimeline,
  MotionTimelineResponse,
  VisualTimeline,
  RenderJob,
  RenderValidationReport,
  SystemProvidersResponse,
  HardwareDiagnostics,
  SanitizedDiagnostics,
  OllamaConfig,
  OllamaModelsResponse,
  SystemResourcesResponse,
  StoryboardDocument,
  StoryboardSegment,
  StoryboardSegmentUpdate,
  MusicTakeRecord,
  MusicCuePlan,
  MusicDirectionPlan,
  MusicGenerationRequest,
  SFXCapabilityReport,
  CloudLLMConfig,
  CloudLLMTestRequest,
  CloudLLMTestResponse,
  CloudLLMChatRequest,
  CloudLLMChatResponse,
  AvailableLLMProvidersResponse,
  GlobalLLMSettings,
  SaveGlobalLLMSettingsRequest,
  YouTubePackagingData,
  YouTubePackagingGenerateRequest,
  AutoPilotStatusResponse,
  AutoPilotStartRequest,
  AutoPilotStageItem,
} from "@panelflow/shared-types";


export interface ComfyWorkflowInfo {
  id: string;
  purpose: string;
  filename: string;
  sha256: string;
  verified_sha256?: string;
  available: boolean;
  error?: string;
  node_count?: number;
  model_files: string[];
}

export interface ComfyImageRequest {
  workflow_id?: string;
  prompt: string;
  negative_prompt?: string;
  width?: number;
  height?: number;
  seed?: number;
  timeout_s?: number;
}

export interface GeneratedAsset {
  id: string;
  asset_type: string;
  filename: string;
  relative_path: string;
  content_type: string;
  width: number;
  height: number;
  byte_size: number;
  sha256: string;
  status: string;
  provenance: Record<string, any>;
  created_at: string | null;
}

export interface CreateProjectParams {
  title: string;
  source_type: SourceType;
  source_url?: string;
  rights_status: RightsStatus;
  license_info?: string;
  source_metadata?: Record<string, any>;
  settings?: Record<string, any>;
}

export class ApiRequestError extends Error {
  constructor(message: string, readonly status: number, readonly code?: string) { super(message); this.name = "ApiRequestError"; }
}

export class PanelFlowApiClient {
  private baseUrl: string;
  private engineToken?: string;
  private projectHistory = new Map<string, import("@panelflow/shared-types").ProjectHistoryState>();
  private projectWriters = new Map<string, Promise<unknown>>();
  private pendingProjectWrites = new Map<string, { path: string; body: string; signature: string }>();

  constructor(baseUrl: string = "http://127.0.0.1:8765", engineToken?: string) {
    this.baseUrl = baseUrl.replace(/\/$/, "");
    this.engineToken = engineToken;
  }

  setEngineToken(engineToken: string): void {
    this.engineToken = engineToken;
  }

  private resourceUrl(endpoint: string): string {
    const suffix = this.engineToken ? `;pf-token=${encodeURIComponent(this.engineToken)}` : "";
    return `${this.baseUrl}${endpoint}${suffix}`;
  }

  private async request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`;
    const headers: Record<string, string> = {
      Accept: "application/json",
      ...(options.headers as Record<string, string> || {}),
    };

    if (this.engineToken && endpoint !== "/api/system/health") {
      headers["X-PanelFlow-Token"] = this.engineToken;
    }

    if (options.body && typeof options.body === "string" && !headers["Content-Type"]) {
      headers["Content-Type"] = "application/json";
    }

    const response = await fetch(url, {
      ...options,
      headers,
    });

    if (!response.ok) {
      let errorMsg = `HTTP Error ${response.status}: ${response.statusText}`;
      let errorCode: string | undefined;
      try {
        const errJson = await response.json();
        if (errJson.detail) {
          errorMsg = typeof errJson.detail === "string" ? errJson.detail : typeof errJson.detail.message === "string" ? errJson.detail.message : JSON.stringify(errJson.detail);
          errorCode = typeof errJson.detail.code === "string" ? errJson.detail.code : undefined;
        }
      } catch {
        // use fallback
      }
      throw new ApiRequestError(errorMsg, response.status, errorCode);
    }

    if (response.status === 204) {
      return null as T;
    }

    const data = await response.json();
    if (options.method?.toUpperCase() === "POST" && data?.job_id && !endpoint.endsWith("/cancel") && typeof window !== "undefined") {
      window.dispatchEvent(new CustomEvent("panelflow:job-submitted", { detail: { jobId: data.job_id } }));
    }
    return data;
  }

  // Projects
  async listProjects(): Promise<Project[]> {
    return this.request<Project[]>("/api/projects");
  }

  async createProject(params: CreateProjectParams): Promise<Project> {
    return this.request<Project>("/api/projects", {
      method: "POST",
      body: JSON.stringify(params),
    });
  }

  async getProject(projectId: string): Promise<Project> {
    return this.request<Project>(`/api/projects/${projectId}`);
  }

  async uploadBackgroundImage(projectId: string, file: Blob): Promise<{ image_url: string; width: number; height: number }> {
    const result = await this.request<{ image_url: string; width: number; height: number }>(`/api/projects/${encodeURIComponent(projectId)}/backgrounds`, {
      method: "POST", body: file, headers: { "Content-Type": file.type || "application/octet-stream" },
    });
    return { ...result, image_url: this.resourceUrl(result.image_url) };
  }

  /** Restore only recognized project source references with this session's capability. */
  hydrateStoryEditorState<T>(projectId: string, state: T): T {
    return this.storyEditorStateImages(state, projectId, true);
  }

  /** Durable editor snapshots must not retain per-launch engine capabilities. */
  sanitizeStoryEditorState<T>(projectId: string, state: T): T {
    return this.storyEditorStateImages(state, projectId, false);
  }

  private storyEditorStateImages(state: any, projectId: string, authenticated: boolean): any {
    if (!state || typeof state !== "object") return state;
    const imageReference = (imageUrl: unknown, pageId: unknown, panelId?: unknown) => {
      if (typeof imageUrl !== "string") return imageUrl;
      const projectPath = `/api/projects/${encodeURIComponent(projectId)}`;
      const allowed = new Set<string>();
      if (typeof pageId === "string") {
        const pagePath = `${projectPath}/pages/${encodeURIComponent(pageId)}`;
        allowed.add(`${pagePath}/file`); allowed.add(`${pagePath}/normalized-file`);
      }
      if (typeof panelId === "string") allowed.add(`${projectPath}/panels/${encodeURIComponent(panelId)}/file`);
      else if (Array.isArray(panelId)) {
        for (const pid of panelId) {
          if (typeof pid === "string") allowed.add(`${projectPath}/panels/${encodeURIComponent(pid)}/file`);
        }
      }
      try {
        const base = new URL(this.baseUrl);
        const url = new URL(imageUrl, base);
        const loopback = new Set(["127.0.0.1", "localhost", "[::1]"]);
        const sameEngine = url.origin === base.origin || (
          loopback.has(base.hostname) && loopback.has(url.hostname) &&
          url.protocol === base.protocol && url.port === base.port
        );
        const endpoint = url.pathname.replace(/;pf-token=[^/]*$/, "");
        if (endpoint.startsWith(`${projectPath}/backgrounds/`) &&
            /^[a-f\d]{32}\.png\/file$/.test(endpoint.slice(`${projectPath}/backgrounds/`.length))) allowed.add(endpoint);
        if (!sameEngine || url.username || url.password ||
            !allowed.has(endpoint)) return imageUrl;
        const credentialKeys = new Set(["token", "pf-token", "engine_token", "engine-token", "x-panelflow-token"]);
        for (const key of Array.from(url.searchParams.keys())) {
          if (credentialKeys.has(key.toLowerCase())) url.searchParams.delete(key);
        }
        const query = url.searchParams.toString();
        const resource = authenticated ? this.resourceUrl(endpoint) : endpoint;
        return `${resource}${query ? `?${query}` : ""}`;
      } catch { return imageUrl; }
    };
    const backgroundReference = (background: any) => background && typeof background === "object"
      ? { ...background, ...(typeof background.custom_image_url === "string" ? { custom_image_url: imageReference(background.custom_image_url, null) } : {}) } : background;
    return {
      ...state,
      ...(state.background_default ? { background_default: backgroundReference(state.background_default) } : {}),
      ...(Array.isArray(state.scenes) ? { scenes: state.scenes.map((scene: any) => {
        if (!scene || !Array.isArray(scene.layers)) return scene;
        return { ...scene, ...(scene.background ? { background: backgroundReference(scene.background) } : {}), layers: scene.layers.map((layer: any) => {
          if (!layer || typeof layer.image_url !== "string") return layer;
          return { ...layer, image_url: imageReference(layer.image_url, layer.source_page_id, layer.source_panel_id) };
        }) };
      }) } : {}),
      ...(Array.isArray(state.narration_chapter?.segments) ? { narration_chapter: {
        ...state.narration_chapter,
        segments: state.narration_chapter.segments.map((segment: any) => {
          const context = segment?.source_context;
          if (!context || typeof context.panel_preview_url !== "string") return segment;
          return { ...segment, source_context: { ...context,
            panel_preview_url: imageReference(context.panel_preview_url, context.page_id, context.panel_id || context.panel_ids),
          } };
        }),
      } } : {}),
    };
  }

  async getStoryEditorState(projectId: string): Promise<{ state: any | null; history?: import("@panelflow/shared-types").ProjectHistoryState }> {
    const response = await this.request<{ state: any | null; history?: import("@panelflow/shared-types").ProjectHistoryState }>(`/api/projects/${projectId}/story-editor`);
    this.observeProjectHistory(projectId, response.history);
    return { ...response, state: this.hydrateStoryEditorState(projectId, response.state) };
  }

  async saveStoryEditorState(projectId: string, state: any, alignPanels = false): Promise<{ state: any; updated_at: string; history?: import("@panelflow/shared-types").ProjectHistoryState }> {
    const input = { state: this.sanitizeStoryEditorState(projectId, state), align_panels: alignPanels };
    const response = await this.projectWrite(projectId, `/api/projects/${projectId}/story-editor`, input, "PUT");
    return { ...response, state: this.hydrateStoryEditorState(projectId, response.state) };
  }

  getCachedProjectHistory(projectId: string): import("@panelflow/shared-types").ProjectHistoryState | null {
    const cached = this.projectHistory.get(projectId);
    return cached ? structuredClone(cached) : null;
  }

  private observeProjectHistory(projectId: string, history?: import("@panelflow/shared-types").ProjectHistoryState): void {
    if (history && Number.isSafeInteger(history.revision) && history.revision >= (this.projectHistory.get(projectId)?.revision ?? 0))
      this.projectHistory.set(projectId, structuredClone(history));
  }

  async getProjectHistory(projectId: string): Promise<import("@panelflow/shared-types").ProjectHistoryReply> {
    const reply = await this.request<import("@panelflow/shared-types").ProjectHistoryReply>(`/api/projects/${projectId}/history`);
    this.observeProjectHistory(projectId, reply.history);
    return { ...reply, state: this.hydrateStoryEditorState(projectId, reply.state) };
  }

  async moveProjectHistory(projectId: string, direction: "undo" | "redo"): Promise<import("@panelflow/shared-types").ProjectHistoryReply> {
    if (!this.projectHistory.has(projectId)) await this.getProjectHistory(projectId);
    const reply = await this.projectWrite(projectId, `/api/projects/${projectId}/history/${direction}`, {});
    return { ...reply, state: this.hydrateStoryEditorState(projectId, reply.state) };
  }

  async undo(projectId: string): Promise<import("@panelflow/shared-types").ProjectHistoryReply> {
    return this.moveProjectHistory(projectId, "undo");
  }

  async redo(projectId: string): Promise<import("@panelflow/shared-types").ProjectHistoryReply> {
    return this.moveProjectHistory(projectId, "redo");
  }

  async resetProjectHistory(projectId: string, fingerprint: string): Promise<import("@panelflow/shared-types").ProjectHistoryReply> {
    const reply = await this.projectWrite(projectId, `/api/projects/${projectId}/history/reset`, { fingerprint });
    return { ...reply, state: this.hydrateStoryEditorState(projectId, reply.state) };
  }

  async executeProjectHistoryCommand(projectId: string, command: { type: string; version: number; label: string; input: object }): Promise<import("@panelflow/shared-types").ProjectHistoryReply> {
    if (!this.projectHistory.has(projectId)) await this.getProjectHistory(projectId);
    const reply = await this.projectWrite(projectId, `/api/projects/${projectId}/history/commands`, command);
    return { ...reply, state: this.hydrateStoryEditorState(projectId, reply.state) };
  }

  /** One writer per project. Ambiguous failures keep the same receipt ID for retry. */
  private projectWrite(projectId: string, path: string, input: object, method = "POST"): Promise<any> {
    const signature = JSON.stringify({ path, method, input });
    const run = async () => {
      const send = async (pending: { path: string; body: string }) => {
        try {
          const response = await this.request<any>(pending.path, { method: pending.path.endsWith("/story-editor") ? "PUT" : "POST", body: pending.body });
          this.observeProjectHistory(projectId, response.history);
          this.pendingProjectWrites.delete(projectId);
          return response;
        } catch (error) {
          if (error instanceof ApiRequestError && error.status < 500) {
            this.pendingProjectWrites.delete(projectId);
            if (error.code === "CONFLICT") {
              const previous = this.projectHistory.get(projectId);
              if (previous) this.projectHistory.set(projectId, { ...previous, conflicted: true, canUndo: false, canRedo: false, error: { code: error.code, message: error.message } });
            }
          }
          throw error;
        }
      };
      const pending = this.pendingProjectWrites.get(projectId);
      if (pending?.signature === signature) return send(pending);
      // Resolve a possibly committed earlier operation before issuing a different edit.
      if (pending) await send(pending);
      const body = JSON.stringify({ ...input, expected_revision: this.projectHistory.get(projectId)?.revision ?? 0, operation_id: globalThis.crypto.randomUUID() });
      const next = { path, body, signature };
      this.pendingProjectWrites.set(projectId, next);
      return send(next);
    };
    const result = (this.projectWriters.get(projectId) ?? Promise.resolve()).then(run);
    this.projectWriters.set(projectId, result.catch(() => undefined));
    return result;
  }

  async deleteProject(projectId: string): Promise<void> {
    return this.request<void>(`/api/projects/${projectId}`, {
      method: "DELETE",
    });
  }

  async startAcquisition(projectId: string): Promise<{ job_id: string; message: string }> {
    return this.request<{ job_id: string; message: string }>(`/api/projects/${projectId}/acquire`, {
      method: "POST",
    });
  }

  async retryFailedPages(projectId: string): Promise<{ job_id: string; message: string }> {
    return this.request<{ job_id: string; message: string }>(`/api/projects/${projectId}/retry`, {
      method: "POST",
    });
  }

  async confirmAcquisition(projectId: string): Promise<Project> {
    await this.executeProjectHistoryCommand(projectId, {
      type: "project.confirm",
      version: 1,
      label: "Confirm acquisition",
      input: {},
    });
    return this.getProject(projectId);
  }

  async getManifest(projectId: string): Promise<AcquisitionManifest> {
    return this.request<AcquisitionManifest>(`/api/projects/${projectId}/manifest`);
  }

  // Pages
  async listPages(projectId: string): Promise<Page[]> {
    return this.request<Page[]>(`/api/projects/${projectId}/pages`);
  }

  async reorderPages(projectId: string, pageIds: string[]): Promise<Page[]> {
    await this.executeProjectHistoryCommand(projectId, {
      type: "page.reorder",
      version: 1,
      label: "Reorder pages",
      input: { page_ids: pageIds },
    });
    return this.listPages(projectId);
  }

  async deletePage(projectId: string, pageId: string): Promise<void> {
    await this.executeProjectHistoryCommand(projectId, {
      type: "page.delete",
      version: 1,
      label: "Delete page",
      input: { page_id: pageId },
    });
  }

  async rotatePage(projectId: string, pageId: string, degrees: number = 90): Promise<Page> {
    await this.executeProjectHistoryCommand(projectId, {
      type: "page.rotate",
      version: 1,
      label: "Rotate page",
      input: { page_id: pageId, degrees },
    });
    const pages = await this.listPages(projectId);
    const page = pages.find((p) => p.id === pageId);
    if (!page) throw new Error("Rotated page not found");
    return page;
  }

  getPageImageUrl(projectId: string, pageId: string): string {
    return this.resourceUrl(`/api/projects/${projectId}/pages/${pageId}/file`);
  }

  getNormalizedPageImageUrl(projectId: string, pageId: string): string {
    return this.resourceUrl(`/api/projects/${projectId}/pages/${pageId}/normalized-file`);
  }

  // Normalization & Panels
  async normalizeProject(projectId: string, targetWidth: number = 1920): Promise<{ job_id: string; message: string }> {
    return this.request<{ job_id: string; message: string }>(`/api/projects/${projectId}/normalize`, {
      method: "POST",
      body: JSON.stringify({ target_width: targetWidth }),
    });
  }

  async detectPanels(
    projectId: string,
    readingDirection: "ltr" | "rtl" = "ltr",
    minAreaRatio: number = 0.02
  ): Promise<{ job_id: string; message: string }> {
    return this.request<{ job_id: string; message: string }>(`/api/projects/${projectId}/detect-panels`, {
      method: "POST",
      body: JSON.stringify({ reading_direction: readingDirection, min_area_ratio: minAreaRatio }),
    });
  }

  async listPanels(projectId: string, pageId?: string): Promise<Panel[]> {
    const query = pageId ? `?page_id=${encodeURIComponent(pageId)}` : "";
    return this.request<Panel[]>(`/api/projects/${projectId}/panels${query}`);
  }

  async addPanel(
    projectId: string,
    pageId: string,
    x: number,
    y: number,
    width: number,
    height: number,
    panelType: string = "STANDARD"
  ): Promise<Panel> {
    const panelId = globalThis.crypto.randomUUID();
    await this.executeProjectHistoryCommand(projectId, {
      type: "panel.create", version: 1, label: "Add panel", input: { panel_id: panelId, page_id: pageId, x, y, width, height, panel_type: panelType },
    });
    const panel = (await this.listPanels(projectId)).find((candidate) => candidate.id === panelId);
    if (!panel) throw new Error("Panel was not returned after it was created");
    return panel;
  }

  async updatePanel(
    projectId: string,
    panelId: string,
    x: number,
    y: number,
    width: number,
    height: number,
    status?: string,
    panelType?: string
  ): Promise<Panel> {
    await this.executeProjectHistoryCommand(projectId, {
      type: "panel.geometry",
      version: 1,
      label: "Edit panel",
      input: { panel_id: panelId, x, y, width, height, status, panel_type: panelType },
    });
    const panel = (await this.listPanels(projectId)).find((candidate) => candidate.id === panelId);
    if (!panel) throw new Error("Panel was not returned after its geometry was updated");
    return panel;
  }

  async savePanelSelections(projectId: string, panelId: string, selections: Array<{
    x: number; y: number; width: number; height: number; points?: Array<[number, number]>;
  }>, pageBounds = false): Promise<Panel[]> {
    await this.executeProjectHistoryCommand(projectId, {
      type: "panel.selections", version: 1, label: "Save panel selectors",
      input: { panel_id: panelId, selections, page_bounds: pageBounds },
    });
    return this.listPanels(projectId);
  }

  async addPageSelections(projectId: string, pageId: string, selections: Array<{
    x: number; y: number; width: number; height: number; points?: Array<[number, number]>;
  }>): Promise<Panel[]> {
    await this.executeProjectHistoryCommand(projectId, {
      type: "panel.selections", version: 1, label: "Save page selectors",
      input: { page_id: pageId, selections, page_bounds: true },
    });
    return this.listPanels(projectId);
  }

  async splitPanel(
    projectId: string,
    panelId: string,
    splitType: "horizontal" | "vertical" = "horizontal",
    ratio: number = 0.5
  ): Promise<Panel[]> {
    await this.executeProjectHistoryCommand(projectId, {
      type: "panel.split", version: 1, label: "Split panel", input: { panel_id: panelId, split_type: splitType, ratio },
    });
    return this.listPanels(projectId);
  }

  async mergePanels(projectId: string, panelIds: string[]): Promise<Panel> {
    const before = await this.listPanels(projectId);
    const primaryId = before.find((panel) => panelIds.includes(panel.id))?.id;
    await this.executeProjectHistoryCommand(projectId, {
      type: "panel.merge", version: 1, label: "Merge panels", input: { panel_ids: panelIds },
    });
    const panels = await this.listPanels(projectId);
    const panel = panels.find((candidate) => candidate.id === primaryId);
    if (!panel) throw new Error("Merged panel was not returned");
    return panel;
  }

  async detectPagePanels(
    projectId: string,
    pageId: string,
    readingDirection: string = "ltr",
    profile: string = "AUTO"
  ): Promise<Panel[]> {
    return this.request<Panel[]>(`/api/projects/${projectId}/pages/${pageId}/detect-panels`, {
      method: "POST",
      body: JSON.stringify({ reading_direction: readingDirection, profile }),
    });
  }

  async deletePanel(projectId: string, panelId: string): Promise<void> {
    await this.executeProjectHistoryCommand(projectId, {
      type: "panel.delete", version: 1, label: "Delete panel", input: { panel_id: panelId },
    });
  }

  async reorderPanels(projectId: string, panelIds: string[]): Promise<Panel[]> {
    await this.executeProjectHistoryCommand(projectId, {
      type: "panel.reorder", version: 1, label: "Reorder panels", input: { panel_ids: panelIds },
    });
    return this.listPanels(projectId);
  }

  async confirmPanels(projectId: string): Promise<{ current_stage: string; message: string }> {
    await this.executeProjectHistoryCommand(projectId, {
      type: "panel.confirm", version: 1, label: "Confirm panels", input: {},
    });
    return { current_stage: "PANELS_DETECTED", message: "Panels confirmed" };
  }

  getPanelImageUrl(projectId: string, panelId: string): string {
    return this.resourceUrl(`/api/projects/${projectId}/panels/${panelId}/file`);
  }

  async getPanelContentSuggestions(projectId: string): Promise<{
    suggestions: Array<{ region_id: string; panel_id: string; page_id: string; text: string; bbox: number[]; reason: string }>;
    regions_checked: number;
    ocr_required: boolean;
  }> {
    return this.request(`/api/projects/${projectId}/panel-content-suggestions`);
  }

  getTextBlurPreviewUrl(projectId: string, panelId: string, regionId: string): string {
    return this.resourceUrl(`/api/projects/${projectId}/panels/${panelId}/text-blur-preview?region_id=${encodeURIComponent(regionId)}`);
  }

  async blurPanelRegion(
    projectId: string,
    panelId: string,
    box: { x: number; y: number; width: number; height: number; blur_radius?: number; feather?: number }
  ): Promise<{ success: boolean; panel_id: string; has_backup: boolean }> {
    await this.executeProjectHistoryCommand(projectId, {
      type: "panel.image.blur_region",
      version: 1,
      label: "Blur panel region",
      input: { panel_id: panelId, ...box },
    });
    return { success: true, panel_id: panelId, has_backup: true };
  }

  async blurPanelText(
    projectId: string,
    panelId: string,
    params?: { region_ids?: string[]; blur_radius?: number; feather?: number }
  ): Promise<{ success: boolean; panel_id: string; blurred_count: number }> {
    await this.executeProjectHistoryCommand(projectId, {
      type: "panel.image.blur_text",
      version: 1,
      label: "Blur panel text",
      input: { panel_id: panelId, ...(params || {}) },
    });
    const status = await this.getPanelBlurStatus(projectId, panelId);
    return { success: true, panel_id: panelId, blurred_count: status.blurred_regions_count };
  }

  async blurEntirePanel(
    projectId: string,
    panelId: string,
    blurRadius: number = 32
  ): Promise<{ success: boolean; panel_id: string }> {
    await this.executeProjectHistoryCommand(projectId, {
      type: "panel.image.blur_panel",
      version: 1,
      label: "Blur entire panel",
      input: { panel_id: panelId, blur_radius: blurRadius },
    });
    return { success: true, panel_id: panelId };
  }

  async resetPanelImage(
    projectId: string,
    panelId: string
  ): Promise<{ success: boolean; panel_id: string }> {
    const status = await this.getPanelBlurStatus(projectId, panelId);
    if (!status.is_blurred) return { success: false, panel_id: panelId };
    await this.executeProjectHistoryCommand(projectId, {
      type: "panel.image.reset", version: 1, label: "Reset panel image", input: { panel_id: panelId },
    });
    return { success: true, panel_id: panelId };
  }

  async getPanelBlurStatus(
    projectId: string,
    panelId: string
  ): Promise<{ is_blurred: boolean; has_backup: boolean; blurred_regions_count: number }> {
    return this.request<{ is_blurred: boolean; has_backup: boolean; blurred_regions_count: number }>(
      `/api/projects/${projectId}/panels/${panelId}/blur-status`
    );
  }

  async batchBlurPanels(
    projectId: string,
    params?: {
      preset?: "TOP_WATERMARK" | "BOTTOM_SUBSCRIBE" | "ENTIRE_PANEL" | "ALL_TEXT_REGIONS";
      height_px?: number;
      blur_radius?: number;
      feather?: number;
      panel_ids?: string[];
    }
  ): Promise<{ success: boolean; project_id: string; preset: string; blurred_panels_count: number; total_panels: number }> {
    const panels = await this.listPanels(projectId);
    const targetCount = params?.panel_ids?.length ?? panels.length;
    await this.executeProjectHistoryCommand(projectId, {
      type: "panel.image.batch_blur",
      version: 1,
      label: "Batch blur panels",
      input: params || {},
    });
    return {
      success: true,
      project_id: projectId,
      preset: params?.preset || "TOP_WATERMARK",
      blurred_panels_count: targetCount,
      total_panels: panels.length,
    };
  }

  async batchResetPanels(
    projectId: string,
    panelIds?: string[]
  ): Promise<{ success: boolean; project_id: string; restored_panels_count: number; total_panels: number }> {
    const panels = await this.listPanels(projectId);
    const targetCount = panelIds?.length ?? panels.length;
    await this.executeProjectHistoryCommand(projectId, {
      type: "panel.image.batch_reset",
      version: 1,
      label: "Batch reset panels",
      input: { panel_ids: panelIds },
    });
    return {
      success: true,
      project_id: projectId,
      restored_panels_count: targetCount,
      total_panels: panels.length,
    };
  }

  // OCR
  async listOCREngines(): Promise<OCREngineInfo[]> {
    return this.request<OCREngineInfo[]>("/api/ocr/engines");
  }

  async extractOCR(
    projectId: string,
    engineId: string = "mock_ocr",
    language: string = "en"
  ): Promise<{ job_id: string; message: string }> {
    return this.request<{ job_id: string; message: string }>(
      `/api/projects/${projectId}/ocr/extract`,
      {
        method: "POST",
        body: JSON.stringify({ engine_id: engineId, language }),
      }
    );
  }

  async listProjectOCR(projectId: string): Promise<OCRRecord[]> {
    return this.request<OCRRecord[]>(`/api/projects/${projectId}/ocr`);
  }

  async getPanelOCR(projectId: string, panelId: string): Promise<OCRRecord> {
    return this.request<OCRRecord>(
      `/api/projects/${projectId}/panels/${panelId}/ocr`
    );
  }

  async updateAdaptedBlock(
    projectId: string,
    panelId: string,
    blockId: string,
    data: {
      speaker?: string | null;
      text: string;
      classification?: string;
      notes?: string;
    }
  ): Promise<OCRRecord> {
    await this.executeProjectHistoryCommand(projectId, {
      type: "ocr.block.update",
      version: 1,
      label: "Update OCR block",
      input: {
        panel_id: panelId,
        block_id: blockId,
        ...data,
      },
    });
    return this.getPanelOCR(projectId, panelId);
  }

  async confirmOCR(
    projectId: string
  ): Promise<{ project_id: string; current_stage: string; message: string }> {
    await this.executeProjectHistoryCommand(projectId, {
      type: "ocr.confirm",
      version: 1,
      label: "Confirm OCR",
      input: {},
    });
    return {
      project_id: projectId,
      current_stage: "OCR_APPROVED",
      message: "OCR approved successfully.",
    };
  }

  // Text Regions (Parts 5-9, 13)
  async detectTextRegions(projectId: string, pageId?: string): Promise<TextRegion[]> {
    const query = pageId ? `?page_id=${encodeURIComponent(pageId)}` : "";
    return this.request<TextRegion[]>(`/api/projects/${projectId}/detect-text-regions${query}`, {
      method: "POST",
    });
  }

  async listTextRegions(projectId: string, pageId?: string, panelId?: string): Promise<TextRegion[]> {
    const params = new URLSearchParams();
    if (pageId) params.append("page_id", pageId);
    if (panelId) params.append("panel_id", panelId);
    const query = params.toString() ? `?${params.toString()}` : "";
    return this.request<TextRegion[]>(`/api/projects/${projectId}/text-regions${query}`);
  }

  async createManualTextRegion(
    projectId: string,
    panelId: string,
    x: number,
    y: number,
    width: number,
    height: number,
    regionType: string = "SPEECH"
  ): Promise<TextRegion> {
    const regionId = globalThis.crypto.randomUUID();
    await this.executeProjectHistoryCommand(projectId, {
      type: "ocr.region.create",
      version: 1,
      label: "Create text region",
      input: {
        region_id: regionId,
        panel_id: panelId,
        x,
        y,
        width,
        height,
        region_type: regionType,
      },
    });
    const regions = await this.listTextRegions(projectId, undefined, panelId);
    const region = regions.find((candidate) => candidate.id === regionId);
    if (!region) throw new Error("Text region was not returned after creation");
    return region;
  }

  async updateTextRegion(
    projectId: string,
    regionId: string,
    updates: {
      x?: number;
      y?: number;
      width?: number;
      height?: number;
      region_type?: string;
      status?: string;
      corrected_text?: string;
      corrected_by?: string;
      correction_status?: string;
      speaker_character_id?: string;
      speaker_confidence?: number;
      speaker_assignment_method?: string;
    }
  ): Promise<TextRegion> {
    await this.executeProjectHistoryCommand(projectId, {
      type: "ocr.region.update",
      version: 1,
      label: "Update text region",
      input: {
        region_id: regionId,
        ...updates,
      },
    });
    const regions = await this.listTextRegions(projectId);
    const region = regions.find((candidate) => candidate.id === regionId);
    if (!region) throw new Error("Text region was not returned after update");
    return region;
  }

  async deleteTextRegion(projectId: string, regionId: string): Promise<void> {
    await this.executeProjectHistoryCommand(projectId, {
      type: "ocr.region.delete",
      version: 1,
      label: "Delete text region",
      input: { region_id: regionId },
    });
  }

  async ocrSingleRegion(
    projectId: string,
    regionId: string,
    engineId: string = "mock_ocr",
    language: string = "en"
  ): Promise<TextRegion> {
    return this.request<TextRegion>(`/api/projects/${projectId}/text-regions/${regionId}/ocr`, {
      method: "POST",
      body: JSON.stringify({ engine_id: engineId, language }),
    });
  }

  async blurTextRegion(
    projectId: string,
    regionId: string,
    params?: { blur_radius?: number; feather?: number }
  ): Promise<TextRegion> {
    const query = new URLSearchParams();
    if (params?.blur_radius) query.append("blur_radius", String(params.blur_radius));
    if (params?.feather != null) query.append("feather", String(params.feather));
    const qs = query.toString() ? `?${query.toString()}` : "";
    return this.request<TextRegion>(`/api/projects/${projectId}/text-regions/${regionId}/blur${qs}`, {
      method: "POST",
    });
  }

  getTextRegionImageUrl(projectId: string, regionId: string): string {
    return this.resourceUrl(`/api/projects/${projectId}/text-regions/${regionId}/file`);
  }

  // Canonical M4 Export Contract (Part 12)
  async getCanonicalExportContract(projectId: string): Promise<CanonicalExportContract> {
    return this.request<CanonicalExportContract>(`/api/projects/${projectId}/export/contract`);
  }

  // Jobs
  async getJob(jobId: string): Promise<Job> {
    return this.request<Job>(`/api/jobs/${jobId}`);
  }

  async cancelJob(jobId: string): Promise<{ status: string; message: string }> {
    return this.request<{ status: string; message: string }>(`/api/jobs/${jobId}/cancel`, {
      method: "POST",
    });
  }

  async listProjectJobs(projectId: string): Promise<Job[]> {
    return this.request<Job[]>(`/api/jobs/project/${projectId}`);
  }

  // Adapters
  async inspectSource(source: string): Promise<SourceInspection> {
    return this.request<SourceInspection>("/api/adapters/inspect", {
      method: "POST",
      body: JSON.stringify({ source }),
    });
  }

  async listAdapters(): Promise<Array<{ id: string; name: string }>> {
    return this.request<Array<{ id: string; name: string }>>("/api/adapters");
  }

  // System
  async checkHealth(): Promise<{ status: string; app: string; version: string; instance_id?: string }> {
    return this.request<{ status: string; app: string; version: string; instance_id?: string }>("/api/system/health", { signal: AbortSignal.timeout(3000) });
  }

  async restartEngine(): Promise<{ status: string; instance_id: string }> {
    return this.request("/api/system/restart", {
      method: "POST",
      headers: { "X-PanelFlow-Control": "restart" },
    });
  }

  async browseFilesystem(path?: string, showFiles: boolean = true, extensions?: string[]): Promise<{
    current_path: string;
    parent_path: string | null;
    entries: Array<{ name: string; path: string; is_dir: boolean; size: number }>;
  }> {
    return this.request<{
      current_path: string;
      parent_path: string | null;
      entries: Array<{ name: string; path: string; is_dir: boolean; size: number }>;
    }>("/api/system/browse", {
      method: "POST",
      body: JSON.stringify({ path, show_files: showFiles, extensions }),
    });
  }

  async openProjectFolder(projectId: string): Promise<{ opened: boolean; path: string }> {
    return this.request<{ opened: boolean; path: string }>(`/api/system/projects/${projectId}/open-folder`, {
      method: "POST",
    });
  }

  // Story & Narrative IR (Milestone 4)
  async listLLMProviders(): Promise<LLMProviderInfo[]> {
    return this.request<LLMProviderInfo[]>("/api/llm/providers");
  }

  async analyzeStory(projectId: string, providerId?: string): Promise<{ job_id: string; message: string }> {
    return this.request<{ job_id: string; message: string }>(`/api/projects/${projectId}/story/analyze`, {
      method: "POST",
      body: JSON.stringify({ provider_id: providerId }),
    });
  }

  async getNarrative(projectId: string): Promise<NarrativeDocument> {
    return this.request<NarrativeDocument>(`/api/projects/${projectId}/narrative`);
  }

  async confirmStory(projectId: string): Promise<{ project_id: string; current_stage: string; message: string }> {
    await this.executeProjectHistoryCommand(projectId, {
      type: "story.confirm",
      version: 1,
      label: "Confirm story",
      input: {},
    });
    return {
      project_id: projectId,
      current_stage: "STORY_APPROVED",
      message: "Narrative IR approved successfully.",
    };
  }

  async listCharacters(projectId: string): Promise<CharacterEntity[]> {
    return this.request<CharacterEntity[]>(`/api/projects/${projectId}/characters`);
  }

  async updateCharacter(
    projectId: string,
    characterId: string,
    updates: {
      display_name?: string;
      canonical_name?: string;
      role?: string;
      aliases?: string[];
      description?: string;
      status?: string;
      reference_asset_id?: string | null;
      generation_params?: Record<string, unknown>;
      proposed_changes?: Record<string, unknown>;
      change_status?: "NONE" | "PENDING_REVIEW" | "APPROVED" | "REJECTED";
    }
  ): Promise<CharacterEntity | undefined> {
    await this.executeProjectHistoryCommand(projectId, {
      type: "character.update",
      version: 1,
      label: "Update character",
      input: {
        character_id: characterId,
        ...updates,
      },
    });
    const chars = await this.listCharacters(projectId);
    return chars.find(c => c.character_id === characterId || (c as any).id === characterId);
  }

  async mergeCharacters(projectId: string, sourceCharacterId: string, targetCharacterId: string): Promise<any> {
    await this.executeProjectHistoryCommand(projectId, {
      type: "character.merge",
      version: 1,
      label: "Merge characters",
      input: {
        source_character_id: sourceCharacterId,
        target_character_id: targetCharacterId,
      },
    });
    const chars = await this.listCharacters(projectId);
    const target = chars.find(c => c.character_id === targetCharacterId || (c as any).id === targetCharacterId);
    return {
      id: targetCharacterId,
      display_name: target?.display_name || "",
      aliases: target?.aliases || [],
      message: "Characters merged successfully.",
    };
  }

  async splitCharacter(
    projectId: string,
    characterId: string,
    newName: string,
    panelIds: string[]
  ): Promise<any> {
    const newCharId = `char_${globalThis.crypto.randomUUID().replace(/-/g, "").slice(0, 8)}`;
    await this.executeProjectHistoryCommand(projectId, {
      type: "character.split",
      version: 1,
      label: "Split character",
      input: {
        character_id: characterId,
        new_name: newName,
        panel_ids: panelIds,
        new_character_id: newCharId,
      },
    });
    const chars = await this.listCharacters(projectId);
    const created = chars.find(c => c.character_id === newCharId || (c as any).id === newCharId || c.display_name === newName);
    return {
      id: created?.character_id || newCharId,
      character_id: created?.character_id || newCharId,
      display_name: newName,
      message: "Character identity split successfully.",
    };
  }

  async listScenes(projectId: string): Promise<SceneEntity[]> {
    return this.request<SceneEntity[]>(`/api/projects/${projectId}/scenes`);
  }

  async mergeScenes(projectId: string, sceneId1: string, sceneId2: string): Promise<any> {
    await this.executeProjectHistoryCommand(projectId, {
      type: "scene.merge",
      version: 1,
      label: "Merge scenes",
      input: {
        scene_id_1: sceneId1,
        scene_id_2: sceneId2,
      },
    });
    const scenes = await this.listScenes(projectId);
    const merged = scenes.find(s => s.scene_id === sceneId1 || (s as any).id === sceneId1);
    return {
      id: sceneId1,
      scene_id: sceneId1,
      title: merged?.title || "",
      message: "Scenes merged successfully.",
    };
  }

  // Script Adaptation (Milestone 4 - Layer C)
  async waitForWorkflowJob(jobId: string, onProgress?: (job: Job) => void): Promise<Job> {
    for (;;) {
      const job = await this.getJob(jobId);
      onProgress?.(job);
      if (job.status === "SUCCEEDED") return job;
      if (job.status === "FAILED" || job.status === "CANCELLED") throw new Error(job.error || job.message);
      await new Promise(resolve => setTimeout(resolve, 1500));
    }
  }

  async generateScriptJob(projectId: string, adaptationProfile: string): Promise<{job_id: string}> {
    return this.request(`/api/projects/${projectId}/scripts/generate-job`, {
      method: "POST", body: JSON.stringify({ adaptation_profile: adaptationProfile }),
    });
  }

  async generateAudioJob(projectId: string, voiceCasting?: Record<string, string>): Promise<{job_id: string}> {
    return this.request(`/api/projects/${projectId}/audio/generate-job`, {
      method: "POST",
      body: JSON.stringify({ voice_casting: voiceCasting }),
    });
  }

  async generateScript(projectId: string, adaptationProfile: AdaptationProfile | string = "FAITHFUL"): Promise<VideoScript> {
    return this.request<VideoScript>(`/api/projects/${projectId}/scripts/generate`, {
      method: "POST",
      body: JSON.stringify({
        adaptation_profile: adaptationProfile,
      }),
    });
  }

  async getScript(projectId: string): Promise<VideoScript> {
    return this.request<VideoScript>(`/api/projects/${projectId}/scripts`);
  }

  async updateScriptSegment(
    projectId: string,
    scriptId: string,
    segmentId: string,
    updates: {
      text?: string;
      speaker_character_id?: string;
      emotion?: string;
      intensity?: number;
      estimated_duration?: number;
    }
  ): Promise<any> {
    await this.executeProjectHistoryCommand(projectId, {
      type: "script.segment.update",
      version: 1,
      label: "Update script segment",
      input: {
        script_id: scriptId,
        segment_id: segmentId,
        ...updates,
      },
    });
    const script = await this.getScript(projectId);
    const seg = script?.segments?.find((s: any) => s.segment_id === segmentId || s.id === segmentId);
    return {
      id: segmentId,
      text: seg?.text,
      estimated_duration: seg?.estimated_duration,
      manual_override: true,
    };
  }

  async editScriptSegment(projectId: string, scriptId: string, segmentId: string, action: string): Promise<VideoScript> {
    return this.request<VideoScript>(`/api/projects/${projectId}/scripts/${scriptId}/segments/${segmentId}/action`, {
      method: "POST", body: JSON.stringify({ action }),
    });
  }

  async validateScript(projectId: string, scriptId: string): Promise<ScriptValidationReport> {
    return this.request<ScriptValidationReport>(`/api/projects/${projectId}/scripts/${scriptId}/validate`, {
      method: "POST",
    });
  }

  async approveScript(projectId: string, scriptId: string): Promise<{ script_id: string; status: string; message: string }> {
    await this.executeProjectHistoryCommand(projectId, {
      type: "script.approve",
      version: 1,
      label: "Approve script",
      input: {
        script_id: scriptId,
      },
    });
    return {
      script_id: scriptId,
      status: "APPROVED",
      message: "Script approved! Project advanced to SCRIPT_APPROVED.",
    };
  }

  // ---------------------------------------------------------------------------
  // Audio Director (Milestone 6 & 8)
  // ---------------------------------------------------------------------------
  async getAudioTimeline(projectId: string): Promise<AudioTimelineResponse> {
    return this.request<AudioTimelineResponse>(`/api/projects/${projectId}/audio/timeline`);
  }

  async generateAudio(
    projectId: string,
    voiceCasting?: Record<string, string>
  ): Promise<AudioTimelineResponse> {
    return this.request<AudioTimelineResponse>(`/api/projects/${projectId}/audio/generate`, {
      method: "POST",
      body: JSON.stringify({ voice_casting: voiceCasting }),
    });
  }

  async regenerateAudioSegment(
    projectId: string,
    segmentId: string
  ): Promise<{ status: string; segment_id: string; total_duration: number; timeline: MasterAudioTimeline }> {
    return this.request<any>(`/api/projects/${projectId}/audio/regenerate-segment`, {
      method: "POST",
      body: JSON.stringify({ segment_id: segmentId }),
    });
  }

  async approveAudio(projectId: string): Promise<{ approved: boolean; message: string }> {
    await this.executeProjectHistoryCommand(projectId, {
      type: "audio.approve",
      version: 1,
      label: "Approve audio",
      input: {},
    });
    return { approved: true, message: "Audio timeline approved" };
  }

  async acceptAudioDraft(projectId: string, draft: any): Promise<any> {
    await this.executeProjectHistoryCommand(projectId, {
      type: "audio.draft.accept",
      version: 1,
      label: "Accept audio draft",
      input: { draft },
    });
    return this.getAudioTimeline(projectId);
  }

  async acceptSynthesizedAudio(projectId: string, result: any): Promise<any> {
    await this.executeProjectHistoryCommand(projectId, {
      type: "audio.synthesized.accept",
      version: 1,
      label: "Accept synthesized audio",
      input: { result },
    });
    return this.getAudioTimeline(projectId);
  }

  async approveAudioTimeline(projectId: string): Promise<{ approved: boolean; message: string }> {
    return this.approveAudio(projectId);
  }

  getAudioFileUrl(projectId: string, filePath: string): string {
    if (/^https?:\/\//i.test(filePath)) return filePath;

    let resolvedPath = filePath;
    const streamedRoute = `/api/projects/${projectId}/audio/file`;
    if (filePath.startsWith(streamedRoute)) {
      const parsed = new URL(filePath, this.baseUrl);
      resolvedPath = parsed.searchParams.get("path") || filePath;
    } else {
      const dialoguePrefix = `/api/projects/${projectId}/audio/dialogue/`;
      if (filePath.startsWith(dialoguePrefix)) {
        resolvedPath = `audio/dialogue/${decodeURIComponent(filePath.slice(dialoguePrefix.length))}`;
      }
    }

    return `${this.resourceUrl(`/api/projects/${projectId}/audio/file`)}?path=${encodeURIComponent(resolvedPath)}`;
  }

  async getAudioProviders(): Promise<{
    primary_provider: string;
    providers: Array<{
      id: string;
      name: string;
      location: string;
      license: string;
      commercial_use: string;
      status: string;
      notes?: string;
      device?: string;
      capabilities?: any;
      voices?: any[];
    }>;
  }> {
    return this.request<any>("/api/audio/providers");
  }

  async draftNarration(
    projectId: string,
    scenes: any[],
    providerId?: string,
    modelName?: string,
    mode?: "full" | "page_only" | "panel_only" | "harmonize",
    targetPageSequence?: number,
    existingPageScripts?: Record<string, any>,
    signal?: AbortSignal
  ): Promise<any> {
    return this.request<any>(`/api/projects/${projectId}/narration/draft`, {
      method: "POST",
      signal,
      body: JSON.stringify({
        scenes,
        provider_id: providerId,
        model_name: modelName,
        mode: mode || "full",
        target_page_sequence: targetPageSequence,
        existing_page_scripts: existingPageScripts,
      }),
    });
  }

  async draftNarrationJob(
    projectId: string,
    scenes: any[],
    providerId?: string,
    modelName?: string,
    mode?: "full" | "page_only" | "panel_only" | "harmonize",
    targetPageSequence?: number,
    existingPageScripts?: Record<string, any>
  ): Promise<{ job_id: string; status: string; message: string }> {
    return this.request<{ job_id: string; status: string; message: string }>(
      `/api/projects/${projectId}/narration/draft-job`,
      {
        method: "POST",
        body: JSON.stringify({
          scenes,
          provider_id: providerId,
          model_name: modelName,
          mode: mode || "full",
          target_page_sequence: targetPageSequence,
          existing_page_scripts: existingPageScripts,
        }),
      }
    );
  }

  async getNarrationPlan(projectId: string): Promise<any> {
    return this.request<any>(`/api/projects/${projectId}/narration/plan`);
  }

  async harmonizeNarration(
    projectId: string,
    scenes: any[],
    pageScripts: Record<string, any>,
    providerId?: string,
    modelName?: string
  ): Promise<any> {
    return this.request<any>(`/api/projects/${projectId}/narration/harmonize`, {
      method: "POST",
      body: JSON.stringify({
        scenes,
        page_scripts: pageScripts,
        provider_id: providerId,
        model_name: modelName,
      }),
    });
  }

  async analyzePanelVision(
    projectId: string,
    panelId: string,
    modelName?: string
  ): Promise<{ panel_id: string; visual_description: string; model_used: string }> {
    return this.request<{ panel_id: string; visual_description: string; model_used: string }>(
      `/api/projects/${projectId}/panels/${panelId}/analyze-vision${modelName ? `?model_name=${encodeURIComponent(modelName)}` : ""}`,
      {
        method: "POST",
      }
    );
  }

  async synthesizeNarrationSegment(
    projectId: string,
    params: {
      segment_id: string;
      text: string;
      voice?: string;
      emotion?: string;
      intensity?: number;
      speed?: number;
      text_revision?: number;
      content_hash?: string;
      force?: boolean;
    }
  ): Promise<{
    success: boolean;
    segment_id: string;
    audio_path: string;
    audio_url: string;
    measured_duration_sec: number;
    sample_rate: number;
    channels: number;
    generated_audio_revision: number;
    content_hash?: string;
  }> {
    return this.request<any>(`/api/projects/${projectId}/narration/synthesize-segment`, {
      method: "POST",
      body: JSON.stringify(params),
    });
  }

  async synthesizeNarrationBatch(
    projectId: string,
    segments: Array<{
      segment_id: string;
      text: string;
      voice?: string;
      emotion?: string;
      intensity?: number;
      speed?: number;
      text_revision?: number;
      content_hash?: string;
      force?: boolean;
    }>
  ): Promise<{
    project_id: string;
    results: Array<{
      id: string;
      success: boolean;
      audio_path?: string;
      audio_url?: string;
      duration?: number;
      error?: string;
    }>;
  }> {
    return this.request<any>(`/api/projects/${projectId}/narration/synthesize-batch`, {
      method: "POST",
      body: JSON.stringify({ segments }),
    });
  }

  // ---------------------------------------------------------------------------
  // Motion Director (Milestone 6 & 8)
  // ---------------------------------------------------------------------------
  async getMotionTimeline(projectId: string): Promise<MotionTimelineResponse> {
    return this.request<MotionTimelineResponse>(`/api/projects/${projectId}/motion/timeline`);
  }

  async planMotion(
    projectId: string,
    stylePreset: string = "cinematic",
    overrides?: Record<string, any>
  ): Promise<MotionTimelineResponse> {
    return this.request<MotionTimelineResponse>(`/api/projects/${projectId}/motion/plan`, {
      method: "POST",
      body: JSON.stringify({
        style_preset: stylePreset,
        overrides,
      }),
    });
  }

  async applyMotionOverrides(
    projectId: string,
    overrides: Record<string, any>
  ): Promise<MotionTimelineResponse> {
    await this.executeProjectHistoryCommand(projectId, {
      type: "motion.overrides",
      version: 1,
      label: "Set shot overrides",
      input: { overrides },
    });
    return this.getMotionTimeline(projectId);
  }

  async setShotOverrides(
    projectId: string,
    overrides: Record<string, any>
  ): Promise<MotionTimelineResponse> {
    return this.applyMotionOverrides(projectId, overrides);
  }

  async approveMotion(projectId: string): Promise<{ approved: boolean; message: string }> {
    await this.executeProjectHistoryCommand(projectId, {
      type: "motion.approve",
      version: 1,
      label: "Approve motion",
      input: {},
    });
    return { approved: true, message: "Motion timeline approved" };
  }

  async approveMotionTimeline(projectId: string): Promise<{ approved: boolean; message: string }> {
    return this.approveMotion(projectId);
  }

  async acceptMotionPlan(projectId: string, plan: any): Promise<MotionTimelineResponse> {
    await this.executeProjectHistoryCommand(projectId, {
      type: "motion.plan.accept",
      version: 1,
      label: "Accept motion plan",
      input: { plan },
    });
    return this.getMotionTimeline(projectId);
  }

  // ---------------------------------------------------------------------------
  // Production Renderer (Milestone 7 & 8)
  // ---------------------------------------------------------------------------
  async startRender(
    projectId: string,
    options: {
      profileName?: string;
      customOutputPath?: string;
      subtitleEnabled?: boolean;
      bgmVolumeDb?: number;
      dialogueGainDb?: number;
      isDraft?: boolean;
      timelineData?: any;
    } = {}
  ): Promise<RenderJob> {
    return this.request<RenderJob>(`/api/projects/${projectId}/render/jobs`, {
      method: "POST",
      body: JSON.stringify({
        profile_name: options.profileName || "standard_1080p",
        custom_output_path: options.customOutputPath,
        subtitle_enabled: options.subtitleEnabled ?? false,
        bgm_volume_db: options.bgmVolumeDb ?? -10.0,
        dialogue_gain_db: options.dialogueGainDb ?? 0.0,
        is_draft: options.isDraft ?? false,
        timeline_data: options.timelineData,
      }),
    });
  }

  async preflightTimelineRender(projectId: string, timelineData?: any): Promise<any> {
    return this.request<any>(`/api/projects/${projectId}/render/preflight`, {
      method: "POST",
      body: JSON.stringify({ timeline_data: timelineData }),
    });
  }

  async getRenderProfiles(): Promise<{ profiles: any[] }> {
    return this.request<{ profiles: any[] }>(`/api/render/profiles`);
  }

  async listRenders(projectId: string): Promise<RenderJob[]> {
    return this.request<RenderJob[]>(`/api/projects/${projectId}/render/jobs`);
  }

  async getRender(projectId: string, renderId: string): Promise<RenderJob> {
    return this.request<RenderJob>(`/api/projects/${projectId}/render/jobs/${renderId}`);
  }

  async cancelRender(projectId: string, renderId: string): Promise<{ cancelled: boolean; render_id: string }> {
    return this.request<{ cancelled: boolean; render_id: string }>(`/api/projects/${projectId}/render/jobs/${renderId}/cancel`, {
      method: "POST",
    });
  }

  getRenderVideoUrl(projectId: string, renderId: string): string {
    return this.resourceUrl(`/api/projects/${projectId}/render/jobs/${renderId}/output`);
  }

  getRenderContactSheetUrl(projectId: string, renderId: string): string {
    return this.resourceUrl(`/api/projects/${projectId}/render/jobs/${renderId}/contact-sheet`);
  }

  getRenderAuditSampleUrl(projectId: string, renderId: string, sampleIndex: number): string {
    return this.resourceUrl(`/api/projects/${projectId}/render/jobs/${renderId}/samples/${sampleIndex}`);
  }

  async getRenderValidation(projectId: string, renderId: string): Promise<RenderValidationReport> {
    return this.request<RenderValidationReport>(`/api/projects/${projectId}/render/jobs/${renderId}/validation`);
  }

  subscribeRenderEvents(
    onProgress: (event: any) => void,
    onError?: (error: any) => void
  ): () => void {
    const eventSource = new EventSource(this.resourceUrl("/api/render/events"));
    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        onProgress(data);
      } catch (e) {
        // Heartbeat or malformed comment
      }
    };
    eventSource.onerror = (err) => {
      if (onError) onError(err);
    };
    return () => {
      eventSource.close();
    };
  }

  // ---------------------------------------------------------------------------
  // System & Provider Health (Milestone 8)
  // ---------------------------------------------------------------------------
  async getProviderHealth(): Promise<SystemProvidersResponse> {
    return this.request<SystemProvidersResponse>("/api/system/providers");
  }

  async getHardwareDiagnostics(): Promise<HardwareDiagnostics> {
    return this.request<HardwareDiagnostics>("/api/system/hardware");
  }

  async exportDiagnostics(): Promise<SanitizedDiagnostics> {
    return this.request<SanitizedDiagnostics>("/api/system/diagnostics");
  }

  async openPath(path: string, selectFile: boolean = false): Promise<{ opened: boolean; path: string }> {
    return this.request<{ opened: boolean; path: string }>("/api/system/open-path", {
      method: "POST",
      body: JSON.stringify({ path, select_file: selectFile }),
    });
  }

  // ---------------------------------------------------------------------------
  // Ollama Configuration & Capabilities
  // ---------------------------------------------------------------------------
  async getOllamaConfig(): Promise<OllamaConfig> {
    return this.request<OllamaConfig>("/api/system/ollama/config");
  }

  async saveOllamaConfig(config: Partial<OllamaConfig> & { auth_token?: string }): Promise<OllamaConfig> {
    return this.request<OllamaConfig>("/api/system/ollama/config", {
      method: "POST",
      body: JSON.stringify(config),
    });
  }

  async getOllamaModels(): Promise<OllamaModelsResponse> {
    return this.request<OllamaModelsResponse>("/api/system/ollama/models");
  }

  async testOllamaConnection(params: { endpoint_url?: string; is_remote?: boolean; auth_token?: string } = {}): Promise<any> {
    return this.request<any>("/api/system/ollama/test", {
      method: "POST",
      body: JSON.stringify(params),
    });
  }

  // ---------------------------------------------------------------------------
  // Cloud & Free LLM Gateway (OpenRouter, Groq, Custom OpenAI-Compatible)
  // ---------------------------------------------------------------------------
  async getCloudLLMConfig(): Promise<CloudLLMConfig> {
    return this.request<CloudLLMConfig>("/api/system/llm/cloud-config");
  }

  async saveCloudLLMConfig(config: CloudLLMConfig): Promise<CloudLLMConfig> {
    return this.request<CloudLLMConfig>("/api/system/llm/cloud-config", {
      method: "POST",
      body: JSON.stringify(config),
    });
  }

  async testCloudLLMConnection(params: CloudLLMTestRequest): Promise<CloudLLMTestResponse> {
    return this.request<CloudLLMTestResponse>("/api/system/llm/cloud-test", {
      method: "POST",
      body: JSON.stringify(params),
    });
  }

  async chatWithCloudLLM(params: CloudLLMChatRequest): Promise<CloudLLMChatResponse> {
    return this.request<CloudLLMChatResponse>("/api/system/llm/cloud-chat", {
      method: "POST",
      body: JSON.stringify(params),
    });
  }

  async getAllAvailableLLMProviders(): Promise<AvailableLLMProvidersResponse> {
    return this.request<AvailableLLMProvidersResponse>("/api/system/llm/providers/all");
  }

  async getGlobalLLMSettings(): Promise<GlobalLLMSettings> {
    return this.request<GlobalLLMSettings>("/api/system/llm/global-settings");
  }

  async saveGlobalLLMSettings(settings: SaveGlobalLLMSettingsRequest): Promise<any> {
    return this.request<any>("/api/system/llm/global-settings", {
      method: "POST",
      body: JSON.stringify(settings),
    });
  }

  // ---------------------------------------------------------------------------
  // System Resource Telemetry & Concurrency
  // ---------------------------------------------------------------------------
  async getSystemResources(): Promise<SystemResourcesResponse> {
    return this.request<SystemResourcesResponse>("/api/system/resources");
  }

  async setConcurrencySettings(params: { concurrency_mode: string; max_gpu_concurrency: number }): Promise<any> {
    return this.request<any>("/api/system/concurrency", {
      method: "POST",
      body: JSON.stringify(params),
    });
  }

  async runConcurrencyBenchmark(model?: string): Promise<any> {
    return this.request<any>("/api/system/benchmark", {
      method: "POST",
      body: JSON.stringify({ model }),
    });
  }

  // ---------------------------------------------------------------------------
  // Visual Storyboard & Alignment
  // ---------------------------------------------------------------------------
  async getStoryboard(projectId: string): Promise<StoryboardDocument> {
    return this.request<StoryboardDocument>(`/api/projects/${projectId}/storyboard`);
  }

  async updateStoryboardSegment(
    projectId: string,
    segmentId: string,
    update: StoryboardSegmentUpdate
  ): Promise<StoryboardSegment> {
    await this.executeProjectHistoryCommand(projectId, {
      type: "storyboard.segment.update",
      version: 1,
      label: "Update storyboard segment",
      input: {
        segment_id: segmentId,
        updates: update,
      },
    });
    const storyboard = await this.getStoryboard(projectId);
    const seg = storyboard.segments.find(s => s.segment_id === segmentId);
    if (!seg) throw new Error("Storyboard segment was not found after update");
    return seg;
  }

  async realignStoryboard(projectId: string): Promise<StoryboardDocument> {
    await this.executeProjectHistoryCommand(projectId, {
      type: "storyboard.realign",
      version: 1,
      label: "Realign storyboard",
      input: {},
    });
    return this.getStoryboard(projectId);
  }

  // ---------------------------------------------------------------------------
  // Multi-Project Job Queue
  // ---------------------------------------------------------------------------
  async listAllJobs(status?: string, projectId?: string, limit: number = 50): Promise<Job[]> {
    const params = new URLSearchParams();
    if (status) params.append("status", status);
    if (projectId) params.append("project_id", projectId);
    params.append("limit", limit.toString());
    return this.request<Job[]>(`/api/jobs?${params.toString()}`);
  }

  async listJobs(status?: string, projectId?: string, limit: number = 50): Promise<Job[]> {
    return this.listAllJobs(status, projectId, limit);
  }

  async retryJob(jobId: string): Promise<any> {
    return this.request<any>(`/api/jobs/${jobId}/retry`, {
      method: "POST",
    });
  }

  // ---------------------------------------------------------------------------
  // Chapter 9: Story-Aware AI Music & Sound Design
  // ---------------------------------------------------------------------------
  async getMusicServiceHealth(): Promise<{ service: string; health: any; gpu: any; recommended_tier: string }> {
    return this.request<{ service: string; health: any; gpu: any; recommended_tier: string }>("/api/music/health");
  }

  async getSFXCapabilityReport(): Promise<SFXCapabilityReport> {
    return this.request<SFXCapabilityReport>("/api/music/sfx/capability");
  }

  async getProjectMusicPlan(projectId: string, forceReplan: boolean = false): Promise<MusicDirectionPlan> {
    return this.request<MusicDirectionPlan>(`/api/projects/${projectId}/music/plan?force_replan=${forceReplan}`);
  }

  async saveProjectMusicPlan(projectId: string, plan: MusicDirectionPlan): Promise<{ saved: boolean; plan_id: string; updated_at: number }> {
    return this.request<{ saved: boolean; plan_id: string; updated_at: number }>(`/api/projects/${projectId}/music/plan`, {
      method: "POST",
      body: JSON.stringify(plan),
    });
  }

  async updateCuePrompt(projectId: string, cueId: string, prompt: string, bpm?: number, intensity?: number): Promise<MusicCuePlan> {
    return this.request<MusicCuePlan>(`/api/projects/${projectId}/music/plan/cue-prompt`, {
      method: "POST",
      body: JSON.stringify({ cue_id: cueId, prompt, bpm, intensity }),
    });
  }

  async generateMusic(projectId: string, req: MusicGenerationRequest): Promise<MusicTakeRecord> {
    return this.request<MusicTakeRecord>(`/api/projects/${projectId}/music/generate`, {
      method: "POST",
      body: JSON.stringify(req),
    });
  }

  async listProjectMusicTakes(projectId: string, cueId?: string): Promise<MusicTakeRecord[]> {
    const url = cueId
      ? `/api/projects/${projectId}/music/takes?cue_id=${encodeURIComponent(cueId)}`
      : `/api/projects/${projectId}/music/takes`;
    return this.request<MusicTakeRecord[]>(url);
  }

  async selectMusicTake(projectId: string, cueId: string, takeId: string): Promise<MusicDirectionPlan> {
    return this.request<MusicDirectionPlan>(`/api/projects/${projectId}/music/takes/${takeId}/select`, {
      method: "POST",
      body: JSON.stringify({ cue_id: cueId, take_id: takeId }),
    });
  }

  async addTakeToTimeline(
    projectId: string,
    takeId: string,
    params: { cue_id: string; volume?: number; fade_in_sec?: number; fade_out_sec?: number; loop?: boolean; start_time_sec?: number }
  ): Promise<any> {
    return this.request<any>(`/api/projects/${projectId}/music/takes/${takeId}/add-to-timeline`, {
      method: "POST",
      body: JSON.stringify(params),
    });
  }

  // ComfyUI image generation
  async listApprovedComfyWorkflows(): Promise<{ workflows: ComfyWorkflowInfo[]; errors: string[] }> {
    return this.request<{ workflows: ComfyWorkflowInfo[]; errors: string[] }>("/api/comfyui/workflow-registry");
  }

  async generateComfyImage(projectId: string, request: ComfyImageRequest): Promise<{ job_id: string; status: string; workflow_id: string }> {
    return this.request<{ job_id: string; status: string; workflow_id: string }>(`/api/projects/${projectId}/comfyui/image`, {
      method: "POST",
      body: JSON.stringify(request),
    });
  }

  async listGeneratedAssets(projectId: string): Promise<{ assets: GeneratedAsset[] }> {
    return this.request<{ assets: GeneratedAsset[] }>(`/api/projects/${projectId}/assets`);
  }

  getGeneratedAssetUrl(projectId: string, assetId: string): string {
    return this.resourceUrl(`/api/projects/${projectId}/assets/${assetId}/file`);
  }

  // YouTube Packaging & ComfyUI Thumbnail Research
  async getYoutubePackaging(projectId: string, refresh = false, profileName?: string): Promise<YouTubePackagingData> {
    const params = new URLSearchParams();
    if (refresh) params.set("refresh", "true");
    if (profileName) params.set("profile_name", profileName);
    const query = params.toString() ? `?${params.toString()}` : "";
    return this.request<YouTubePackagingData>(`/api/projects/${projectId}/youtube/packaging${query}`);
  }

  async generateYoutubePackaging(projectId: string, request: YouTubePackagingGenerateRequest): Promise<YouTubePackagingData> {
    return this.request<YouTubePackagingData>(`/api/projects/${projectId}/youtube/packaging/generate`, {
      method: "POST",
      body: JSON.stringify(request),
    });
  }

  // End-to-End Pipeline Auto-Pilot
  async startAutoPilot(projectId: string, request: AutoPilotStartRequest = {}): Promise<AutoPilotStatusResponse> {
    return this.request<AutoPilotStatusResponse>(`/api/projects/${projectId}/autopilot/run`, {
      method: "POST",
      body: JSON.stringify(request),
    });
  }

  async getAutoPilotStatus(projectId: string): Promise<AutoPilotStatusResponse> {
    return this.request<AutoPilotStatusResponse>(`/api/projects/${projectId}/autopilot/status`);
  }

  async cancelAutoPilot(projectId: string): Promise<{ cancelled: boolean; project_id: string }> {
    return this.request<{ cancelled: boolean; project_id: string }>(`/api/projects/${projectId}/autopilot/cancel`, {
      method: "POST",
    });
  }

  // ---------------------------------------------------------------------------
  // Setup & Model Onboarding Engine
  // ---------------------------------------------------------------------------
  async locateFfmpeg(): Promise<{ found: boolean; ffmpeg_path: string | null; ffprobe_path: string | null; version: string | null; injected_into_path: boolean }> {
    return this.request<{ found: boolean; ffmpeg_path: string | null; ffprobe_path: string | null; version: string | null; injected_into_path: boolean }>("/api/system/locate-ffmpeg", {
      method: "POST",
    });
  }

  async provisionVoices(): Promise<{ success: boolean; voice_directory: string; copied_count: number; total_profiles: number; profiles: any[] }> {
    return this.request<{ success: boolean; voice_directory: string; copied_count: number; total_profiles: number; profiles: any[] }>("/api/system/provision-voices", {
      method: "POST",
    });
  }

  async installPlaywrightBrowsers(): Promise<{ status: string; message: string }> {
    return this.request<{ status: string; message: string }>("/api/system/install-playwright", {
      method: "POST",
    });
  }

  async getPlaywrightInstallStatus(): Promise<{ status: string; log_lines: string[]; error_message: string | null; exit_code: number | null }> {
    return this.request<{ status: string; log_lines: string[]; error_message: string | null; exit_code: number | null }>("/api/system/install-playwright/status");
  }

  async pullOllamaModel(model: string, endpointUrl?: string): Promise<{ status: string; model: string; message?: string }> {
    return this.request<{ status: string; model: string; message?: string }>("/api/system/ollama/pull", {
      method: "POST",
      body: JSON.stringify({ model, endpoint_url: endpointUrl }),
    });
  }

  async getOllamaPullStatus(): Promise<{ status: string; model_name: string; status_text: string; completed_bytes: number; total_bytes: number; percent: number; error_message: string | null }> {
    return this.request<{ status: string; model_name: string; status_text: string; completed_bytes: number; total_bytes: number; percent: number; error_message: string | null }>("/api/system/ollama/pull/status");
  }
}

export const api = new PanelFlowApiClient();


