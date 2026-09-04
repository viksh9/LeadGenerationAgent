import axios, { AxiosError } from 'axios';

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

/** Shared Axios instance for the FastAPI backend. */
export const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 15000,
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
      return { code: data.error.code, message: data.error.message, status };
    }
    if (data?.detail) {
      const message = Array.isArray(data.detail)
        ? 'Validation error. Please check the submitted values.'
        : String(data.detail);
      return { code: 'validation_error', message, status };
    }
    return {
      code: 'network_error',
      message: axiosError.message || 'Unable to reach the server.',
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
