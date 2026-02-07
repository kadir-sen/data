export function LoadingState({ message = "Loading…" }: { message?: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-gray-400">
      <div className="mb-3 h-8 w-8 animate-spin rounded-full border-2 border-gray-300 border-t-indigo-600" />
      <p className="text-sm">{message}</p>
    </div>
  );
}
