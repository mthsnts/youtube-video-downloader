import { storeGet, storeSet } from "./storage.js";

let apiKey = storeGet("apiKey", "");

/** Calls the API. When the server asks for its password, prompts once and retries. */
export async function api(path, body, { askKey = true } = {}) {
  const res = await fetch(path, {
    method: body ? "POST" : "GET",
    headers: { "Content-Type": "application/json", ...(apiKey ? { "X-Api-Key": apiKey } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({ error: "Resposta inválida do servidor." }));
  if (res.status === 401 && data.auth && askKey) {
    const key = window.prompt("Este servidor pede uma senha de acesso:");
    if (key) {
      apiKey = key;
      storeSet("apiKey", key);
      return api(path, body);
    }
  }
  if (!res.ok) throw new Error(data.error || `Erro ${res.status}`);
  return data;
}

/** Link to a finished file; the password goes in the query because the browser downloads it directly. */
export function fileUrl(jobId, suffix) {
  return `/api/jobs/${jobId}${suffix}${apiKey ? `?key=${encodeURIComponent(apiKey)}` : ""}`;
}
