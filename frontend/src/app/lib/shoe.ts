import type { Shoe } from "./types";
import { GENDER_LABELS } from "./vocab";

/** "Scarpa Instinct VSR (unisex)"; version omitted for a base model. */
export function shoeName(shoe: Shoe): string {
  const version = shoe.version === "" ? "" : ` ${shoe.version}`;
  return `${shoe.brand} ${shoe.model}${version} (${GENDER_LABELS[shoe.gender]})`;
}
