import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { DrillDownPanel } from "@/components/DrillDownPanel";
import type { WorkItem } from "@/lib/types";

const mockItem: WorkItem = {
  id: "1",
  source: "jira",
  source_id: "PLAT-101",
  title: "Fix login bug",
  description: null,
  item_type: "bug",
  status: "in_progress",
  priority: "high",
  story_points: 3,
  due_date: null,
  resolved_at: null,
  assignee_id: null,
  sprint_id: null,
  parent_id: null,
  labels: [],
  changelog: [],
  created_at: "2025-01-01T00:00:00Z",
  updated_at: "2025-01-02T00:00:00Z",
};

describe("DrillDownPanel", () => {
  it("renders nothing when closed", () => {
    const { container } = render(
      <DrillDownPanel title="Test" items={[mockItem]} open={false} onClose={() => {}} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("renders title and items when open", () => {
    render(
      <DrillDownPanel title="Bug items" items={[mockItem]} open={true} onClose={() => {}} />,
    );
    expect(screen.getByText("Bug items")).toBeInTheDocument();
    expect(screen.getByText("Fix login bug")).toBeInTheDocument();
    expect(screen.getByText(/PLAT-101/)).toBeInTheDocument();
  });

  it("shows item count", () => {
    render(
      <DrillDownPanel title="Test" items={[mockItem]} open={true} onClose={() => {}} />,
    );
    expect(screen.getByText("1 item")).toBeInTheDocument();
  });

  it("calls onClose when close button clicked", () => {
    const onClose = vi.fn();
    render(
      <DrillDownPanel title="Test" items={[mockItem]} open={true} onClose={onClose} />,
    );
    const buttons = screen.getAllByRole("button");
    fireEvent.click(buttons[0]);
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("shows empty message when no items", () => {
    render(
      <DrillDownPanel title="Empty" items={[]} open={true} onClose={() => {}} />,
    );
    expect(screen.getByText("No items to display.")).toBeInTheDocument();
  });
});
