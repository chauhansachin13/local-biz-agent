export async function handler() {
  return {
    statusCode: 200,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      service: "BizPresence AI (Netlify Edge/Function)",
      status: "healthy",
      timestamp: new Date().toISOString(),
    }),
  };
}
