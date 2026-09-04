import { Link } from 'react-router-dom';
import { Compass } from 'lucide-react';

export function NotFoundPage() {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-4 px-4 text-center">
      <Compass className="h-10 w-10 text-slate-300" aria-hidden="true" />
      <div>
        <p className="text-3xl font-semibold text-slate-900">404</p>
        <p className="mt-1 text-sm text-slate-500">This page could not be found.</p>
      </div>
      <Link to="/dashboard" className="btn-primary">
        Back to dashboard
      </Link>
    </div>
  );
}
