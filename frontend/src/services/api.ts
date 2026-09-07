import axios, { AxiosError } from 'axios';
import { friendlyMessage } from '@/utils/apiError';

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

/** Default request timeout (ms). Configurable via VITE_API_TIMEOUT. */
export const API_TIMEOUT = Number(import.meta.env.VITE_API_TIMEOUT) || 15000;
/** Analysis can legitimately take longer than plain CRUD. */
export const ANALYZE_TIMEOUT = Number(import.meta.env.VITE_ANALYZE_TIMEOUT) || 30000;

/** Shared Axios instance for the FastAPI backend. */
export const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: API_TIMEOUT,
  headers: { 'Content-Type': 'application/json' },
});

/** Backend error envelope: { error: { code, message } } or FastAPI 422 { detail }. */
export interface ApiErrorShape {
  code: string;
  message: string;
  status?: number;
}

export function toApiError(error: unknown): ApiErrorShape {
  if (axios.isAxiosError(error)) {
    const axiosError = error as AxiosError<{ error?: { code: string; message: string }; detail?: unknown }>;
    const status = axiosError.response?.status;
    const data = axiosError.response?.data;
    if (data?.error) {
      // Trust backend 4xx messages; use a friendly generic for 5xx to avoid
      // leaking server internals.
      const message =
        status && status >= 500 ? friendlyMessage(status, data.error.message) : data.error.message;
      return { code: data.error.code, message, status };
    }
    if (data?.detail) {
      return { code: 'validation_error', message: friendlyMessage(422, 'Validation error.'), status };
    }
    return {
      code: 'network_error',
      message: status ? friendlyMessage(status, axiosError.message) : 'Unable to reach the server.',
      status,
    };
  }
  return { code: 'unknown_error', message: 'An unexpected error occurred.' };
}

// Normalize errors so callers/UI always get a consistent shape.
api.interceptors.response.use(
  (response) => response,
  (error) => Promise.reject(toApiError(error)),
);
