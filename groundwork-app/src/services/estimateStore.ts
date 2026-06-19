/**
 * Lightweight in-memory store for the latest estimate result.
 *
 * Avoids passing large JSON blobs through URL params.
 * Result lives only for the current app session — no persistence needed.
 */
import type { EstimateResult } from './api';

let _result: EstimateResult | null = null;
let _jobId: string | null = null;

export interface ProjectClient {
  name: string;
  address: string;
}

let _projectClient: ProjectClient | null = null;

export function setEstimateResult(data: EstimateResult) {
  _result = data;
}

export function getEstimateResult(): EstimateResult | null {
  return _result;
}

export function clearEstimateResult() {
  _result = null;
  _jobId  = null;
  _projectClient = null;
}

export function setEstimateJobId(jobId: string) {
  _jobId = jobId;
}

export function getEstimateJobId(): string | null {
  return _jobId;
}

export function setProjectClient(client: ProjectClient) {
  _projectClient = client;
}

export function getProjectClient(): ProjectClient | null {
  return _projectClient;
}
