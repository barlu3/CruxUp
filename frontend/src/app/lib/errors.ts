// Turns the backend's size-error messages (anchors.py) into plain language
// that names the shoe. Anything unrecognised is passed through untouched as
// raw text for a "Technical details" disclosure.

import type { SelectedAnchor } from "./payload";
import { shoeName } from "./shoe";
import { ANCHOR_SIZE_MAX_LENGTH } from "./vocab";

export interface SizeProblem {
  shoeId: string;
  message: string;
}

export interface InterpretedErrors {
  sizeProblems: SizeProblem[];
  unmatched: string[];
}

// `known_good_shoes[0]: 'size' contains [...] -- it records a brand size, ...`
const CHARSET = /^known_(good|bad)_shoes\[(\d+)\]: 'size' contains .* -- it records a brand size/;
// `known_bad_shoes[2]: 'size' is 70 characters, maximum 64`
const LENGTH = /^known_(good|bad)_shoes\[(\d+)\]: 'size' is \d+ characters, maximum \d+$/;

export function interpretErrors(
  errors: readonly string[],
  good: readonly SelectedAnchor[],
  bad: readonly SelectedAnchor[],
): InterpretedErrors {
  const sizeProblems: SizeProblem[] = [];
  const unmatched: string[] = [];
  for (const raw of errors) {
    const charset = CHARSET.exec(raw);
    const length = charset ? null : LENGTH.exec(raw);
    const hit = charset ?? length;
    const anchor = hit ? (hit[1] === "good" ? good : bad)[Number(hit[2])] : undefined;
    if (!hit || !anchor) {
      unmatched.push(raw);
      continue;
    }
    const name = shoeName(anchor.shoe);
    sizeProblems.push({
      shoeId: anchor.shoe.id,
      message: charset
        ? `Size for ${name}: use only letters, numbers, spaces and . / + - (for example 41 or 8.5).`
        : `Size for ${name}: use ${ANCHOR_SIZE_MAX_LENGTH} characters or fewer.`,
    });
  }
  return { sizeProblems, unmatched };
}
