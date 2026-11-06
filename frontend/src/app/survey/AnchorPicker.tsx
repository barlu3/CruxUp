"use client";

import { useEffect, useId, useRef, useState } from "react";
import type { KeyboardEvent } from "react";

import type { AnchorFormEntry } from "../lib/survey-payload";
import type { Shoe } from "../lib/types";

const MAX_OPTIONS = 20;
const NO_MATCH_MESSAGE = "No matching shoes";

interface AnchorPickerProps {
  label: string;
  shoes: Shoe[];
  value: AnchorFormEntry[];
  onChange: (next: AnchorFormEntry[]) => void;
}

export function AnchorPicker({ label, shoes, value, onChange }: AnchorPickerProps) {
  const baseId = useId();
  const listboxId = `${baseId}-listbox`;
  const inputRef = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState("");
  const [isOpen, setIsOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);

  const options = filterShoes(shoes, value, query);
  const hasActive = isOpen && activeIndex >= 0 && activeIndex < options.length;

  // Optional call: jsdom does not implement scrollIntoView.
  useEffect(() => {
    if (activeIndex < 0) return;
    document.getElementById(optionId(baseId, activeIndex))?.scrollIntoView?.({ block: "nearest" });
  }, [activeIndex, baseId]);

  function handleQueryChange(next: string) {
    setQuery(next);
    setIsOpen(true);
    setActiveIndex(-1);
  }

  function handleSelect(shoe: Shoe) {
    onChange([...value, { shoe, size: "" }]);
    setQuery("");
    setIsOpen(false);
    setActiveIndex(-1);
  }

  function handleRemove(shoeId: string) {
    onChange(value.filter((e) => e.shoe.id !== shoeId));
    inputRef.current?.focus();
  }

  function handleKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      if (options.length === 0) return;
      const step = event.key === "ArrowDown" ? 1 : -1;
      // Wraps at both ends; from "no active option" ArrowUp lands on the last one.
      const start = activeIndex < 0 && step === -1 ? 0 : activeIndex;
      setIsOpen(true);
      setActiveIndex((start + step + options.length) % options.length);
    } else if (event.key === "Enter" && hasActive) {
      event.preventDefault();
      handleSelect(options[activeIndex]);
    } else if (event.key === "Escape") {
      if (!isOpen) setQuery("");
      setIsOpen(false);
      setActiveIndex(-1);
    }
  }

  const liveMessage = !isOpen
    ? ""
    : options.length === 0
      ? NO_MATCH_MESSAGE
      : `${options.length} ${options.length === 1 ? "shoe" : "shoes"} available`;

  return (
    <div className="flex flex-col gap-2">
      <label htmlFor={`${baseId}-input`} className="font-medium">
        {label}
      </label>
      <div className="relative">
        <input
          ref={inputRef}
          id={`${baseId}-input`}
          type="text"
          role="combobox"
          aria-expanded={isOpen && options.length > 0}
          aria-controls={listboxId}
          aria-autocomplete="list"
          aria-activedescendant={hasActive ? optionId(baseId, activeIndex) : undefined}
          autoComplete="off"
          placeholder="Search brand or model"
          value={query}
          onChange={(event) => handleQueryChange(event.target.value)}
          onFocus={() => setIsOpen(true)}
          onClick={() => setIsOpen(true)}
          onBlur={() => setIsOpen(false)}
          onKeyDown={handleKeyDown}
          className="min-h-11 w-full rounded-control border border-control-border bg-background px-3 text-foreground placeholder:text-muted"
        />
        <ul
          id={listboxId}
          role="listbox"
          aria-label={`${label} suggestions`}
          hidden={!isOpen || options.length === 0}
          // mousedown would blur the input and close the list before click fires.
          onMouseDown={(event) => event.preventDefault()}
          className="absolute z-10 mt-1 max-h-72 w-full overflow-auto rounded-control border border-control-border bg-surface"
        >
          {options.map((shoe, index) => (
            <li
              key={shoe.id}
              id={optionId(baseId, index)}
              role="option"
              aria-selected={hasActive && index === activeIndex}
              onClick={() => handleSelect(shoe)}
              className={`min-h-11 cursor-pointer border-l-4 px-3 py-2.5 ${
                hasActive && index === activeIndex
                  ? "border-accent-foreground bg-accent text-accent-foreground"
                  : "border-transparent text-foreground"
              }`}
            >
              {toShoeLabel(shoe)}
            </li>
          ))}
        </ul>
        {isOpen && options.length === 0 && (
          <p
            aria-hidden="true"
            className="absolute z-10 mt-1 w-full rounded-control border border-control-border bg-surface px-3 py-2.5 text-muted"
          >
            {NO_MATCH_MESSAGE}
          </p>
        )}
        <div role="status" aria-live="polite" className="sr-only">
          {liveMessage}
        </div>
      </div>
      {value.length > 0 && (
        <ul className="flex flex-col gap-2">
          {value.map((entry) => {
            const shoeLabel = toShoeLabel(entry.shoe);
            return (
              <li
                key={entry.shoe.id}
                className="flex flex-wrap items-center gap-2 rounded-control border border-control-border bg-surface p-2"
              >
                <span className="grow">{shoeLabel}</span>
                <label className="flex items-center gap-2">
                  <span className="text-sm text-muted">Size</span>
                  <input
                    type="text"
                    aria-label={`Size for ${shoeLabel}`}
                    placeholder="e.g. 40.5 EU"
                    value={entry.size}
                    onChange={(event) =>
                      onChange(
                        value.map((e) =>
                          e.shoe.id === entry.shoe.id ? { ...e, size: event.target.value } : e,
                        ),
                      )
                    }
                    className="min-h-11 w-32 rounded-control border border-control-border bg-background px-3 text-foreground placeholder:text-muted"
                  />
                </label>
                <button
                  type="button"
                  aria-label={`Remove ${shoeLabel}`}
                  onClick={() => handleRemove(entry.shoe.id)}
                  className="min-h-11 min-w-11 rounded-control border border-control-border px-3 text-danger"
                >
                  Remove
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

function optionId(baseId: string, index: number): string {
  return `${baseId}-option-${index}`;
}

// Version and gender are always shown: (brand, model) alone is ambiguous in the catalog.
function toShoeLabel(shoe: Shoe): string {
  return (
    [shoe.brand, shoe.model, shoe.version].filter((part) => part !== "").join(" ") +
    ` (${shoe.gender})`
  );
}

function filterShoes(shoes: Shoe[], picked: AnchorFormEntry[], query: string): Shoe[] {
  const terms = query.toLowerCase().split(/\s+/).filter(Boolean);
  const pickedIds = new Set(picked.map((entry) => entry.shoe.id));
  return shoes
    .filter((shoe) => {
      if (pickedIds.has(shoe.id)) return false;
      const haystack = `${shoe.brand} ${shoe.model} ${shoe.version}`.toLowerCase();
      return terms.every((term) => haystack.includes(term));
    })
    .slice(0, MAX_OPTIONS);
}
