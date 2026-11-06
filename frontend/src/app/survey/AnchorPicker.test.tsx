import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { AnchorFormEntry } from "../lib/survey-payload";
import type { Shoe } from "../lib/types";

import { AnchorPicker } from "./AnchorPicker";

const INSTINCT_VS: Shoe = { id: "scarpa-instinct-vs", brand: "Scarpa", model: "Instinct", version: "VS", gender: "unisex" };
const INSTINCT_VSR: Shoe = { id: "scarpa-instinct-vsr", brand: "Scarpa", model: "Instinct", version: "VSR", gender: "unisex" };
const KATANA_LACE: Shoe = { id: "ls-katana-lace", brand: "La Sportiva", model: "Katana", version: "Lace", gender: "unisex" };
const KATANA_VELCRO: Shoe = { id: "ls-katana-velcro", brand: "La Sportiva", model: "Katana", version: "Velcro", gender: "unisex" };
const SOLUTION: Shoe = { id: "ls-solution-womens", brand: "La Sportiva", model: "Solution", version: "", gender: "womens" };
const SOLUTION_COMP: Shoe = { id: "ls-solution-comp", brand: "La Sportiva", model: "Solution", version: "Comp", gender: "mens" };
const DEFY_MENS: Shoe = { id: "evolv-defy-mens", brand: "Evolv", model: "Defy", version: "", gender: "mens" };
const DEFY_WOMENS: Shoe = { id: "evolv-defy-womens", brand: "Evolv", model: "Defy", version: "", gender: "womens" };

const SHOES = [INSTINCT_VS, INSTINCT_VSR, KATANA_LACE, KATANA_VELCRO, SOLUTION, SOLUTION_COMP, DEFY_MENS, DEFY_WOMENS];

function renderPicker(value: AnchorFormEntry[] = [], shoes: Shoe[] = SHOES) {
  const onChange = vi.fn();
  render(<AnchorPicker label="Shoes you love" shoes={shoes} value={value} onChange={onChange} />);
  return onChange;
}

function typeQuery(text: string) {
  const input = screen.getByRole("combobox");
  fireEvent.focus(input);
  fireEvent.change(input, { target: { value: text } });
  return input;
}

describe("AnchorPicker", () => {
  it("shows exactly two options when typing a model with two versions", () => {
    renderPicker();
    typeQuery("instinct");
    expect(screen.getAllByRole("option")).toHaveLength(2);
  });

  it("gives the two Instinct options different accessible names", () => {
    renderPicker();
    typeQuery("instinct");
    expect(screen.getByRole("option", { name: "Scarpa Instinct VS (unisex)" })).not.toBe(
      screen.getByRole("option", { name: "Scarpa Instinct VSR (unisex)" }),
    );
  });

  it("distinguishes same brand and model by gender when version is empty", () => {
    renderPicker();
    typeQuery("defy");
    const names = screen.getAllByRole("option").map((o) => o.textContent);
    expect(names).toEqual(["Evolv Defy (mens)", "Evolv Defy (womens)"]);
  });

  it("matches every whitespace-separated term case-insensitively", () => {
    renderPicker();
    typeQuery("KATANA  velcro");
    expect(screen.getAllByRole("option")).toHaveLength(1);
  });

  it("calls onChange with the first match and an empty size on ArrowDown then Enter", () => {
    const onChange = renderPicker();
    const input = typeQuery("instinct");
    fireEvent.keyDown(input, { key: "ArrowDown" });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onChange).toHaveBeenCalledWith([{ shoe: INSTINCT_VS, size: "" }]);
  });

  it("wraps from the first option to the last on ArrowUp", () => {
    const onChange = renderPicker();
    const input = typeQuery("instinct");
    fireEvent.keyDown(input, { key: "ArrowDown" });
    fireEvent.keyDown(input, { key: "ArrowUp" });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onChange).toHaveBeenCalledWith([{ shoe: INSTINCT_VSR, size: "" }]);
  });

  it("appends to existing entries when selecting", () => {
    const existing = { shoe: DEFY_MENS, size: "41" };
    const onChange = renderPicker([existing]);
    const input = typeQuery("katana velcro");
    fireEvent.keyDown(input, { key: "ArrowDown" });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onChange).toHaveBeenCalledWith([existing, { shoe: KATANA_VELCRO, size: "" }]);
  });

  it("calls onChange with the exact shoe when an option is clicked", () => {
    const onChange = renderPicker();
    typeQuery("katana");
    fireEvent.click(screen.getByRole("option", { name: "La Sportiva Katana Velcro (unisex)" }));
    expect(onChange).toHaveBeenCalledWith([{ shoe: KATANA_VELCRO, size: "" }]);
  });

  it("closes the listbox on Escape", () => {
    renderPicker();
    const input = typeQuery("instinct");
    fireEvent.keyDown(input, { key: "Escape" });
    expect(input).toHaveAttribute("aria-expanded", "false");
  });

  it("keeps the typed text on Escape", () => {
    renderPicker();
    const input = typeQuery("instinct");
    fireEvent.keyDown(input, { key: "Escape" });
    expect(input).toHaveValue("instinct");
  });

  it("does not offer an already-selected shoe", () => {
    renderPicker([{ shoe: INSTINCT_VS, size: "" }]);
    typeQuery("instinct");
    expect(screen.getAllByRole("option").map((o) => o.textContent)).toEqual(["Scarpa Instinct VSR (unisex)"]);
  });

  it("calls onChange without the entry when its remove button is clicked", () => {
    const keep = { shoe: DEFY_MENS, size: "" };
    const onChange = renderPicker([{ shoe: INSTINCT_VS, size: "" }, keep]);
    fireEvent.click(screen.getByRole("button", { name: "Remove Scarpa Instinct VS (unisex)" }));
    expect(onChange).toHaveBeenCalledWith([keep]);
  });

  it("calls onChange with the updated size when the size input is edited", () => {
    const onChange = renderPicker([{ shoe: INSTINCT_VS, size: "" }]);
    fireEvent.change(screen.getByRole("textbox", { name: "Size for Scarpa Instinct VS (unisex)" }), {
      target: { value: "40.5 EU" },
    });
    expect(onChange).toHaveBeenCalledWith([{ shoe: INSTINCT_VS, size: "40.5 EU" }]);
  });

  it("shows the current size in the size input", () => {
    renderPicker([{ shoe: INSTINCT_VS, size: "39" }]);
    expect(screen.getByRole("textbox", { name: "Size for Scarpa Instinct VS (unisex)" })).toHaveValue("39");
  });

  it("points aria-activedescendant at the active option", () => {
    renderPicker();
    const input = typeQuery("instinct");
    fireEvent.keyDown(input, { key: "ArrowDown" });
    const active = screen.getByRole("option", { name: "Scarpa Instinct VS (unisex)" });
    expect(input.getAttribute("aria-activedescendant")).toBe(active.id);
  });

  it("marks only the active option as aria-selected", () => {
    renderPicker();
    const input = typeQuery("instinct");
    fireEvent.keyDown(input, { key: "ArrowDown" });
    expect(screen.getAllByRole("option", { selected: true })).toHaveLength(1);
  });

  it("shows a message when no shoe matches", () => {
    renderPicker();
    typeQuery("zzzzqqq");
    expect(screen.getByText("No matching shoes", { selector: "p" })).toBeVisible();
  });

  it("keeps aria-expanded false when the query matches nothing", () => {
    renderPicker();
    const input = typeQuery("zzzzqqq");
    expect(input).toHaveAttribute("aria-expanded", "false");
  });

  it("keeps the empty-state message outside the listbox", () => {
    renderPicker();
    typeQuery("zzzzqqq");
    const listbox = screen.getByRole("listbox", { hidden: true });
    expect(within(listbox).queryByText("No matching shoes")).toBeNull();
  });

  it("names the listbox differently from the input", () => {
    renderPicker();
    expect(screen.getByRole("listbox", { hidden: true })).toHaveAttribute("aria-label", "Shoes you love suggestions");
  });

  it("hides the listbox when there are no options", () => {
    renderPicker();
    typeQuery("zzzzqqq");
    expect(screen.getByRole("listbox", { hidden: true })).not.toBeVisible();
  });

  it("announces the number of available shoes in a live region", () => {
    renderPicker();
    typeQuery("instinct");
    expect(screen.getByRole("status")).toHaveTextContent("2 shoes available");
  });

  it("announces when no shoes match in a live region", () => {
    renderPicker();
    typeQuery("zzzzqqq");
    expect(screen.getByRole("status")).toHaveTextContent("No matching shoes");
  });

  it("leaves the live region empty while the list is closed", () => {
    renderPicker();
    expect(screen.getByRole("status")).toBeEmptyDOMElement();
  });

  it("prevents default on mousedown over an option so the input keeps focus", () => {
    renderPicker();
    typeQuery("katana");
    const option = screen.getByRole("option", { name: "La Sportiva Katana Velcro (unisex)" });
    expect(fireEvent.mouseDown(option)).toBe(false);
  });

  it("closes the listbox when the input loses focus", () => {
    renderPicker();
    const input = typeQuery("instinct");
    fireEvent.blur(input);
    expect(input).toHaveAttribute("aria-expanded", "false");
  });

  it("clears aria-activedescendant after Escape", () => {
    renderPicker();
    const input = typeQuery("instinct");
    fireEvent.keyDown(input, { key: "ArrowDown" });
    fireEvent.keyDown(input, { key: "Escape" });
    expect(input).not.toHaveAttribute("aria-activedescendant");
  });

  it("clears aria-activedescendant after selecting", () => {
    renderPicker();
    const input = typeQuery("instinct");
    fireEvent.keyDown(input, { key: "ArrowDown" });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(input).not.toHaveAttribute("aria-activedescendant");
  });

  it("opens a closed list on ArrowDown", () => {
    renderPicker();
    const input = typeQuery("instinct");
    fireEvent.keyDown(input, { key: "Escape" });
    fireEvent.keyDown(input, { key: "ArrowDown" });
    expect(input).toHaveAttribute("aria-expanded", "true");
  });

  it("reopens a closed list when the input is clicked", () => {
    renderPicker();
    const input = typeQuery("instinct");
    fireEvent.keyDown(input, { key: "Escape" });
    fireEvent.click(input);
    expect(input).toHaveAttribute("aria-expanded", "true");
  });

  it("does not select anything on Enter when no option is active", () => {
    const onChange = renderPicker();
    const input = typeQuery("instinct");
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onChange).not.toHaveBeenCalled();
  });

  it("clears the text on a second Escape once the list is closed", () => {
    renderPicker();
    const input = typeQuery("instinct");
    fireEvent.keyDown(input, { key: "Escape" });
    fireEvent.keyDown(input, { key: "Escape" });
    expect(input).toHaveValue("");
  });

  it("returns focus to the combobox after an entry is removed", () => {
    renderPicker([{ shoe: INSTINCT_VS, size: "" }]);
    fireEvent.click(screen.getByRole("button", { name: "Remove Scarpa Instinct VS (unisex)" }));
    expect(screen.getByRole("combobox")).toHaveFocus();
  });

  it("shows a visible Size label next to the size input", () => {
    renderPicker([{ shoe: INSTINCT_VS, size: "" }]);
    expect(screen.getByText("Size")).toBeVisible();
  });

  describe("scrolling the active option into view", () => {
    const scrolled: string[] = [];
    const original = Element.prototype.scrollIntoView;

    beforeEach(() => {
      scrolled.length = 0;
      Element.prototype.scrollIntoView = function scrollIntoView(this: Element, arg?: unknown) {
        scrolled.push(`${this.id}:${(arg as ScrollIntoViewOptions).block}`);
      };
    });

    afterEach(() => {
      Element.prototype.scrollIntoView = original;
    });

    it("scrolls the newly active option into view with block nearest", () => {
      renderPicker();
      const input = typeQuery("instinct");
      fireEvent.keyDown(input, { key: "ArrowDown" });
      const active = screen.getByRole("option", { name: "Scarpa Instinct VS (unisex)" });
      expect(scrolled).toEqual([`${active.id}:nearest`]);
    });
  });

  it("caps the number of displayed options at 20", () => {
    const many: Shoe[] = Array.from({ length: 30 }, (_, i) => ({
      id: `m-${i}`,
      brand: "Brand",
      model: `Model ${i}`,
      version: "",
      gender: "unisex",
    }));
    renderPicker([], many);
    typeQuery("brand");
    expect(screen.getAllByRole("option")).toHaveLength(20);
  });

  it("renders catalog strings literally instead of as markup", () => {
    const hostile: Shoe = { id: "x", brand: "<b>x</b>", model: "Evil", version: "", gender: "unisex" };
    renderPicker([], [hostile]);
    typeQuery("evil");
    expect(screen.getByRole("option")).toHaveTextContent("<b>x</b> Evil (unisex)");
  });
});
