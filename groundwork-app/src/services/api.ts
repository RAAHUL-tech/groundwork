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

export interface ConfirmResponse {
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

export interface EstimateResult {
  room_type: string;
  room_confidence: number;
  condition: string;
  condition_notes: string;
  detected_items: DetectedItem[];
  voice_scope_items: VoiceScopeItem[];
  estimate_breakdown: LineItem[];
  subtotal_materials: number;
  subtotal_labor: number;
  permits: number;
  contingency: number;
  total_estimate: number;
  estimate_range: { low: number; high: number };
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
  _mock?: boolean;
}

export interface DetectedItem {
  label: string;
  confidence: number;
  quantity: number;
  unit: string;
}

export interface VoiceScopeItem {
  item: string;
  action: string;
  source: string;
  notes?: string;
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

// ─── API calls ────────────────────────────────────────────────────────────────

export const groundworkApi = {
  /** Step 1: Get a presigned S3 PUT URL and create a pending room_scan. */
  presign(body: {
    file_name: string;
    content_type: string;
    project_id?: string;
    room_label?: string;
  }) {
    return request<PresignResponse>('/upload/presign', {
      method: 'POST',
      body: JSON.stringify(body),
    });
  },

  /** Step 3: Confirm upload done → enqueue vision pipeline. */
  confirm(body: {
    s3_key?: string;
    s3_keys?: string[];
    room_scan_id?: string | null;
    tier?: string;
    zip_code?: string;
    voice_transcript?: string;
    room_hints?: string[];
  }) {
    return request<ConfirmResponse>('/upload/confirm', {
      method: 'POST',
      body: JSON.stringify(body),
    });
  },

  /** Poll for Celery task result. */
  pollStatus(jobId: string) {
    return request<JobStatusResponse>(`/estimate/status/${jobId}`);
  },

  /** Health check — used to verify backend is reachable. */
  health() {
    return request<{ status: string }>('/health');
  },
};
