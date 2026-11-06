import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import QuadrantPage from "./page";

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn().mockReturnValue(new Promise(() => {})));
});

describe("Quadrant page", () => {
  it("renders the Shoe quadrant heading", () => {
    render(<QuadrantPage />);
    expect(screen.getByRole("heading", { level: 1, name: "Shoe quadrant" })).toBeInTheDocument();
  });
});
