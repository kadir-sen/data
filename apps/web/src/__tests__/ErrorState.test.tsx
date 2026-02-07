import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { ErrorState } from "@/components/ErrorState";

describe("ErrorState", () => {
  it("renders default message", () => {
    render(<ErrorState />);
    expect(screen.getByText("Something went wrong")).toBeInTheDocument();
  });

  it("renders custom message", () => {
    render(<ErrorState message="API failed" />);
    expect(screen.getByText("API failed")).toBeInTheDocument();
  });

  it("renders retry button when onRetry provided", () => {
    const onRetry = vi.fn();
    render(<ErrorState onRetry={onRetry} />);
    const btn = screen.getByText("Retry");
    expect(btn).toBeInTheDocument();
    fireEvent.click(btn);
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it("does not render retry button without onRetry", () => {
    render(<ErrorState />);
    expect(screen.queryByText("Retry")).not.toBeInTheDocument();
  });
});
