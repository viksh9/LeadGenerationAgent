/** Normalized frontend error shape — safe to surface in the UI. */
export interface ApiError {
  code: string;
  message: string;
  status?: number;
}

/**
 * User-facing message per HTTP status. Never exposes server internals or stack
 * traces — the UI shows these friendly strings instead of raw backend errors.
 */
export function friendlyMessage(status: number | undefined, fallback: string): string {
  switch (status) {
    case 400:
      return 'The request was invalid. Please check your input and try again.';
    case 401:
      return 'You are not authorized. Please sign in and try again.';
    case 403:
      return "You don't have permission to do that.";
    case 404:
      return 'The requested item could not be found.';
    case 409:
      return 'This conflicts with existing data. It may already exist.';
    case 422:
      return 'Some fields are invalid. Please review and try again.';
    case 429:
      return 'Too many requests. Please wait a moment and try again.';
    case 500:
      return 'Something went wrong on the server. Please try again.';
    case 502:
    case 503:
    case 504:
      return 'The server is temporarily unavailable. Please try again shortly.';
    default:
      return fallback || 'An unexpected error occurred.';
  }
}
