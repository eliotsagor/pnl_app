export const exportApi = {
  async generate(): Promise<{ blob: Blob; filename: string }> {
    const res = await fetch("/api/export", { method: "POST" });
    if (!res.ok) throw new Error(res.statusText);
    const disposition = res.headers.get("content-disposition") ?? "";
    const match = /filename=([^;]+)/.exec(disposition);
    const filename = match ? match[1].trim() : "PnL_Export.xlsx";
    const blob = await res.blob();
    return { blob, filename };
  },
  async stats(): Promise<{ days_with_data: number }> {
    const res = await fetch("/api/stats");
    return res.json();
  },
};
