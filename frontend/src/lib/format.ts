export function money(value: number | string | null) {
  return value === null
    ? "Unavailable"
    : new Intl.NumberFormat("en-IN", {
        style: "currency",
        currency: "INR",
        maximumFractionDigits: 2,
      }).format(Number(value));
}
export function measurement(value: number | string | null, unit: string) {
  return value === null
    ? "Unavailable"
    : `${Number(value).toLocaleString("en-IN")} ${unit}`;
}
export function localTime(value: string) {
  return (
    new Intl.DateTimeFormat("en-IN", {
      dateStyle: "medium",
      timeStyle: "short",
      timeZone: "Asia/Kolkata",
    }).format(new Date(value)) + " IST"
  );
}
export function exportCsv(
  rows: Record<string, string | number>[],
  filename: string,
) {
  if (!rows.length) return;
  const escape = (v: unknown) =>
    '"' +
    String(v)
      .replace(/^[=+@-]/, "'$&")
      .replaceAll('"', '""') +
    '"';
  const csv = [Object.keys(rows[0]), ...rows.map(Object.values)]
    .map((r) => r.map(escape).join(","))
    .join("\r\n");
  const url = URL.createObjectURL(
    new Blob([csv], { type: "text/csv;charset=utf-8;" }),
  );
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
