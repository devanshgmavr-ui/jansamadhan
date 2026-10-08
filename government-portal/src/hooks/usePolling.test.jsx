import { cleanup, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { usePolling } from "./usePolling";

function setHidden(hidden) {
  Object.defineProperty(document, "hidden", {
    configurable: true,
    get: () => hidden,
  });
}

function Harness({ onTick, interval }) {
  usePolling(onTick, interval);
  return null;
}

describe("usePolling", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    setHidden(false);
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    setHidden(false);
  });

  it("polls on the interval without duplicating calls", () => {
    const onTick = vi.fn();
    render(<Harness onTick={onTick} interval={45000} />);
    expect(onTick).not.toHaveBeenCalled();
    vi.advanceTimersByTime(45000);
    expect(onTick).toHaveBeenCalledTimes(1);
    vi.advanceTimersByTime(45000);
    expect(onTick).toHaveBeenCalledTimes(2);
  });

  it("stops when the tab is hidden and resumes when visible", () => {
    const onTick = vi.fn();
    render(<Harness onTick={onTick} interval={45000} />);
    setHidden(true);
    document.dispatchEvent(new Event("visibilitychange"));
    vi.advanceTimersByTime(180000);
    expect(onTick).not.toHaveBeenCalled();
    setHidden(false);
    document.dispatchEvent(new Event("visibilitychange"));
    // Resume triggers one immediate refresh, then the interval continues.
    expect(onTick).toHaveBeenCalledTimes(1);
    vi.advanceTimersByTime(45000);
    expect(onTick).toHaveBeenCalledTimes(2);
  });

  it("cleans up the interval on unmount", () => {
    const onTick = vi.fn();
    const { unmount } = render(<Harness onTick={onTick} interval={45000} />);
    unmount();
    vi.advanceTimersByTime(180000);
    expect(onTick).not.toHaveBeenCalled();
  });

  it("does nothing when disabled", () => {
    const onTick = vi.fn();
    render(<Harness onTick={onTick} interval={0} />);
    vi.advanceTimersByTime(300000);
    expect(onTick).not.toHaveBeenCalled();
  });
});
