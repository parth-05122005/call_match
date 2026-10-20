// Sends a request with the X-Organization header and returns the JSON body.
// Throws an Error with the server's message if the response is not OK.
export async function apiRequest(path, organization, options = {}) {
  const response = await fetch(`/api${path}`, {
    ...options,
    headers: { "X-Organization": organization, ...options.headers },
  });

  const body = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(body?.detail || `Request failed (${response.status})`);
  }
  return body;
}

// Formats a number or numeric string as money, e.g. "25000.00" -> "$25,000.00".
export function formatMoney(value) {
  return Number(value).toLocaleString("en-US", { style: "currency", currency: "USD" });
}