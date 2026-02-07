"use client";

import clsx from "clsx";

interface Column<T> {
  key: string;
  header: string;
  render: (row: T) => React.ReactNode;
  className?: string;
}

interface DataTableProps<T> {
  columns: Column<T>[];
  data: T[];
  keyFn: (row: T) => string;
  onRowClick?: (row: T) => void;
  emptyMessage?: string;
}

export function DataTable<T>({
  columns,
  data,
  keyFn,
  onRowClick,
  emptyMessage = "No data",
}: DataTableProps<T>) {
  if (data.length === 0) {
    return <p className="py-8 text-center text-sm text-gray-400">{emptyMessage}</p>;
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-200 text-left">
            {columns.map((col) => (
              <th
                key={col.key}
                className={clsx("px-3 py-2 text-xs font-medium uppercase tracking-wide text-gray-500", col.className)}
              >
                {col.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {data.map((row) => (
            <tr
              key={keyFn(row)}
              onClick={() => onRowClick?.(row)}
              className={clsx(
                "transition-colors",
                onRowClick && "cursor-pointer hover:bg-gray-50",
              )}
            >
              {columns.map((col) => (
                <td key={col.key} className={clsx("px-3 py-2", col.className)}>
                  {col.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
