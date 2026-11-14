export const dynamic = "force-dynamic";

export function GET() {
  const configured = process.env.BACKEND_URL || "http://127.0.0.1:8000";
  try {
    const host = new URL(configured).hostname.toLowerCase();
    const destination = host === "localhost" || host === "[::1]" || host === "127.0.0.1"
      ? "This PC"
      : host.endsWith(".trycloudflare.com") || host.endsWith(".colab.research.google.com")
        ? "Colab / tunnel backend"
        : "Remote backend";
    return Response.json({ destination }, { headers: { "Cache-Control": "no-store" } });
  } catch {
    return Response.json({ destination: "Unknown backend" });
  }
}
