import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import shoes from "../../../e2e/fixtures/shoes.json";
import type { SelectedAnchor } from "../lib/payload";
import type { Shoe } from "../lib/types";
import { AnchorPicker, type CatalogueStatus } from "./AnchorPicker";

const catalogue = shoes as Shoe[];
const twins: Shoe[] = [
  { id: "t-1", brand: "Test Brand", model: "Twin", version: "", gender: "mens" },
  { id: "t-2", brand: "Test Brand", model: "Twin", version: "", gender: "womens" },
];

interface HarnessProps {
  status?: CatalogueStatus;
  list?: Shoe[];
  initial?: SelectedAnchor[];
  excludedIds?: readonly string[];
  onChange?: (next: SelectedAnchor[]) => void;
  sizeErrorIds?: Readonly<Record<string, string>>;
  onSizeEdit?: (shoeId: string) => void;
  onRetry?: () => void;
}

function Harness({
  status = "ready",
  list = catalogue,
  initial = [],
  excludedIds = [],
  onChange,
  sizeErrorIds,
  onSizeEdit,
  onRetry,
}: HarnessProps) {
  const [selected, setSelected] = useState<SelectedAnchor[]>(initial);
  return (
    <AnchorPicker
      id="good"
      label="Shoes that fit you well"
      status={status}
      shoes={list}
      selected={selected}
      excludedIds={excludedIds}
      sizeErrorIds={sizeErrorIds}
      onSizeEdit={onSizeEdit}
      onRetry={onRetry}
      onChange={(next) => {
        setSelected(next);
        onChange?.(next);
      }}
    />
  );
}

const combobox = () => screen.getByRole("combobox", { name: "Shoes that fit you well" });
const liveRegion = () => screen.getByRole("status");
const optionNames = () => screen.queryAllByRole("option").map((o) => o.textContent);

describe("AnchorPicker", () => {
  it("disambiguates shoes sharing brand and model by version and selects by keyboard", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    await user.type(combobox(), "instinct");
    expect(
      screen.getByRole("option", { name: "Scarpa Instinct VS (unisex)" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("option", { name: "Scarpa Instinct VSR (unisex)" }),
    ).toBeInTheDocument();
    expect(screen.getAllByRole("option")).toHaveLength(2);

    await user.keyboard("{ArrowDown}{ArrowDown}{Enter}");
    expect(onChange).toHaveBeenCalledTimes(1);
    const next = onChange.mock.calls[0][0] as SelectedAnchor[];
    expect(next).toHaveLength(1);
    expect(next[0].shoe.version).toBe("VSR");
    expect(next[0].shoe.model).toBe("Instinct");
  });

  it("tells the Solution base and Solution Comp apart", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.type(combobox(), "solution");
    expect(optionNames().sort()).toEqual([
      "La Sportiva Solution (unisex)",
      "La Sportiva Solution Comp (unisex)",
    ]);
  });

  it("tells shoes differing only by gender apart", async () => {
    const user = userEvent.setup();
    render(<Harness list={twins} />);
    await user.type(combobox(), "twin");
    expect(optionNames()).toEqual([
      "Test Brand Twin (men's)",
      "Test Brand Twin (women's)",
    ]);
  });

  it("matches every query token case-insensitively across brand, model, version and gender", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.type(combobox(), "SCARPA vsr");
    expect(optionNames()).toEqual(["Scarpa Instinct VSR (unisex)"]);
    await user.clear(combobox());
    await user.type(combobox(), "evolv women's");
    expect(optionNames()).toEqual(["Evolv Elektra (women's)"]);
  });

  it("says so when nothing matches", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.type(combobox(), "zzzz");
    expect(screen.queryAllByRole("option")).toHaveLength(0);
    expect(liveRegion()).toHaveTextContent("No matching shoes.");
  });

  it("exposes combobox ARIA state and moves the active option with the arrows", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const input = combobox();
    expect(input).toHaveAttribute("aria-expanded", "false");
    expect(input).toHaveAttribute("aria-autocomplete", "list");
    expect(input).not.toHaveAttribute("aria-activedescendant");

    await user.click(input);
    await user.keyboard("{ArrowDown}");
    expect(input).toHaveAttribute("aria-expanded", "true");
    const listboxId = input.getAttribute("aria-controls");
    expect(screen.getByRole("listbox")).toHaveAttribute("id", listboxId);
    const options = screen.getAllByRole("option");
    expect(options.length).toBe(catalogue.length);
    expect(input).toHaveAttribute("aria-activedescendant", options[0].id);
    expect(options[0]).toHaveAttribute("aria-selected", "true");
    expect(options[1]).toHaveAttribute("aria-selected", "false");

    await user.keyboard("{ArrowDown}");
    expect(input).toHaveAttribute("aria-activedescendant", options[1].id);
    await user.keyboard("{ArrowUp}");
    expect(input).toHaveAttribute("aria-activedescendant", options[0].id);
    await user.keyboard("{ArrowUp}");
    expect(input).toHaveAttribute(
      "aria-activedescendant",
      options[options.length - 1].id,
    );
  });

  it("Escape closes the list, and clears the text when already closed", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const input = combobox();
    await user.type(input, "instinct");
    expect(input).toHaveAttribute("aria-expanded", "true");
    await user.keyboard("{Escape}");
    expect(input).toHaveAttribute("aria-expanded", "false");
    expect(input).toHaveValue("instinct");
    expect(screen.queryAllByRole("option")).toHaveLength(0);
    await user.keyboard("{Escape}");
    expect(input).toHaveValue("");
  });

  it("Enter with no active option selects nothing", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    await user.type(combobox(), "instinct{Enter}");
    expect(onChange).not.toHaveBeenCalled();
  });

  it("clears the text, closes and keeps focus after selecting; Tab leaves normally", async () => {
    const user = userEvent.setup();
    render(
      <>
        <Harness />
        <button type="button">next</button>
      </>,
    );
    const input = combobox();
    await user.type(input, "drago");
    await user.keyboard("{ArrowDown}{Enter}");
    expect(input).toHaveValue("");
    expect(input).toHaveAttribute("aria-expanded", "false");
    expect(input).toHaveFocus();
    // The selected shoe's size input and remove button follow in tab order.
    await user.tab();
    expect(screen.getByLabelText("Size (optional) for Scarpa Drago (unisex)")).toHaveFocus();
    await user.tab();
    expect(screen.getByRole("button", { name: "Remove Scarpa Drago (unisex)" })).toHaveFocus();
    await user.tab();
    expect(screen.getByRole("button", { name: "next" })).toHaveFocus();
  });

  it("selects with the mouse", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    await user.type(combobox(), "defy");
    await user.click(screen.getByRole("option", { name: "Evolv Defy (men's)" }));
    expect((onChange.mock.calls[0][0] as SelectedAnchor[])[0].shoe.model).toBe("Defy");
  });

  it("removes a selected shoe by keyboard and returns focus to the input", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <Harness
        onChange={onChange}
        initial={[{ shoe: catalogue[0], size: "" }]}
      />,
    );
    const remove = screen.getByRole("button", { name: "Remove Black Diamond Momentum (unisex)" });
    remove.focus();
    await user.keyboard("{Enter}");
    expect(onChange).toHaveBeenLastCalledWith([]);
    expect(screen.queryByRole("button", { name: /^Remove/ })).toBeNull();
    expect(combobox()).toHaveFocus();
  });

  it("records the optional size, capped at 64 characters", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <Harness onChange={onChange} initial={[{ shoe: catalogue[0], size: "" }]} />,
    );
    const size = screen.getByLabelText("Size (optional) for Black Diamond Momentum (unisex)");
    expect(size).toHaveAttribute("maxlength", "64");
    await user.type(size, "42");
    expect(onChange).toHaveBeenLastCalledWith([{ shoe: catalogue[0], size: "42" }]);
  });

  it("excludes shoes already chosen in this list and in the other list", async () => {
    const user = userEvent.setup();
    const vs = catalogue.find((s) => s.version === "VS" && s.model === "Instinct")!;
    const vsr = catalogue.find((s) => s.version === "VSR")!;
    render(
      <Harness initial={[{ shoe: vs, size: "" }]} excludedIds={[vsr.id]} />,
    );
    await user.type(combobox(), "instinct");
    expect(screen.queryAllByRole("option")).toHaveLength(0);
  });

  it("disables the input while loading and says why", () => {
    render(<Harness status="loading" list={[]} />);
    expect(combobox()).toBeDisabled();
    expect(liveRegion()).toHaveTextContent("Loading shoes…");
  });

  it("disables the input on error and says the list could not be loaded", () => {
    render(<Harness status="error" list={[]} />);
    expect(combobox()).toBeDisabled();
    expect(liveRegion()).toHaveTextContent(/shoe list could not be loaded/i);
  });

  it("lists selected shoes inside a labelled list", () => {
    render(<Harness initial={[{ shoe: catalogue[0], size: "" }]} />);
    const list = screen.getByRole("list", { name: "Shoes that fit you well: selected" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(1);
  });

  it("keeps one polite live region in the DOM at all times, even when empty", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const region = liveRegion();
    expect(region).toHaveAttribute("aria-live", "polite");
    expect(region).toHaveTextContent("");
    await user.type(combobox(), "instinct");
    expect(liveRegion()).toBe(region);
    expect(region).toHaveTextContent("2 shoes match");
    await user.clear(combobox());
    await user.type(combobox(), "drago");
    expect(region).toHaveTextContent("1 shoe match");
    expect(region).not.toHaveTextContent("1 shoes");
    await user.keyboard("{Escape}");
    expect(region).toHaveTextContent("");
  });

  it("does not report a count while open with an empty query", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(combobox());
    await user.keyboard("{ArrowDown}");
    expect(liveRegion()).toHaveTextContent("");
  });

  it("never submits the form on Enter, even when nothing matches", async () => {
    // A combobox query is never a submittable value; an accidental submit of
    // the whole survey is costly. Submit stays on the button.
    const user = userEvent.setup();
    const onSubmit = vi.fn((e: React.FormEvent) => e.preventDefault());
    render(
      <form onSubmit={onSubmit}>
        <Harness />
        <button type="submit">go</button>
      </form>,
    );
    await user.type(combobox(), "zzzz{Enter}");
    await user.clear(combobox());
    await user.type(combobox(), "{Enter}");
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("still swallows Enter while a list with options is shown", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn((e: React.FormEvent) => e.preventDefault());
    render(
      <form onSubmit={onSubmit}>
        <Harness />
        <button type="submit">go</button>
      </form>,
    );
    await user.type(combobox(), "instinct{Enter}");
    expect(onSubmit).not.toHaveBeenCalled();
  });
});

describe("AnchorPicker round 3", () => {
  const sizeInput = (name: string) => screen.getByLabelText(`Size (optional) for ${name}`);

  it("opens the list on click, showing everything for an empty query, but not on focus", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const input = combobox();
    input.focus();
    expect(input).toHaveAttribute("aria-expanded", "false");
    await user.click(input);
    expect(input).toHaveAttribute("aria-expanded", "true");
    expect(screen.getAllByRole("option")).toHaveLength(catalogue.length);
  });

  it("does not blur the input on mouse-down inside the listbox itself", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(combobox());
    const listbox = screen.getByRole("listbox");
    // fireEvent returns false when preventDefault was called.
    expect(fireEvent.mouseDown(listbox)).toBe(false);
    expect(combobox()).toHaveFocus();
  });

  it("ignores keys while an IME composition is in progress", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    await user.type(combobox(), "drago");
    await user.keyboard("{ArrowDown}");
    fireEvent.keyDown(combobox(), { key: "Enter", isComposing: true });
    expect(onChange).not.toHaveBeenCalled();
    fireEvent.keyDown(combobox(), { key: "ArrowDown", isComposing: true });
    expect(combobox()).toHaveAttribute("aria-activedescendant");
    await user.keyboard("{Enter}");
    expect(onChange).toHaveBeenCalledTimes(1);
  });

  it("announces choosing and removing a shoe, and clears the notice on typing", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.type(combobox(), "drago");
    await user.keyboard("{ArrowDown}{Enter}");
    expect(liveRegion()).toHaveTextContent("Scarpa Drago (unisex) added. 1 selected.");
    await user.click(screen.getByRole("button", { name: "Remove Scarpa Drago (unisex)" }));
    expect(liveRegion()).toHaveTextContent("Scarpa Drago (unisex) removed. 0 selected.");
    await user.type(combobox(), "d");
    expect(liveRegion()).not.toHaveTextContent("removed");
    expect(liveRegion()).toHaveTextContent(/shoes? match/);
  });

  it("uses one visible polite status paragraph and no aria-hidden duplicate", () => {
    render(<Harness status="loading" list={[]} />);
    const region = liveRegion();
    expect(region).toHaveAttribute("aria-live", "polite");
    expect(region).not.toHaveClass("sr-only");
    expect(document.querySelector('[aria-hidden="true"]')).toBeNull();
    expect(combobox().getAttribute("aria-describedby")).toContain(region.id);
  });

  it("gives loading/error text priority over a notice", () => {
    render(<Harness status="error" list={[]} />);
    expect(liveRegion()).toHaveTextContent(/could not be loaded/i);
  });

  it("explains that chosen shoes are hidden when nothing else matches", async () => {
    const user = userEvent.setup();
    const drago = catalogue.find((s) => s.model === "Drago")!;
    render(<Harness initial={[{ shoe: drago, size: "" }]} />);
    await user.type(combobox(), "drago");
    expect(liveRegion()).toHaveTextContent(
      "No matching shoes. Shoes you already chose are not shown.",
    );
    await user.clear(combobox());
    await user.type(combobox(), "zzzz");
    // Something is still excluded, so the longer text applies here too.
    expect(liveRegion()).toHaveTextContent("Shoes you already chose are not shown.");
  });

  it("keeps the short no-match text when nothing is excluded", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.type(combobox(), "zzzz");
    expect(liveRegion().textContent).toBe("No matching shoes.");
  });

  it("has keyboard instructions in the hint and no placeholder on the combobox", () => {
    render(<Harness />);
    const input = combobox();
    expect(input).not.toHaveAttribute("placeholder");
    const hint = document.getElementById(input.getAttribute("aria-describedby")!.split(" ")[0]);
    expect(hint).toHaveTextContent(/up and down arrow keys and Enter/i);
  });

  it("marks the active option with a non-colour cue", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(combobox());
    await user.keyboard("{ArrowDown}");
    expect(screen.getAllByRole("option")[0].className).toMatch(/outline-2/);
    expect(screen.getAllByRole("option")[1].className).not.toMatch(/outline-2/);
  });

  it("gives each size input a visible label, a hint, no placeholder and autocomplete off", () => {
    render(<Harness initial={[{ shoe: catalogue[0], size: "" }]} />);
    const input = sizeInput("Black Diamond Momentum (unisex)");
    expect(input).not.toHaveAttribute("placeholder");
    expect(input).toHaveAttribute("autocomplete", "off");
    expect(input).toHaveAttribute("maxlength", "64");
    const label = document.querySelector(`label[for="${input.id}"]`)!;
    expect(label.textContent).toBe("Size (optional) for Black Diamond Momentum (unisex)");
    expect(label.querySelector(".sr-only")?.textContent).toBe(" for Black Diamond Momentum (unisex)");
    const hint = document.getElementById(input.getAttribute("aria-describedby")!.split(" ")[0]);
    expect(hint).toHaveTextContent(/As printed on the shoe/);
    expect(hint).toHaveTextContent(/letters, numbers, spaces and \. \/ \+ -/);
    expect(input).not.toHaveAttribute("aria-invalid");
  });

  it("flags an invalid size, links it to its error, and reports edits", async () => {
    const user = userEvent.setup();
    const onSizeEdit = vi.fn();
    const shoe = catalogue[0];
    render(
      <>
        <p id="err-1">bad size</p>
        <Harness
          initial={[{ shoe, size: "4,1" }]}
          sizeErrorIds={{ [shoe.id]: "err-1" }}
          onSizeEdit={onSizeEdit}
        />
      </>,
    );
    const input = sizeInput("Black Diamond Momentum (unisex)");
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(input.getAttribute("aria-describedby")).toContain("err-1");
    await user.type(input, "5");
    expect(onSizeEdit).toHaveBeenCalledWith(shoe.id);
  });

  it("offers a Try again button in the error state that calls onRetry", async () => {
    const user = userEvent.setup();
    const onRetry = vi.fn();
    render(<Harness status="error" list={[]} onRetry={onRetry} />);
    await user.keyboard("{Tab}");
    const retry = screen.getByRole("button", { name: /try again/i });
    expect(retry).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("moves focus to the input once a retry succeeds", async () => {
    const user = userEvent.setup();
    const { rerender } = render(<Harness status="error" list={[]} onRetry={() => {}} />);
    await user.click(screen.getByRole("button", { name: /try again/i }));
    rerender(<Harness status="loading" list={[]} onRetry={() => {}} />);
    rerender(<Harness status="ready" list={catalogue} onRetry={() => {}} />);
    expect(combobox()).toHaveFocus();
  });

  it("shows no Try again button unless the catalogue failed", () => {
    render(<Harness />);
    expect(screen.queryByRole("button", { name: /try again/i })).toBeNull();
  });
});

describe("AnchorPicker scrolling", () => {
  const scroll = vi.fn();
  const original = Element.prototype.scrollIntoView;
  beforeEach(() => {
    scroll.mockReset();
    Element.prototype.scrollIntoView = scroll;
  });
  afterEach(() => {
    Element.prototype.scrollIntoView = original;
  });

  it("scrolls the active option into view whenever it changes", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(combobox());
    await user.keyboard("{ArrowDown}");
    const first = screen.getAllByRole("option")[0];
    expect(scroll).toHaveBeenLastCalledWith({ block: "nearest" });
    expect(scroll.mock.contexts.at(-1)).toBe(first);
    await user.keyboard("{ArrowDown}");
    expect(scroll.mock.contexts.at(-1)).toBe(screen.getAllByRole("option")[1]);
    expect(scroll).toHaveBeenCalledTimes(2);
  });
});
