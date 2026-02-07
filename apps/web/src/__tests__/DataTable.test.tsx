import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { DataTable } from "@/components/DataTable";

interface Row {
  id: string;
  name: string;
  value: number;
}

const columns = [
  { key: "name", header: "Name", render: (r: Row) => r.name },
  { key: "value", header: "Value", render: (r: Row) => String(r.value) },
];

const data: Row[] = [
  { id: "1", name: "Alice", value: 10 },
  { id: "2", name: "Bob", value: 20 },
];

describe("DataTable", () => {
  it("renders column headers", () => {
    render(<DataTable columns={columns} data={data} keyFn={(r) => r.id} />);
    expect(screen.getByText("Name")).toBeInTheDocument();
    expect(screen.getByText("Value")).toBeInTheDocument();
  });

  it("renders rows", () => {
    render(<DataTable columns={columns} data={data} keyFn={(r) => r.id} />);
    expect(screen.getByText("Alice")).toBeInTheDocument();
    expect(screen.getByText("Bob")).toBeInTheDocument();
    expect(screen.getByText("10")).toBeInTheDocument();
    expect(screen.getByText("20")).toBeInTheDocument();
  });

  it("shows empty message for empty data", () => {
    render(
      <DataTable columns={columns} data={[]} keyFn={(r) => r.id} emptyMessage="No rows" />,
    );
    expect(screen.getByText("No rows")).toBeInTheDocument();
  });

  it("calls onRowClick", () => {
    const onClick = vi.fn();
    render(
      <DataTable columns={columns} data={data} keyFn={(r) => r.id} onRowClick={onClick} />,
    );
    fireEvent.click(screen.getByText("Alice"));
    expect(onClick).toHaveBeenCalledWith(data[0]);
  });
});
