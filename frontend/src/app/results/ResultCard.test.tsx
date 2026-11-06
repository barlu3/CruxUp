import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { Recommendation, RecommendTerms } from "../lib/types";

import { ResultCard } from "./ResultCard";

const TERMS: RecommendTerms = { fit: true, style: true, budget: true };

function makeResult(overrides: Partial<Recommendation> = {}): Recommendation {
  return {
    id: "s1",
    brand: "La Sportiva",
    model: "Solution",
    version: "",
    gender: "mens",
    x: 0.1,
    y: 0.2,
    prior_source: "corpus",
    is_anchor: false,
    quadrant: "Q1",
    msrp_usd: 189,
    price_unknown: false,
    fit_score: 0.82,
    style_score: 0.6,
    budget_score: 1,
    total_score: 0.74,
    confidence: 0.9,
    confidence_label: "high",
    rank: 1,
    warnings: [],
    ...overrides,
  };
}

function renderCard(overrides: Partial<Recommendation> = {}, terms: RecommendTerms = TERMS) {
  return render(<ResultCard result={makeResult(overrides)} terms={terms} />);
}

describe("ResultCard", () => {
  it("headlines the shoe label", () => {
    renderCard();
    expect(screen.getByRole("heading", { level: 3 })).toHaveTextContent("La Sportiva Solution (mens)");
  });

  it("names the card after its heading", () => {
    renderCard();
    expect(screen.getByRole("article")).toHaveAccessibleName("La Sportiva Solution (mens)");
  });

  it("shows the rank", () => {
    renderCard();
    expect(screen.getByText("Rank 1")).toBeInTheDocument();
  });

  it("shows the match score first", () => {
    renderCard();
    expect(screen.getAllByRole("term")[0]).toHaveTextContent("Match");
  });

  it("shows the match score out of 100", () => {
    renderCard();
    expect(screen.getByText("74/100")).toBeInTheDocument();
  });

  it("shows a low confidence badge in text", () => {
    renderCard({ confidence_label: "low" });
    expect(screen.getByText("Low confidence")).toBeInTheDocument();
  });

  it("tells a low confidence reader to treat it as a rough starting point", () => {
    renderCard({ confidence_label: "low", prior_source: "spec" });
    expect(screen.getByText(/Treat this as a rough starting point: this shoe's position is estimated from its specs\./)).toBeInTheDocument();
  });

  it("falls back to the explanation when a low card has no reasons", () => {
    renderCard({ confidence_label: "low" });
    expect(screen.getByText(/Treat this as a rough starting point: Much of the information/)).toBeInTheDocument();
  });

  it("does not show the rough starting point text on a high card", () => {
    renderCard({ confidence_label: "high" });
    expect(screen.queryByText(/rough starting point/)).not.toBeInTheDocument();
  });

  it("explains medium confidence", () => {
    renderCard({ confidence_label: "medium" });
    expect(screen.getByText(/could shift/)).toBeInTheDocument();
  });

  it("gives a low card a dashed border", () => {
    renderCard({ confidence_label: "low" });
    expect(screen.getByRole("article")).toHaveClass("border-dashed", "border-warning");
  });

  it("gives a high card a solid border", () => {
    renderCard({ confidence_label: "high" });
    expect(screen.getByRole("article")).not.toHaveClass("border-dashed");
  });

  it("gives a medium card a solid border", () => {
    renderCard({ confidence_label: "medium" });
    expect(screen.getByRole("article")).not.toHaveClass("border-dashed");
  });

  it("uses a thick border on a low card", () => {
    renderCard({ confidence_label: "low" });
    expect(screen.getByRole("article")).toHaveClass("border-2");
  });

  it("lets the heading shrink on a phone", () => {
    renderCard();
    expect(screen.getByRole("heading", { level: 3 })).toHaveClass("min-w-0");
  });

  it("wraps long words anywhere on the card", () => {
    renderCard();
    expect(screen.getByRole("article")).toHaveClass("wrap-anywhere");
  });

  it("notes a neutral budget estimate when the price is unknown", () => {
    renderCard({ price_unknown: true, msrp_usd: null, budget_score: 0.5 });
    expect(screen.getByText(/price unknown, so this is a neutral estimate/)).toBeInTheDocument();
  });

  it("does not add the neutral budget note when the price is known", () => {
    renderCard();
    expect(screen.queryByText(/neutral estimate/)).not.toBeInTheDocument();
  });

  it("renders the fallback sentence for an unknown warning code", () => {
    renderCard({ warnings: ["brand_new_code"] });
    expect(screen.getByRole("list")).toHaveTextContent("There is a note about this result that we can't describe yet.");
  });

  it("renders one list item per warning code", () => {
    renderCard({ warnings: ["reported_good_fit", "brand_new_code"] });
    expect(within(screen.getByRole("list")).getAllByRole("listitem")).toHaveLength(2);
  });

  it("tags each warning with its code", () => {
    renderCard({ warnings: ["brand_new_code"] });
    expect(within(screen.getByRole("list")).getByRole("listitem")).toHaveAttribute("data-code", "brand_new_code");
  });

  it("hides the warning icon from assistive tech", () => {
    const { container } = renderCard({ confidence_label: "low" });
    expect(container.querySelector("svg")).toHaveAttribute("aria-hidden", "true");
  });

  it("flags an unknown price", () => {
    renderCard({ price_unknown: true, msrp_usd: null });
    expect(screen.getByText("Price unknown")).toBeInTheDocument();
  });

  it("shows a known list price", () => {
    renderCard();
    expect(screen.getByText("List price (US) $189")).toBeInTheDocument();
  });

  it("does not flag a known price as unknown", () => {
    renderCard();
    expect(screen.queryByText("Price unknown")).not.toBeInTheDocument();
  });

  it("marks an unused fit score", () => {
    renderCard({ fit_score: null }, { ...TERMS, fit: false });
    expect(screen.getByText("Not used")).toBeInTheDocument();
  });

  it("explains why the fit score was not used", () => {
    renderCard({ fit_score: null }, { ...TERMS, fit: false });
    expect(screen.getByText(/answer the fit questions/)).toBeInTheDocument();
  });

  it("shows the fit score out of 100", () => {
    renderCard();
    expect(screen.getByText("82/100")).toBeInTheDocument();
  });

  it("shows a translated warning sentence", () => {
    renderCard({ warnings: ["reported_poor_fit"] });
    expect(screen.getByRole("list")).toHaveTextContent(/still ranked/);
  });

  it("omits the warnings list when there are none", () => {
    renderCard({ warnings: [] });
    expect(screen.queryByRole("list")).not.toBeInTheDocument();
  });

  it("renders a hostile brand literally", () => {
    renderCard({ brand: "<img src=x>" });
    expect(screen.getByRole("heading", { level: 3 })).toHaveTextContent("<img src=x> Solution (mens)");
  });
});
