"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { FormEvent } from "react";

import { fetchShoes, submitSurvey } from "../lib/api";
import { interpretErrors } from "../lib/errors";
import type { SizeProblem } from "../lib/errors";
import { buildPayload, emptyFormState } from "../lib/payload";
import type { FormState } from "../lib/payload";
import type { Shoe } from "../lib/types";
import {
  BUDGET_HINT,
  BUDGET_INPUT,
  STREET_SIZE_HINT,
  ENUM_VOCAB,
  OPTION_LABELS,
  STREET_SIZE_INPUT,
} from "../lib/vocab";
import type { EnumField } from "../lib/vocab";
import { AnchorPicker, sizeInputId } from "./AnchorPicker";
import type { CatalogueStatus } from "./AnchorPicker";

const FOCUS = "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700";
const CONTROL = `mt-1 block w-full rounded border border-gray-500 px-2 py-1 ${FOCUS}`;

const FALLBACK_ERROR = "One of your answers could not be accepted. Please check them and try again.";
const GENERIC_ERROR = "Something went wrong sending your answers. Please try again.";

interface SelectFieldProps {
  field: EnumField;
  label: string;
  hint?: string;
  value: string;
  onChange: (value: string) => void;
}

function SelectField({ field, label, hint, value, onChange }: SelectFieldProps) {
  const id = `survey-${field}`;
  return (
    <div className="mt-4">
      <label htmlFor={id} className="block font-medium">
        {label}
      </label>
      {hint ? (
        <p id={`${id}-hint`} className="text-sm text-gray-700">
          {hint}
        </p>
      ) : null}
      <select
        id={id}
        value={value}
        aria-describedby={hint ? `${id}-hint` : undefined}
        onChange={(e) => onChange(e.target.value)}
        className={CONTROL}
      >
        <option value="">Not sure</option>
        {ENUM_VOCAB[field].map((v) => (
          <option key={v} value={v}>
            {OPTION_LABELS[field][v]}
          </option>
        ))}
      </select>
    </div>
  );
}

interface NumberFieldProps {
  id: string;
  label: string;
  hint: string;
  value: string;
  bounds: { min: number; max: number; step: number };
  onChange: (value: string) => void;
}

function NumberField({ id, label, hint, value, bounds, onChange }: NumberFieldProps) {
  return (
    <div className="mt-4">
      <label htmlFor={id} className="block font-medium">
        {label}
      </label>
      <p id={`${id}-hint`} className="text-sm text-gray-700">
        {hint}
      </p>
      <input
        id={id}
        type="number"
        inputMode="decimal"
        {...bounds}
        value={value}
        aria-describedby={`${id}-hint`}
        onChange={(e) => onChange(e.target.value)}
        className={CONTROL}
      />
    </div>
  );
}

type Failure =
  | { kind: "invalid"; sizeProblems: SizeProblem[]; unmatched: string[] }
  | { kind: "generic" };

const sizeErrorId = (shoeId: string) => `size-error-${shoeId}`;

export function SurveyForm() {
  const [state, setState] = useState<FormState>(emptyFormState);
  const [shoes, setShoes] = useState<Shoe[]>([]);
  const [catalogue, setCatalogue] = useState<CatalogueStatus>("loading");
  const [pending, setPending] = useState(false);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [done, setDone] = useState(false);
  const [attempt, setAttempt] = useState(0);
  /** shoe id -> id of its error message; cleared per shoe when its size is edited. */
  const [sizeErrors, setSizeErrors] = useState<Record<string, string>>({});
  const confirmationRef = useRef<HTMLHeadingElement>(null);
  const alertRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const controller = new AbortController();
    fetchShoes(controller.signal).then(
      (list) => {
        if (controller.signal.aborted) return;
        setShoes(list);
        setCatalogue("ready");
      },
      () => {
        // An abort means we unmounted or retried; never show it as an error.
        if (!controller.signal.aborted) setCatalogue("error");
      },
    );
    return () => controller.abort();
  }, [attempt]);

  const retryCatalogue = () => {
    setCatalogue("loading");
    setAttempt((a) => a + 1);
  };

  useEffect(() => {
    if (done) confirmationRef.current?.focus();
  }, [done]);

  useEffect(() => {
    if (failure) alertRef.current?.focus();
  }, [failure]);

  const goodIds = useMemo(() => state.known_good_shoes.map((s) => s.shoe.id), [state.known_good_shoes]);
  const badIds = useMemo(() => state.known_bad_shoes.map((s) => s.shoe.id), [state.known_bad_shoes]);

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) =>
    setState((s) => ({ ...s, [key]: value }));

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (pending) return;
    setPending(true);
    setFailure(null);
    setSizeErrors({});
    const result = await submitSurvey(buildPayload(state));
    setPending(false);
    if (result.kind === "created") setDone(true);
    else if (result.kind === "invalid") {
      const { sizeProblems, unmatched } = interpretErrors(
        result.errors,
        state.known_good_shoes,
        state.known_bad_shoes,
      );
      setSizeErrors(Object.fromEntries(sizeProblems.map((p) => [p.shoeId, sizeErrorId(p.shoeId)])));
      setFailure({ kind: "invalid", sizeProblems, unmatched });
    }
    else setFailure({ kind: "generic" });
  }

  if (done) {
    return (
      <div role="status" className="mt-6">
        <h2 ref={confirmationRef} tabIndex={-1} className="text-xl font-semibold">
          Thank you, your answers are saved.
        </h2>
        <p className="mt-2">We will use them to match you with climbing shoes.</p>
      </div>
    );
  }

  const onSizeEdit = (shoeId: string) =>
    setSizeErrors((e) => {
      if (!(shoeId in e)) return e;
      return Object.fromEntries(Object.entries(e).filter(([id]) => id !== shoeId));
    });
  const listIdFor = (shoeId: string) =>
    state.known_good_shoes.some((s) => s.shoe.id === shoeId) ? "good" : "bad";

  const select = (field: EnumField, label: string, hint?: string) => (
    <SelectField
      field={field}
      label={label}
      hint={hint}
      value={state[field]}
      onChange={(v) => set(field, v)}
    />
  );

  return (
    <form onSubmit={onSubmit} className="mt-6">
      <fieldset className="mt-6">
        <legend className="text-xl font-semibold">Your feet</legend>
        {select("foot_width", "Foot width")}
        {select("instep", "Instep", "How high the top of your foot rises.")}
        {select("toe_shape", "Toe shape")}
        {select("arch", "Arch")}
        {select("heel_fit", "Heel fit", "Whether your heel is narrow or wide.")}
        <NumberField
          id="survey-street_size"
          label="Street size (US)"
          hint={STREET_SIZE_HINT}
          value={state.street_size}
          bounds={STREET_SIZE_INPUT}
          onChange={(v) => set("street_size", v)}
        />
      </fieldset>

      <fieldset className="mt-6">
        <legend className="text-xl font-semibold">How you climb</legend>
        {select("discipline", "Discipline")}
        {select("terrain", "Terrain")}
        {select("level", "Level")}
        {/* How a comfort-vs-performance answer becomes q* is an open decision
            (timeline.md section 13), so no goal input is built or sent yet. */}
      </fieldset>

      <fieldset className="mt-6">
        <legend className="text-xl font-semibold">Budget</legend>
        <NumberField
          id="survey-budget_cap_usd"
          label="Budget cap (US dollars)"
          hint={BUDGET_HINT}
          value={state.budget_cap_usd}
          bounds={BUDGET_INPUT}
          onChange={(v) => set("budget_cap_usd", v)}
        />
      </fieldset>

      <fieldset className="mt-6">
        <legend className="text-xl font-semibold">Shoes you know</legend>
        <AnchorPicker
          id="good"
          label="Shoes that fit you well"
          hint="Pick shoes you have worn that suited your feet."
          status={catalogue}
          shoes={shoes}
          selected={state.known_good_shoes}
          excludedIds={badIds}
          onChange={(next) => set("known_good_shoes", next)}
          sizeErrorIds={sizeErrors}
          onSizeEdit={onSizeEdit}
          onRetry={retryCatalogue}
        />
        <AnchorPicker
          id="bad"
          label="Shoes that fit you badly"
          hint="Pick shoes you have worn that did not suit your feet."
          status={catalogue}
          shoes={shoes}
          selected={state.known_bad_shoes}
          excludedIds={goodIds}
          onChange={(next) => set("known_bad_shoes", next)}
          sizeErrorIds={sizeErrors}
          onSizeEdit={onSizeEdit}
          onRetry={retryCatalogue}
        />
      </fieldset>

      {failure ? (
        <div
          ref={alertRef}
          role="alert"
          tabIndex={-1}
          className="mt-6 rounded border border-red-700 p-3 text-red-900"
        >
          {failure.kind === "invalid" ? (
            <>
              <p className="font-medium">Please check your answers.</p>
              {failure.sizeProblems.length > 0 ? (
                <ul className="list-disc pl-5">
                  {failure.sizeProblems.map((p) => {
                    const target = sizeInputId(listIdFor(p.shoeId), p.shoeId);
                    return (
                      <li key={p.shoeId} id={sizeErrorId(p.shoeId)}>
                        <a
                          href={`#${target}`}
                          onClick={(e) => {
                            e.preventDefault();
                            document.getElementById(target)?.focus();
                          }}
                          className={`underline ${FOCUS}`}
                        >
                          {p.message}
                        </a>
                      </li>
                    );
                  })}
                </ul>
              ) : null}
              {failure.unmatched.length > 0 ? (
                <>
                  <p>{FALLBACK_ERROR}</p>
                  <details className="mt-2">
                    <summary className={`cursor-pointer ${FOCUS}`}>Technical details</summary>
                    <ul className="list-disc pl-5">
                      {failure.unmatched.map((message, i) => (
                        <li key={i}>{message}</li>
                      ))}
                    </ul>
                  </details>
                </>
              ) : null}
            </>
          ) : (
            <p>{GENERIC_ERROR}</p>
          )}
        </div>
      ) : null}

      <button
        type="submit"
        aria-disabled={pending}
        className={`mt-6 rounded bg-blue-800 px-4 py-2 font-medium text-white aria-disabled:cursor-wait aria-disabled:opacity-60 ${FOCUS}`}
      >
        {pending ? "Sending…" : "Submit answers"}
      </button>
    </form>
  );
}
