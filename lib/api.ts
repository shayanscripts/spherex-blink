export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api/science${path}`, { ...init, cache: "no-store" });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new Error("Cannot reach the science service. Start the Python backend on port 8000 and reconnect.");
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const detail = typeof body?.detail === "string" ? body.detail : null;
    throw new Error(detail || (response.status >= 500 ? "Science service unavailable. Start the Python backend on port 8000 and reconnect." : `Request failed (${response.status}).`));
  }
  return response.json();
}
