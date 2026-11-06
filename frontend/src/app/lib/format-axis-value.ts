// Rounds before checking the sign so a value that displays as zero never reads "−0.00".
export function formatAxisValue(value: number): string {
  const magnitude = Math.abs(value).toFixed(2);
  return value < 0 && magnitude !== "0.00" ? `−${magnitude}` : magnitude;
}
