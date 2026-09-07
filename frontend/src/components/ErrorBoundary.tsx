import { Component, type ErrorInfo, type ReactNode } from 'react';

interface Props {
  children: ReactNode;
}
interface State {
  hasError: boolean;
}

/**
 * App-level error boundary. Shows a friendly fallback instead of a blank screen
 * (or a stack trace) when a render throws. No server internals are exposed.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Log for developers; never surface to the user.
    console.error('Unhandled UI error:', error, info.componentStack);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-slate-50 p-6 text-center dark:bg-slate-950">
          <div>
            <h1 className="text-lg font-semibold text-slate-900 dark:text-slate-100">Something went wrong.</h1>
            <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
              An unexpected error occurred. Reloading usually fixes it.
            </p>
          </div>
          <button type="button" className="btn-primary" onClick={() => window.location.reload()}>
            Reload application
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
