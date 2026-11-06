import type { Shoe } from "./types";

// Version and gender are always shown: (brand, model) alone is ambiguous in the catalog.
export function toShoeLabel(shoe: Pick<Shoe, "brand" | "model" | "version" | "gender">): string {
  return (
    [shoe.brand, shoe.model, shoe.version].filter((part) => part !== "").join(" ") +
    ` (${shoe.gender})`
  );
}
