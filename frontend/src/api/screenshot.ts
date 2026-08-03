export interface ParsedLine {
  label: string;
  value: number;
}

export interface ParseScreenshotResult {
  lines: ParsedLine[];
  total: number | null;
  sheet_values: Record<string, number>;
  unmapped: { label: string; value: number }[];
  computed_total: number;
}

export const screenshotApi = {
  async parse(file: File): Promise<ParseScreenshotResult> {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch("/api/screenshot/parse", { method: "POST", body: form });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail ?? res.statusText);
    }
    return res.json();
  },
};
