export type UploadDirective = {
  type: "upload";
  uploadUrl: string;
  keyPrefix: string;
  expiresInSeconds?: number;
  bucket?: string;
};

export function parseUploadDirective(text: string): UploadDirective | null {
  try {
    const block = text.match(/```json\s*([\s\S]*?)```/i)?.[1] ?? text;
    const jsons = block.match(/{[\s\S]*?}/g) || [];
    for (const j of jsons) {
      const parsed = JSON.parse(j);
      if (parsed?.type === "upload" && parsed?.uploadUrl && parsed?.keyPrefix) {
        return parsed as UploadDirective;
      }
    }
  } catch {}
  return null;
}

export async function putToPresigned(url: string, file: File) {
  const r = await fetch(url, {
    method: "PUT",
    headers: { "Content-Type": file.type || "application/octet-stream" },
    body: file,
  });
  if (!r.ok) throw new Error(`upload PUT ${r.status}`);
}
