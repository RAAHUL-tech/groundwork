/**
 * Lightweight in-memory store for the latest estimate result.
 *
 * Avoids passing large JSON blobs through URL params.
 * Result lives only for the current app session — no persistence needed.
 */
import type { EstimateResult } from './api';

let _result: EstimateResult | null = null;

export function setEstimateResult(data: EstimateResult) {
  _result = data;
}

export function getEstimateResult(): EstimateResult | null {
  return _result;
}

export function clearEstimateResult() {
  _result = null;
}
