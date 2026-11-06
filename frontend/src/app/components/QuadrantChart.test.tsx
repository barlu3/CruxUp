import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PLOT_PADDING, VIEW_SIZE } from "../lib/quadrant-scale";

import type { QuadrantShoe } from "../lib/types";

import { QuadrantChart } from "./QuadrantChart";

const DEFY: QuadrantShoe = { id: "defy", brand: "Evolv", model: "Defy", version: "", gender: "mens", x: -0.6, y: 0.4, prior_source: "hand", is_anchor: true, quadrant: "Q3" };
const KATANA: QuadrantShoe = { id: "katana", brand: "La Sportiva", model: "Katana", version: "Lace", gender: "unisex", x: 0.1, y: -0.3, prior_source: "spec", is_anchor: false, quadrant: "Q1" };
const SOLUTION: QuadrantShoe = { id: "solution", brand: "La Sportiva", model: "Solution", version: "", gender: "womens", x: 0.5, y: -0.6, prior_source: "hand", is_anchor: false, quadrant: "Q1" };
const DRAGO: QuadrantShoe = { id: "drago", brand: "Scarpa", model: "Drago", version: "", gender: "unisex", x: 0.8, y: 0.7, prior_source: "hand", is_anchor: true, quadrant: "Q4" };
// Deliberately unsorted: the tab order must come from x, not input order.
const SHOES = [DRAGO, KATANA, DEFY, SOLUTION];

function getPoint(label: string) {
  return screen.getByRole("img", { name: new RegExp(`^${label.replace(/[()]/g, "\\$&")}`) });
}

function getPoints() {
  return screen.getAllByRole("img", { name: /Comfort–performance/ });
}

function getTabStop(container: HTMLElement) {
  return container.querySelector<SVGElement>('[tabindex="0"]');
}

function labelPosition(text: string, axis: "x" | "y") {
  return Number(screen.getByText(text).getAttribute(axis));
}

describe("QuadrantChart marks", () => {
  it("renders one point per shoe", () => {
    render(<QuadrantChart shoes={SHOES} />);
    expect(getPoints()).toHaveLength(4);
  });

  it("places the Q1 label below the Q3 label", () => {
    render(<QuadrantChart shoes={SHOES} />);
    expect(labelPosition("Q1 · Performance", "y")).toBeGreaterThan(labelPosition("Q3 · Comfort", "y"));
  });

  it("places the Q1 label right of the Q2 label", () => {
    render(<QuadrantChart shoes={SHOES} />);
    expect(labelPosition("Q1 · Performance", "x")).toBeGreaterThan(labelPosition("Q2 · Comfort", "x"));
  });

  it("places the Q4 label above the Q2 label", () => {
    render(<QuadrantChart shoes={SHOES} />);
    expect(labelPosition("Q4 · Performance", "y")).toBeLessThan(labelPosition("Q2 · Comfort", "y"));
  });

  it.each(["Comfort", "Performance", "Soft", "Stiff"])("renders the %s axis label", (label) => {
    render(<QuadrantChart shoes={SHOES} />);
    expect(screen.getByText(label)).toBeInTheDocument();
  });

  it("shows a visible text label for an anchor", () => {
    render(<QuadrantChart shoes={SHOES} />);
    expect(screen.getByText("Drago")).toBeInTheDocument();
  });

  it("shows no text label for a non-anchor", () => {
    render(<QuadrantChart shoes={SHOES} />);
    expect(screen.queryByText("Solution")).not.toBeInTheDocument();
  });

  it("draws a spec-derived point hollow", () => {
    render(<QuadrantChart shoes={SHOES} />);
    expect(getPoint("La Sportiva Katana Lace")).toHaveClass("fill-background");
  });

  it("draws a hand-placed point filled", () => {
    render(<QuadrantChart shoes={SHOES} />);
    expect(getPoint("La Sportiva Solution")).toHaveClass("fill-foreground");
  });

  it("names the provenance on each point", () => {
    render(<QuadrantChart shoes={SHOES} />);
    expect(getPoint("La Sportiva Katana Lace")).toHaveAccessibleName(
      "La Sportiva Katana Lace (unisex). Comfort–performance 0.10, leaning performance. Stiff–soft −0.30, leaning stiff. Spec-derived.",
    );
  });

  it("calls a value near zero neutral in the accessible name", () => {
    render(<QuadrantChart shoes={[{ ...KATANA, x: 0.04, y: -0.04 }]} />);
    expect(getPoint("La Sportiva Katana Lace")).toHaveAccessibleName(
      "La Sportiva Katana Lace (unisex). Comfort–performance 0.04, neutral. Stiff–soft −0.04, neutral. Spec-derived.",
    );
  });

  it("describes each point as a shoe", () => {
    render(<QuadrantChart shoes={SHOES} />);
    expect(getPoint("Scarpa Drago")).toHaveAttribute("aria-roledescription", "shoe");
  });

  it("gives each point a hit area of at least 20 viewBox units", () => {
    const { container } = render(<QuadrantChart shoes={[DRAGO]} />);
    expect(Number(container.querySelector("circle.fill-transparent")?.getAttribute("r"))).toBeGreaterThanOrEqual(20);
  });

  it.each([
    ["Comfort", "start"],
    ["Performance", "end"],
  ])("anchors the %s axis label as %s", (text, anchor) => {
    render(<QuadrantChart shoes={SHOES} />);
    expect(screen.getByText(text)).toHaveAttribute("text-anchor", anchor);
  });

  it.each(["Comfort", "Performance"])("keeps the %s axis label anchor inside the viewBox", (text) => {
    render(<QuadrantChart shoes={SHOES} />);
    const x = labelPosition(text, "x");
    expect(x >= 0 && x <= VIEW_SIZE).toBe(true);
  });

  it("keeps the full quadrant wording in the label's second line", () => {
    render(<QuadrantChart shoes={SHOES} />);
    expect(screen.getByText("Q1 · Performance").parentElement).toHaveTextContent("Q1 · Performance+ stiff");
  });

  it.each(["Soft", "Q1 · Performance", "Drago"])("sizes the %s label at 18 viewBox units or more", (text) => {
    render(<QuadrantChart shoes={SHOES} />);
    expect(screen.getByText(text).closest("[class*='text-lg']")).not.toBeNull();
  });

  it("places the Q3 label above the plot frame", () => {
    render(<QuadrantChart shoes={SHOES} />);
    expect(labelPosition("Q3 · Comfort", "y")).toBeLessThan(PLOT_PADDING);
  });

  it("places the Q1 label below the plot frame", () => {
    render(<QuadrantChart shoes={SHOES} />);
    expect(labelPosition("Q1 · Performance", "y")).toBeGreaterThan(VIEW_SIZE - PLOT_PADDING);
  });

  it("marks anchors as section 3 reference shoes in the accessible name", () => {
    render(<QuadrantChart shoes={SHOES} />);
    expect(getPoint("Scarpa Drago")).toHaveAccessibleName(/Section 3 reference shoe\./);
  });
});

describe("QuadrantChart legend", () => {
  it("lists Hand-placed when a hand point is present", () => {
    render(<QuadrantChart shoes={SHOES} />);
    expect(within(screen.getByRole("list", { name: "Legend" })).getByText("Hand-placed")).toBeInTheDocument();
  });

  it("omits the corpus entry when no corpus point is present", () => {
    render(<QuadrantChart shoes={SHOES} />);
    expect(within(screen.getByRole("list", { name: "Legend" })).queryByText("Corpus-derived")).not.toBeInTheDocument();
  });

  it("lists the section 3 reference shoe entry when an anchor is present", () => {
    render(<QuadrantChart shoes={SHOES} />);
    expect(within(screen.getByRole("list", { name: "Legend" })).getByText("Section 3 reference shoe")).toBeInTheDocument();
  });
});

describe("QuadrantChart empty state", () => {
  it("says there are no shoes to show", () => {
    render(<QuadrantChart shoes={[]} />);
    expect(screen.getByText("No shoes to show")).toBeInTheDocument();
  });

  it("renders no points for an empty list", () => {
    render(<QuadrantChart shoes={[]} />);
    expect(screen.queryAllByRole("img")).toHaveLength(0);
  });
});

describe("QuadrantChart keyboard interaction", () => {
  it("makes exactly one point a tab stop", () => {
    const { container } = render(<QuadrantChart shoes={SHOES} />);
    expect(container.querySelectorAll('[tabindex="0"]')).toHaveLength(1);
  });

  it("makes the lowest-x shoe the initial tab stop", () => {
    const { container } = render(<QuadrantChart shoes={SHOES} />);
    expect(getTabStop(container)).toHaveAccessibleName(/^Evolv Defy/);
  });

  it("moves focus to the next shoe by x on ArrowRight", () => {
    render(<QuadrantChart shoes={SHOES} />);
    getPoint("Evolv Defy").focus();
    fireEvent.keyDown(getPoint("Evolv Defy"), { key: "ArrowRight" });
    expect(getPoint("La Sportiva Katana Lace")).toHaveFocus();
  });

  it("moves focus to the next shoe on ArrowDown", () => {
    render(<QuadrantChart shoes={SHOES} />);
    getPoint("Evolv Defy").focus();
    fireEvent.keyDown(getPoint("Evolv Defy"), { key: "ArrowDown" });
    expect(getPoint("La Sportiva Katana Lace")).toHaveFocus();
  });

  it("moves focus to the previous shoe on ArrowLeft", () => {
    render(<QuadrantChart shoes={SHOES} />);
    getPoint("La Sportiva Katana Lace").focus();
    fireEvent.keyDown(getPoint("La Sportiva Katana Lace"), { key: "ArrowLeft" });
    expect(getPoint("Evolv Defy")).toHaveFocus();
  });

  it("moves focus to the previous shoe on ArrowUp", () => {
    render(<QuadrantChart shoes={SHOES} />);
    getPoint("La Sportiva Katana Lace").focus();
    fireEvent.keyDown(getPoint("La Sportiva Katana Lace"), { key: "ArrowUp" });
    expect(getPoint("Evolv Defy")).toHaveFocus();
  });

  it("keeps focus on the first shoe on ArrowLeft", () => {
    render(<QuadrantChart shoes={SHOES} />);
    getPoint("Evolv Defy").focus();
    fireEvent.keyDown(getPoint("Evolv Defy"), { key: "ArrowLeft" });
    expect(getPoint("Evolv Defy")).toHaveFocus();
  });

  it("keeps focus on the last shoe on ArrowRight", () => {
    render(<QuadrantChart shoes={SHOES} />);
    getPoint("Scarpa Drago").focus();
    fireEvent.keyDown(getPoint("Scarpa Drago"), { key: "ArrowRight" });
    expect(getPoint("Scarpa Drago")).toHaveFocus();
  });

  it("moves focus to the last shoe on End", () => {
    render(<QuadrantChart shoes={SHOES} />);
    getPoint("Evolv Defy").focus();
    fireEvent.keyDown(getPoint("Evolv Defy"), { key: "End" });
    expect(getPoint("Scarpa Drago")).toHaveFocus();
  });

  it("moves focus to the first shoe on Home", () => {
    render(<QuadrantChart shoes={SHOES} />);
    getPoint("Scarpa Drago").focus();
    fireEvent.keyDown(getPoint("Scarpa Drago"), { key: "Home" });
    expect(getPoint("Evolv Defy")).toHaveFocus();
  });

  it("returns the tab stop to the last-focused point after blur", () => {
    const { container } = render(<QuadrantChart shoes={SHOES} />);
    getPoint("La Sportiva Solution").focus();
    fireEvent.blur(getPoint("La Sportiva Solution"));
    expect(getTabStop(container)).toHaveAccessibleName(/^La Sportiva Solution/);
  });

  it("describes the chart controls on the group", () => {
    render(<QuadrantChart shoes={SHOES} />);
    expect(screen.getByRole("group")).toHaveAccessibleDescription(/most comfort-focused to most performance-focused/);
  });
});

describe("QuadrantChart tooltip", () => {
  function getTooltip() {
    return screen.getByRole("tooltip", { hidden: true });
  }

  it("is hidden by default", () => {
    render(<QuadrantChart shoes={SHOES} />);
    expect(screen.queryByRole("tooltip", { hidden: true })).not.toBeInTheDocument();
  });

  it("shows the shoe label on focus", () => {
    render(<QuadrantChart shoes={SHOES} />);
    fireEvent.focus(getPoint("Scarpa Drago"));
    expect(getTooltip()).toHaveTextContent("Scarpa Drago (unisex)");
  });

  it("shows on mouseenter", () => {
    render(<QuadrantChart shoes={SHOES} />);
    fireEvent.mouseEnter(getPoint("Scarpa Drago"));
    expect(getTooltip()).toBeInTheDocument();
  });

  it("hides on mouseleave", () => {
    render(<QuadrantChart shoes={SHOES} />);
    fireEvent.mouseEnter(getPoint("Scarpa Drago"));
    fireEvent.mouseLeave(getPoint("Scarpa Drago"));
    expect(screen.queryByRole("tooltip", { hidden: true })).not.toBeInTheDocument();
  });

  it("hides on pointerleave", () => {
    render(<QuadrantChart shoes={SHOES} />);
    fireEvent.mouseEnter(getPoint("Scarpa Drago"));
    fireEvent.pointerLeave(getPoint("Scarpa Drago"));
    expect(screen.queryByRole("tooltip", { hidden: true })).not.toBeInTheDocument();
  });

  it("hides on a pointerdown outside the chart", () => {
    render(<QuadrantChart shoes={SHOES} />);
    fireEvent.mouseEnter(getPoint("Scarpa Drago"));
    fireEvent.pointerDown(document.body);
    expect(screen.queryByRole("tooltip", { hidden: true })).not.toBeInTheDocument();
  });

  it("uses the same wording as the accessible name", () => {
    render(<QuadrantChart shoes={SHOES} />);
    fireEvent.mouseEnter(getPoint("Scarpa Drago"));
    expect(getTooltip()).toHaveTextContent("Stiff–soft 0.70, leaning soft.");
  });

  it("hides on blur", () => {
    render(<QuadrantChart shoes={SHOES} />);
    fireEvent.focus(getPoint("Scarpa Drago"));
    fireEvent.blur(getPoint("Scarpa Drago"));
    expect(screen.queryByRole("tooltip", { hidden: true })).not.toBeInTheDocument();
  });

  it("hides on Escape", () => {
    render(<QuadrantChart shoes={SHOES} />);
    fireEvent.mouseEnter(getPoint("Scarpa Drago"));
    fireEvent.keyDown(getPoint("Scarpa Drago"), { key: "Escape" });
    expect(screen.queryByRole("tooltip", { hidden: true })).not.toBeInTheDocument();
  });

  it("keeps focus on the point after Escape", () => {
    render(<QuadrantChart shoes={SHOES} />);
    getPoint("Scarpa Drago").focus();
    fireEvent.keyDown(getPoint("Scarpa Drago"), { key: "Escape" });
    expect(getPoint("Scarpa Drago")).toHaveFocus();
  });

  it("shows again after Escape when another point is entered", () => {
    render(<QuadrantChart shoes={SHOES} />);
    fireEvent.mouseEnter(getPoint("Scarpa Drago"));
    fireEvent.keyDown(getPoint("Scarpa Drago"), { key: "Escape" });
    fireEvent.mouseEnter(getPoint("Evolv Defy"));
    expect(getTooltip()).toHaveTextContent("Evolv Defy (men's)");
  });

  it("says Hand-placed for a hand-placed shoe", () => {
    render(<QuadrantChart shoes={SHOES} />);
    fireEvent.mouseEnter(getPoint("La Sportiva Solution"));
    expect(getTooltip()).toHaveTextContent("Hand-placed");
  });

  it("says Section 3 reference shoe for an anchor", () => {
    render(<QuadrantChart shoes={SHOES} />);
    fireEvent.mouseEnter(getPoint("Scarpa Drago"));
    expect(getTooltip()).toHaveTextContent("Section 3 reference shoe.");
  });

  it("is hidden from assistive technology", () => {
    render(<QuadrantChart shoes={SHOES} />);
    fireEvent.mouseEnter(getPoint("Scarpa Drago"));
    expect(getTooltip()).toHaveAttribute("aria-hidden", "true");
  });
});
