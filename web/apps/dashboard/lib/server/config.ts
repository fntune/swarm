export function apiBaseUrl(): string {
  const url = process.env.SPAWND_API_URL;
  if (!url) {
    throw new Error("SPAWND_API_URL is required (e.g. http://localhost:8765)");
  }
  return url.replace(/\/$/, "");
}
