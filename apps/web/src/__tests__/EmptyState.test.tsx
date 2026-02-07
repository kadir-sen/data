import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { EmptyState } from "@/components/EmptyState";

describe("EmptyState", () => {
  it("renders default message", () => {
    render(<EmptyState />);
    expect(screen.getByText("No data available")).toBeInTheDocument();
  });

  it("renders custom message", () => {
    render(<EmptyState message="Nothing here" />);
    expect(screen.getByText("Nothing here")).toBeInTheDocument();
  });
});
