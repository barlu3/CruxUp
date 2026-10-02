"use client";

// Catalogue-backed anchor picker: the WAI-ARIA APG "combobox with listbox
// popup" pattern, hand-rolled. Shoes are chosen from the catalogue (never free
// text) and shown with brand, model, version and gender so shoes sharing
// (brand, model) stay distinguishable.

import { useEffect, useId, useMemo, useRef, useState } from "react";
import type { KeyboardEvent } from "react";

import type { SelectedAnchor } from "../lib/payload";
import { shoeName } from "../lib/shoe";
import type { Shoe } from "../lib/types";
import { ANCHOR_SIZE_MAX_LENGTH, GENDER_LABELS, SIZE_HINT } from "../lib/vocab";

export type CatalogueStatus = "loading" | "error" | "ready";

export interface AnchorPickerProps {
  id: string;
  label: string;
  hint?: string;
  status: CatalogueStatus;
  shoes: readonly Shoe[];
  selected: readonly SelectedAnchor[];
  /** Ids chosen in the other list; they are not offered here. */
  excludedIds?: readonly string[];
  onChange: (next: SelectedAnchor[]) => void;
  /** shoe id -> id of the element holding that size's error message. */
  sizeErrorIds?: Readonly<Record<string, string>>;
  /** Called when the user edits a size input. */
  onSizeEdit?: (shoeId: string) => void;
  /** Re-run the catalogue request; shows a "Try again" button on error. */
  onRetry?: () => void;
}

/** DOM id of a selected shoe's size input (the form links errors to it). */
export function sizeInputId(listId: string, shoeId: string): string {
  return `${listId}-size-${shoeId}`;
}

const KEYBOARD_HINT =
  "Type to search, then use the up and down arrow keys and Enter to choose.";

function haystack(shoe: Shoe): string {
  return `${shoe.brand} ${shoe.model} ${shoe.version} ${GENDER_LABELS[shoe.gender]}`.toLowerCase();
}

const NONE: readonly string[] = [];

const FOCUS = "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700";

export function AnchorPicker({
  id,
  label,
  hint,
  status,
  shoes,
  selected,
  excludedIds = NONE,
  onChange,
  sizeErrorIds,
  onSizeEdit,
  onRetry,
}: AnchorPickerProps) {
  const uid = useId();
  const inputId = `${id}-input${uid}`;
  const listboxId = `${id}-listbox${uid}`;
  const hintId = `${id}-hint${uid}`;
  const statusId = `${id}-status${uid}`;
  const inputRef = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const [notice, setNotice] = useState("");
  const retryRef = useRef<HTMLButtonElement>(null);
  const retryClicked = useRef(false);

  const taken = useMemo(
    () => new Set([...excludedIds, ...selected.map((s) => s.shoe.id)]),
    [excludedIds, selected],
  );
  const options = useMemo(() => {
    const tokens = query.toLowerCase().split(/\s+/).filter(Boolean);
    return shoes.filter((s) => {
      if (taken.has(s.id)) return false;
      const text = haystack(s);
      return tokens.every((t) => text.includes(t));
    });
  }, [shoes, taken, query]);

  const disabled = status !== "ready";
  const showList = open && !disabled && options.length > 0;
  const optionId = (shoe: Shoe) => `${id}-opt-${shoe.id}${uid}`;
  const activeShoe = showList && active >= 0 ? options[active] : undefined;

  const activeId = activeShoe ? optionId(activeShoe) : undefined;
  useEffect(() => {
    if (activeId) document.getElementById(activeId)?.scrollIntoView({ block: "nearest" });
  }, [activeId]);

  // After "Try again": the button unmounts while loading, so hand focus to the
  // input on success (or back to the new button if it fails again).
  useEffect(() => {
    if (!retryClicked.current || status === "loading") return;
    retryClicked.current = false;
    if (status === "ready") inputRef.current?.focus();
    else retryRef.current?.focus();
  }, [status]);

  function choose(shoe: Shoe) {
    onChange([...selected, { shoe, size: "" }]);
    setNotice(`${shoeName(shoe)} added. ${selected.length + 1} selected.`);
    setQuery("");
    setOpen(false);
    setActive(-1);
    inputRef.current?.focus();
  }

  function remove(shoe: Shoe) {
    onChange(selected.filter((s) => s.shoe.id !== shoe.id));
    setNotice(`${shoeName(shoe)} removed. ${selected.length - 1} selected.`);
    inputRef.current?.focus();
  }

  function setSize(shoeId: string, size: string) {
    onSizeEdit?.(shoeId);
    onChange(selected.map((s) => (s.shoe.id === shoeId ? { ...s, size } : s)));
  }

  function onKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.nativeEvent.isComposing) return; // IME composition owns the keys
    const count = options.length;
    switch (e.key) {
      case "ArrowDown":
        e.preventDefault();
        if (count === 0) return;
        setOpen(true);
        setActive((a) => (open ? (a + 1) % count : 0));
        break;
      case "ArrowUp":
        e.preventDefault();
        if (count === 0) return;
        setOpen(true);
        setActive((a) => (open ? (a <= 0 ? count - 1 : a - 1) : count - 1));
        break;
      case "Enter":
        // Always swallowed: a combobox query is never a submittable value, and
        // an accidental submit of the whole survey is costly. Submit stays on
        // the button (and Enter in the other fields).
        e.preventDefault();
        if (activeShoe) choose(activeShoe);
        break;
      case "Escape":
        if (open) {
          e.preventDefault();
          setOpen(false);
          setActive(-1);
        } else if (query !== "") {
          e.preventDefault();
          setQuery("");
        }
        break;
    }
  }

  // One persistent live region. Priority: loading/error, then the add/remove
  // notice, then the match count while typing, then "no matches".
  const excludedSome = shoes.some((s) => taken.has(s.id));
  let statusText = "";
  let statusInDescription = false;
  if (status === "loading") {
    statusText = "Loading shoes…";
    statusInDescription = true;
  } else if (status === "error") {
    statusText = "The shoe list could not be loaded. You can still submit your other answers.";
    statusInDescription = true;
  } else if (notice) {
    statusText = notice;
  } else if (open && query.trim() !== "") {
    if (options.length > 0) {
      statusText = `${options.length} ${options.length === 1 ? "shoe matches" : "shoes match"}`;
    } else {
      statusText = excludedSome
        ? "No matching shoes. Shoes you already chose are not shown."
        : "No matching shoes.";
    }
  }

  return (
    <div className="mt-4">
      <label htmlFor={inputId} className="block font-medium">
        {label}
      </label>
      <p id={hintId} className="text-sm text-gray-700">
        {hint ? `${hint} ` : ""}
        {KEYBOARD_HINT}
      </p>
      <input
        ref={inputRef}
        id={inputId}
        type="text"
        role="combobox"
        autoComplete="off"
        aria-expanded={showList}
        aria-controls={listboxId}
        aria-autocomplete="list"
        aria-activedescendant={activeId}
        aria-describedby={statusInDescription ? `${hintId} ${statusId}` : hintId}
        disabled={disabled}
        value={query}
        onClick={() => setOpen(true)}
        onChange={(e) => {
          setNotice("");
          setQuery(e.target.value);
          setOpen(true);
          setActive(-1);
        }}
        onKeyDown={onKeyDown}
        onBlur={() => {
          setOpen(false);
          setActive(-1);
        }}
        className={`mt-1 block w-full rounded border border-gray-500 px-2 py-1 disabled:bg-gray-100 ${FOCUS}`}
      />
      <p id={statusId} role="status" aria-live="polite" className="mt-1 min-h-5 text-sm text-gray-700">
        {statusText}
      </p>
      {status === "error" && onRetry ? (
        <button
          ref={retryRef}
          type="button"
          onClick={() => {
            retryClicked.current = true;
            onRetry();
          }}
          className={`mt-1 rounded border border-gray-500 px-2 py-1 ${FOCUS}`}
        >
          Try again<span className="sr-only">{` loading the shoe list for ${label}`}</span>
        </button>
      ) : null}
      <ul
        id={listboxId}
        role="listbox"
        aria-label={`${label} suggestions`}
        hidden={!showList}
        // Keep focus in the input even if the press lands on the listbox's
        // scrollbar or padding rather than an option.
        onMouseDown={(e) => e.preventDefault()}
        className="mt-1 max-h-60 overflow-auto rounded border border-gray-500 bg-white"
      >
        {showList
          ? options.map((shoe, i) => (
              <li
                key={shoe.id}
                id={optionId(shoe)}
                role="option"
                aria-selected={i === active}
                onClick={() => choose(shoe)}
                className={`cursor-pointer px-2 py-1 ${
                  // Outline too, so the active option is visible without colour
                  // (forced-colors mode drops backgrounds).
                  i === active ? "bg-blue-700 text-white outline-2 -outline-offset-2 outline-current" : ""
                }`}
              >
                {shoeName(shoe)}
              </li>
            ))
          : null}
      </ul>
      {selected.length > 0 ? (
        <ul aria-label={`${label}: selected`} className="mt-2 space-y-2">
          {selected.map(({ shoe, size }) => {
            const name = shoeName(shoe);
            const sizeId = sizeInputId(id, shoe.id);
            const hintElId = `${sizeId}-hint`;
            const errorId = sizeErrorIds?.[shoe.id];
            return (
              <li key={shoe.id} className="rounded border border-gray-300 p-2">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">{name}</span>
                </div>
                <div className="mt-2">
                  <label htmlFor={sizeId} className="text-sm font-medium">
                    Size (optional)<span className="sr-only">{` for ${name}`}</span>
                  </label>
                  <p id={hintElId} className="text-sm text-gray-700">
                    {SIZE_HINT}
                  </p>
                  <input
                    id={sizeId}
                    type="text"
                    autoComplete="off"
                    maxLength={ANCHOR_SIZE_MAX_LENGTH}
                    value={size}
                    aria-invalid={errorId ? true : undefined}
                    aria-describedby={errorId ? `${hintElId} ${errorId}` : hintElId}
                    onChange={(e) => setSize(shoe.id, e.target.value)}
                    className={`mt-1 w-40 rounded border border-gray-500 px-2 py-1 ${FOCUS}`}
                  />
                </div>
                <div className="mt-2">
                  <button
                    type="button"
                    aria-label={`Remove ${name}`}
                    onClick={() => remove(shoe)}
                    className={`rounded border border-gray-500 px-2 py-1 ${FOCUS}`}
                  >
                    Remove
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      ) : null}
    </div>
  );
}
