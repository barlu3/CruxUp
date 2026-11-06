import { describe, expect, it } from "vitest";

import { formatAxisValue } from "./format-axis-value";

describe("formatAxisValue", () => {
  it("never renders a negative zero", () => {
    expect(formatAxisValue(-0.001)).toBe("0.00");
  });

  it("renders zero to two decimals", () => {
    expect(formatAxisValue(0)).toBe("0.00");
  });

  it("renders negatives with a true minus sign", () => {
    expect(formatAxisValue(-0.6)).toBe("−0.60");
  });
});
