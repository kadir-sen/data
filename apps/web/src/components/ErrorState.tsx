import { ExclamationTriangleIcon } from "@heroicons/react/24/outline";

interface ErrorStateProps {
  message?: string;
  onRetry?: () => void;
}

export function ErrorState({
  message = "Something went wrong",
  onRetry,
}: ErrorStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-red-400">
      <ExclamationTriangleIcon className="mb-3 h-12 w-12" />
      <p className="mb-3 text-sm">{message}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="rounded bg-red-50 px-3 py-1.5 text-sm text-red-600 hover:bg-red-100"
        >
          Retry
        </button>
      )}
    </div>
  );
}
