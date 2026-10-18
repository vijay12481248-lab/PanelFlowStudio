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
} from "@panelflow/shared-types";


export interface CreateProjectParams {
  title: string;
  source_type: SourceType;
  source_url?: string;
  rights_status: RightsStatus;
  license_info?: string;
  source_metadata?: Record<string, any>;
  settings?: Record<string, any>;
}

export class PanelFlowApiClient {
  private baseUrl: string;

  constructor(baseUrl: string = "http://127.0.0.1:8765") {
    this.baseUrl = baseUrl.replace(/\/$/, "");
  }

  private async request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`;
    const headers: Record<string, string> = {
      Accept: "application/json",
      ...(options.headers as Record<string, string> || {}),
    };

    if (options.body && typeof options.body === "string" && !headers["Content-Type"]) {
      headers["Content-Type"] = "application/json";
    }

    const response = await fetch(url, {
      ...options,
      headers,
    });

    if (!response.ok) {
      let errorMsg = `HTTP Error ${response.status}: ${response.statusText}`;
      try {
        const errJson = await response.json();
        if (errJson.detail) {
          errorMsg = typeof errJson.detail === "string" ? errJson.detail : JSON.stringify(errJson.detail);
        }
      } catch {
        // use fallback
      }
      throw new Error(errorMsg);
    }

    if (response.status === 204) {
      return null as T;
    }

    return response.json();
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

  async getStoryEditorState(projectId: string): Promise<{ state: any | null }> {
    return this.request<{ state: any | null }>(`/api/projects/${projectId}/story-editor`);
  }

  async saveStoryEditorState(projectId: string, state: any): Promise<{ state: any; updated_at: string }> {
    return this.request<{ state: any; updated_at: string }>(`/api/projects/${projectId}/story-editor`, {
      method: "PUT",
      body: JSON.stringify({ state }),
    });
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
    return this.request<Project>(`/api/projects/${projectId}/confirm`, {
      method: "POST",
    });
  }

  async getManifest(projectId: string): Promise<AcquisitionManifest> {
    return this.request<AcquisitionManifest>(`/api/projects/${projectId}/manifest`);
  }

  // Pages
  async listPages(projectId: string): Promise<Page[]> {
    return this.request<Page[]>(`/api/projects/${projectId}/pages`);
  }

  async reorderPages(projectId: string, pageIds: string[]): Promise<Page[]> {
    return this.request<Page[]>(`/api/projects/${projectId}/pages/reorder`, {
      method: "POST",
      body: JSON.stringify({ page_ids: pageIds }),
    });
  }

  async deletePage(projectId: string, pageId: string): Promise<void> {
    return this.request<void>(`/api/projects/${projectId}/pages/${pageId}`, {
      method: "DELETE",
    });
  }

  async rotatePage(projectId: string, pageId: string, degrees: number = 90): Promise<Page> {
    return this.request<Page>(`/api/projects/${projectId}/pages/${pageId}/rotate`, {
      method: "POST",
      body: JSON.stringify({ degrees }),
    });
  }

  getPageImageUrl(projectId: string, pageId: string): string {
    return `${this.baseUrl}/api/projects/${projectId}/pages/${pageId}/file`;
  }

  getNormalizedPageImageUrl(projectId: string, pageId: string): string {
    return `${this.baseUrl}/api/projects/${projectId}/pages/${pageId}/normalized-file`;
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
    return this.request<Panel>(`/api/projects/${projectId}/panels`, {
      method: "POST",
      body: JSON.stringify({ page_id: pageId, x, y, width, height, panel_type: panelType }),
    });
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
    return this.request<Panel>(`/api/projects/${projectId}/panels/${panelId}`, {
      method: "PUT",
      body: JSON.stringify({ x, y, width, height, status, panel_type: panelType }),
    });
  }

  async splitPanel(
    projectId: string,
    panelId: string,
    splitType: "horizontal" | "vertical" = "horizontal",
    ratio: number = 0.5
  ): Promise<Panel[]> {
    return this.request<Panel[]>(`/api/projects/${projectId}/panels/${panelId}/split`, {
      method: "POST",
      body: JSON.stringify({ split_type: splitType, ratio }),
    });
  }

  async mergePanels(projectId: string, panelIds: string[]): Promise<Panel> {
    return this.request<Panel>(`/api/projects/${projectId}/panels/merge`, {
      method: "POST",
      body: JSON.stringify({ panel_ids: panelIds }),
    });
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
    return this.request<void>(`/api/projects/${projectId}/panels/${panelId}`, {
      method: "DELETE",
    });
  }

  async reorderPanels(projectId: string, panelIds: string[]): Promise<Panel[]> {
    return this.request<Panel[]>(`/api/projects/${projectId}/panels/reorder`, {
      method: "POST",
      body: JSON.stringify({ panel_ids: panelIds }),
    });
  }

  async confirmPanels(projectId: string): Promise<{ current_stage: string; message: string }> {
    return this.request<{ current_stage: string; message: string }>(`/api/projects/${projectId}/panels/confirm`, {
      method: "POST",
    });
  }

  getPanelImageUrl(projectId: string, panelId: string): string {
    return `${this.baseUrl}/api/projects/${projectId}/panels/${panelId}/file`;
  }

  async blurPanelRegion(
    projectId: string,
    panelId: string,
    box: { x: number; y: number; width: number; height: number; blur_radius?: number; feather?: number }
  ): Promise<{ success: boolean; panel_id: string; has_backup: boolean }> {
    return this.request<{ success: boolean; panel_id: string; has_backup: boolean }>(
      `/api/projects/${projectId}/panels/${panelId}/blur-region`,
      {
        method: "POST",
        body: JSON.stringify(box),
      }
    );
  }

  async blurPanelText(
    projectId: string,
    panelId: string,
    params?: { region_ids?: string[]; blur_radius?: number; feather?: number }
  ): Promise<{ success: boolean; panel_id: string; blurred_count: number }> {
    return this.request<{ success: boolean; panel_id: string; blurred_count: number }>(
      `/api/projects/${projectId}/panels/${panelId}/blur-text`,
      {
        method: "POST",
        body: JSON.stringify(params || {}),
      }
    );
  }

  async blurEntirePanel(
    projectId: string,
    panelId: string,
    blurRadius: number = 32
  ): Promise<{ success: boolean; panel_id: string }> {
    return this.request<{ success: boolean; panel_id: string }>(
      `/api/projects/${projectId}/panels/${panelId}/blur-panel`,
      {
        method: "POST",
        body: JSON.stringify({ blur_radius: blurRadius }),
      }
    );
  }

  async resetPanelImage(
    projectId: string,
    panelId: string
  ): Promise<{ success: boolean; panel_id: string }> {
    return this.request<{ success: boolean; panel_id: string }>(
      `/api/projects/${projectId}/panels/${panelId}/reset-image`,
      {
        method: "POST",
      }
    );
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
    return this.request(
      `/api/projects/${projectId}/panels/batch-blur`,
      {
        method: "POST",
        body: JSON.stringify(params || {}),
      }
    );
  }

  async batchResetPanels(
    projectId: string,
    panelIds?: string[]
  ): Promise<{ success: boolean; project_id: string; restored_panels_count: number; total_panels: number }> {
    return this.request(
      `/api/projects/${projectId}/panels/batch-reset`,
      {
        method: "POST",
        body: JSON.stringify({ panel_ids: panelIds }),
      }
    );
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
    return this.request<OCRRecord>(
      `/api/projects/${projectId}/panels/${panelId}/ocr/blocks/${blockId}`,
      {
        method: "PUT",
        body: JSON.stringify(data),
      }
    );
  }

  async confirmOCR(
    projectId: string
  ): Promise<{ project_id: string; current_stage: string; message: string }> {
    return this.request<{
      project_id: string;
      current_stage: string;
      message: string;
    }>(`/api/projects/${projectId}/ocr/confirm`, {
      method: "POST",
    });
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
    return this.request<TextRegion>(`/api/projects/${projectId}/panels/${panelId}/text-regions`, {
      method: "POST",
      body: JSON.stringify({ x, y, width, height, region_type: regionType }),
    });
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
    return this.request<TextRegion>(`/api/projects/${projectId}/text-regions/${regionId}`, {
      method: "PUT",
      body: JSON.stringify(updates),
    });
  }

  async deleteTextRegion(projectId: string, regionId: string): Promise<void> {
    return this.request<void>(`/api/projects/${projectId}/text-regions/${regionId}`, {
      method: "DELETE",
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
    return `${this.baseUrl}/api/projects/${projectId}/text-regions/${regionId}/file`;
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
  async checkHealth(): Promise<{ status: string; app: string; version: string }> {
    return this.request<{ status: string; app: string; version: string }>("/api/system/health");
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
    return this.request<{ project_id: string; current_stage: string; message: string }>(`/api/projects/${projectId}/story/confirm`, {
      method: "POST",
    });
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
    }
  ): Promise<any> {
    return this.request<any>(`/api/projects/${projectId}/characters/${characterId}`, {
      method: "PUT",
      body: JSON.stringify(updates),
    });
  }

  async mergeCharacters(projectId: string, sourceCharacterId: string, targetCharacterId: string): Promise<any> {
    return this.request<any>(`/api/projects/${projectId}/characters/merge`, {
      method: "POST",
      body: JSON.stringify({
        source_character_id: sourceCharacterId,
        target_character_id: targetCharacterId,
      }),
    });
  }

  async splitCharacter(
    projectId: string,
    characterId: string,
    newName: string,
    panelIds: string[]
  ): Promise<any> {
    return this.request<any>(`/api/projects/${projectId}/characters/${characterId}/split`, {
      method: "POST",
      body: JSON.stringify({
        new_name: newName,
        panel_ids: panelIds,
      }),
    });
  }

  async listScenes(projectId: string): Promise<SceneEntity[]> {
    return this.request<SceneEntity[]>(`/api/projects/${projectId}/scenes`);
  }

  async mergeScenes(projectId: string, sceneId1: string, sceneId2: string): Promise<any> {
    return this.request<any>(`/api/projects/${projectId}/scenes/merge`, {
      method: "POST",
      body: JSON.stringify({
        scene_id_1: sceneId1,
        scene_id_2: sceneId2,
      }),
    });
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

  async generateAudioJob(projectId: string): Promise<{job_id: string}> {
    return this.request(`/api/projects/${projectId}/audio/generate-job`, { method: "POST", body: "{}" });
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
    return this.request<any>(`/api/projects/${projectId}/scripts/${scriptId}/segments/${segmentId}`, {
      method: "PUT",
      body: JSON.stringify(updates),
    });
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
    return this.request<{ script_id: string; status: string; message: string }>(`/api/projects/${projectId}/scripts/${scriptId}/approve`, {
      method: "POST",
    });
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
    return this.request<{ approved: boolean; message: string }>(`/api/projects/${projectId}/audio/approve`, {
      method: "POST",
    });
  }

  getAudioFileUrl(projectId: string, filePath: string): string {
    return `${this.baseUrl}/api/projects/${projectId}/audio/file?path=${encodeURIComponent(filePath)}`;
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
    modelName?: string
  ): Promise<any> {
    return this.request<any>(`/api/projects/${projectId}/narration/draft`, {
      method: "POST",
      body: JSON.stringify({ scenes, provider_id: providerId, model_name: modelName }),
    });
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
    return this.request<MotionTimelineResponse>(`/api/projects/${projectId}/motion/overrides`, {
      method: "POST",
      body: JSON.stringify({ overrides }),
    });
  }

  async approveMotion(projectId: string): Promise<{ approved: boolean; message: string }> {
    return this.request<{ approved: boolean; message: string }>(`/api/projects/${projectId}/motion/approve`, {
      method: "POST",
    });
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
    return `${this.baseUrl}/api/projects/${projectId}/render/jobs/${renderId}/output`;
  }

  getRenderContactSheetUrl(projectId: string, renderId: string): string {
    return `${this.baseUrl}/api/projects/${projectId}/render/jobs/${renderId}/contact-sheet`;
  }

  getRenderAuditSampleUrl(projectId: string, renderId: string, sampleIndex: number): string {
    return `${this.baseUrl}/api/projects/${projectId}/render/jobs/${renderId}/samples/${sampleIndex}`;
  }

  async getRenderValidation(projectId: string, renderId: string): Promise<RenderValidationReport> {
    return this.request<RenderValidationReport>(`/api/projects/${projectId}/render/jobs/${renderId}/validation`);
  }

  subscribeRenderEvents(
    onProgress: (event: any) => void,
    onError?: (error: any) => void
  ): () => void {
    const eventSource = new EventSource(`${this.baseUrl}/api/render/events`);
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
    return this.request<StoryboardSegment>(`/api/projects/${projectId}/storyboard/segments/${segmentId}`, {
      method: "PUT",
      body: JSON.stringify(update),
    });
  }

  async realignStoryboard(projectId: string): Promise<StoryboardDocument> {
    return this.request<StoryboardDocument>(`/api/projects/${projectId}/storyboard/realign`, {
      method: "POST",
    });
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
}

export const api = new PanelFlowApiClient();


