import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { QuadrantShoe } from "../lib/types";

import { QuadrantTable } from "./QuadrantTable";

const DRAGO: QuadrantShoe = { id: "drago", brand: "Scarpa", model: "Drago", version: "", gender: "unisex", x: 0.8, y: 0.7, prior_source: "hand", is_anchor: true, quadrant: "Q4" };
const DEFY: QuadrantShoe = { id: "defy", brand: "Evolv", model: "Defy", version: "", gender: "mens", x: -0.6, y: 0.4, prior_source: "spec", is_anchor: false, quadrant: "Q3" };
const SHOES = [DEFY, DRAGO];

// The first rowgroup is the thead; the quadrant bodies follow in Q1-Q4 order.
function getGroup(quadrantNumber: 1 | 2 | 3 | 4) {
  return screen.getAllByRole("rowgroup")[quadrantNumber];
}

describe("QuadrantTable", () => {
  it("has a caption", () => {
    render(<QuadrantTable shoes={SHOES} />);
    expect(screen.getByRole("table", { name: "All shoes by quadrant" })).toBeInTheDocument();
  });

  it("hides the caption visually because the section heading already shows it", () => {
    render(<QuadrantTable shoes={SHOES} />);
    expect(screen.getByText("All shoes by quadrant")).toHaveClass("sr-only");
  });

  it("has one row group header per quadrant", () => {
    render(<QuadrantTable shoes={SHOES} />);
    expect(screen.getAllByRole("rowheader")).toHaveLength(4);
  });

  it("lists Drago inside the Q4 group", () => {
    render(<QuadrantTable shoes={SHOES} />);
    expect(within(getGroup(4)).getByRole("cell", { name: /^Scarpa Drago \(unisex\)/ })).toBeInTheDocument();
  });

  it("adds a quadrant cue to the shoe cell for screen readers", () => {
    render(<QuadrantTable shoes={SHOES} />);
    expect(within(getGroup(4)).getByRole("cell", { name: /^Scarpa Drago/ })).toHaveTextContent(
      "Scarpa Drago (unisex) (Q4 · Performance + soft)",
    );
  });

  it("renders x to two decimals", () => {
    render(<QuadrantTable shoes={SHOES} />);
    expect(within(getGroup(4)).getByRole("cell", { name: "0.80" })).toBeInTheDocument();
  });

  it("renders negatives with a true minus sign", () => {
    render(<QuadrantTable shoes={SHOES} />);
    expect(within(getGroup(3)).getByRole("cell", { name: "−0.60" })).toBeInTheDocument();
  });

  it("marks Drago as a section 3 reference", () => {
    render(<QuadrantTable shoes={SHOES} />);
    expect(within(getGroup(4)).getByRole("cell", { name: "Yes" })).toBeInTheDocument();
  });

  it("shows No shoes for an empty quadrant", () => {
    render(<QuadrantTable shoes={SHOES} />);
    expect(within(getGroup(1)).getByRole("cell", { name: "No shoes" })).toBeInTheDocument();
  });
});
