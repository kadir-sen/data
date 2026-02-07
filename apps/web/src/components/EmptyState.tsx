import { InboxIcon } from "@heroicons/react/24/outline";

export function EmptyState({ message = "No data available" }: { message?: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-gray-400">
      <InboxIcon className="mb-3 h-12 w-12" />
      <p className="text-sm">{message}</p>
    </div>
  );
}
