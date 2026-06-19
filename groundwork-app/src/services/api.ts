import { API_BASE_URL } from '@/constants/api';

// ─── Generic fetch wrapper ────────────────────────────────────────────────────

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
    ...options,
  });

  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`API ${res.status} ${path}: ${text}`);
  }

  return res.json() as Promise<T>;
}

// ─── Response types ───────────────────────────────────────────────────────────

export interface PresignResponse {
  upload_url: string;
  s3_key: string;
  room_scan_id: string | null;
  expires_in: number;
}

export interface EstimateJobResponse {
  job_id: string;
  status: string;
  poll_url: string;
  estimated_wait_seconds: number;
}

export type JobStatus = 'processing' | 'complete' | 'failed';

export interface JobStatusResponse {
  job_id: string;
  status: JobStatus;
  result?: EstimateResult;
  error?: string;
}

export interface TierEstimate {
  total: number;
  range: { low: number; high: number };
  subtotal_materials: number;
  subtotal_labor: number;
  permits: number;
  contingency: number;
  breakdown: LineItem[];
  timeline_weeks: number;
}

export interface VisionDetectedFeature {
  item: string;
  estimated_qty: number | null;
  unit: string | null;
  condition: string;
  notes?: string;
}

export interface WorkItem {
  item: string;
  action: string;
  qty: number | null;
  unit: string | null;
  reason: string;
  priority: 'must' | 'should' | 'could';
}

export interface EstimateResult {
  room_type: string;
  room_confidence: number;
  condition: string;
  condition_notes: string;
  vision_detected_features: VisionDetectedFeature[];
  detected_items: DetectedItem[];
  work_items: WorkItem[];
  estimate_breakdown: LineItem[];
  subtotal_materials: number;
  subtotal_labor: number;
  permits: number;
  contingency: number;
  total_estimate: number;
  estimate_range: { low: number; high: number };
  tier_estimates?: {
    economy: TierEstimate;
    standard: TierEstimate;
    premium: TierEstimate;
  };
  confidence: {
    score: number;
    label: string;
    range_pct: number;
    factors: Record<string, unknown>;
  };
  tier: string;
  regional_multiplier: number;
  scope_narrative: string;
  timeline_estimate_weeks: number;
  zip_code?: string;
  _mock?: boolean;
}

export interface DetectedItem {
  label: string;
  confidence: number;
  quantity: number | null;
  unit: string;
  bounding_box?: { x: number; y: number; w: number; h: number };
}


export interface LineItem {
  item: string;
  scope?: string;
  qty: number;
  unit: string;
  material_unit_cost: number;
  labor_unit_cost: number;
  total: number;
  hd_price_reference?: string;
}

export interface RecentEstimate {
  id: string;
  room_scan_id: string | null;
  tier: string;
  total_estimate: number;
  estimate_low: number | null;
  estimate_high: number | null;
  confidence_score: number | null;
  confidence_label: string | null;
  scope_narrative: string | null;
  timeline_weeks: number | null;
  created_at: string;
  // from room_scans join
  room_type: string | null;
  room_confidence: number | null;
  condition: string | null;
  room_label: string | null;
  celery_job_id: string | null;
  // full pipeline result — used to restore estimateStore on tap
  raw_response: EstimateResult | null;
}

export interface ProposalResponse {
  proposal_id: string;
  pdf_url: string | null;
  expires_at: string | null;
}

export interface Project {
  id: string;
  name: string;
  client_name: string | null;
  client_address: string | null;
  status: string;
  total_estimate: number | null;
  created_at: string;
}

export interface ProjectRoom {
  id: string;
  room_label: string;
  total_estimate: number;
  room_scan_id: string | null;
  estimate_id: string | null;
  added_at: string;
}

export interface ProjectAggregate {
  id: string;
  name: string;
  client_name: string | null;
  client_address: string | null;
  status: string;
  created_at: string;
  rooms: ProjectRoom[];
  aggregate: {
    room_count: number;
    subtotal: number;
    mobilization: number;
    grand_total: number;
  };
}

// ─── API calls ────────────────────────────────────────────────────────────────

export const groundworkApi = {
  /** Step 1: Get a presigned S3 PUT URL and create a pending room_scan. */
  presign(body: {
    file_name: string;
    content_type: string;
    project_id?: string;
    room_label?: string;
    room_scan_id?: string;
  }) {
    return request<PresignResponse>('/upload/presign', {
      method: 'POST',
      body: JSON.stringify(body),
    });
  },

  /**
   * Step 3: After S3 upload completes, start the vision pipeline.
   * Replaces the old /upload/confirm endpoint.
   */
  startEstimate(body: {
    s3_key?: string;
    s3_keys?: string[];
    s3_audio_key?: string;
    room_scan_id?: string | null;
    tier?: string;
    zip_code?: string;
    voice_transcript?: string;
    room_hints?: string[];
    project_id?: string;
  }) {
    return request<EstimateJobResponse>('/estimate', {
      method: 'POST',
      body: JSON.stringify(body),
    });
  },

  /** Poll for Celery task result. */
  pollStatus(jobId: string) {
    return request<JobStatusResponse>(`/estimate/status/${jobId}`);
  },

  /** Fetch most recent estimates for the home screen. */
  getRecentEstimates(limit = 10) {
    return request<RecentEstimate[]>(`/estimates/recent?limit=${limit}`);
  },

  /** Generate a PDF proposal from a completed estimate. */
  createProposal(body: {
    estimate_job_id: string;
    contractor?: Record<string, string>;
    client?: Record<string, string>;
    payment_terms?: string;
    valid_days?: number;
  }) {
    return request<ProposalResponse>('/proposal', {
      method: 'POST',
      body: JSON.stringify(body),
    });
  },

  /** Health check — used to verify backend is reachable. */
  health() {
    return request<{ status: string }>('/health');
  },

  /** Fetch all projects for the project picker. */
  getProjects() {
    return request<Project[]>('/projects');
  },

  /** Get a single project with room list and aggregate. */
  getProjectAggregate(projectId: string) {
    return request<ProjectAggregate>(`/projects/${projectId}`);
  },

  /**
   * Link a completed room scan to an existing project.
   * Returns the updated project aggregate.
   */
  addRoomToProject(body: {
    project_id: string;
    estimate_job_id: string;
    room_label?: string;
  }) {
    return request<ProjectAggregate>('/rooms', {
      method: 'POST',
      body: JSON.stringify(body),
    });
  },
};
