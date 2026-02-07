import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { KpiCard } from "@/components/charts/KpiCard";
import type { KpiSnapshot } from "@/lib/types";

const kpi: KpiSnapshot = {
  label: "Delivered",
  value: 18,
  previousValue: 14,
  unit: "items",
  trend: "up",
  trendIsPositive: true,
};

describe("KpiCard", () => {
  it("renders label and value", () => {
    render(<KpiCard kpi={kpi} />);
    expect(screen.getByText("Delivered")).toBeInTheDocument();
    expect(screen.getByText("18")).toBeInTheDocument();
  });

  it("renders unit", () => {
    render(<KpiCard kpi={kpi} />);
    expect(screen.getByText("items")).toBeInTheDocument();
  });

  it("renders delta with sign", () => {
    render(<KpiCard kpi={kpi} />);
    expect(screen.getByText("+4 since yesterday")).toBeInTheDocument();
  });

  it("calls onClick when clicked", () => {
    const onClick = vi.fn();
    render(<KpiCard kpi={kpi} onClick={onClick} />);
    fireEvent.click(screen.getByRole("button"));
    expect(onClick).toHaveBeenCalledOnce();
  });

  it("renders negative delta", () => {
    const kpiDown: KpiSnapshot = {
      label: "WIP",
      value: 7,
      previousValue: 9,
      unit: "items",
      trend: "down",
      trendIsPositive: true,
    };
    render(<KpiCard kpi={kpiDown} />);
    expect(screen.getByText("-2 since yesterday")).toBeInTheDocument();
  });
});
