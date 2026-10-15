import useSWR, { type SWRConfiguration } from "swr";

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, detail: unknown) {
    super(typeof detail === "string" ? detail : formatDetail(detail));
    this.status = status;
    this.detail = detail;
  }
}

function formatDetail(d: unknown): string {
  if (!d) return "Request failed";
  if (Array.isArray(d)) {
    // FastAPI validation errors
    return d.map((e: { loc?: unknown[]; msg?: string }) => `${(e.loc ?? []).slice(1).join(".")}: ${e.msg}`).join("; ");
  }
  if (typeof d === "object" && d !== null && "errors" in d) return (d as { errors: string[] }).errors.join("; ");
  return JSON.stringify(d);
}

async function handle<T>(r: Response): Promise<T> {
  if (!r.ok) {
    let detail: unknown = `${r.status} ${r.statusText}`;
    try {
      const j = await r.json();
      detail = j.detail ?? j;
    } catch {
      if (r.status === 500 || r.status === 502 || r.status === 503)
        detail = "The calculation service is unreachable. Start the backend (see README) and retry.";
    }
    throw new ApiError(r.status, detail);
  }
  return r.json() as Promise<T>;
}

export const api = {
  get: <T>(path: string) => fetch(path, { cache: "no-store" }).then((r) => handle<T>(r)),
  post: <T>(path: string, body?: unknown) =>
    fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body) }).then((r) => handle<T>(r)),
  put: <T>(path: string, body: unknown) =>
    fetch(path, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }).then((r) => handle<T>(r)),
  del: <T>(path: string) => fetch(path, { method: "DELETE" }).then((r) => handle<T>(r)),
  upload: <T>(path: string, form: FormData) => fetch(path, { method: "POST", body: form }).then((r) => handle<T>(r)),
};

const opts: SWRConfiguration = {
  revalidateOnFocus: false,
  keepPreviousData: true,
  // retry only transient failures (network, proxy, 5xx), never validation errors
  onErrorRetry: (error: ApiError, _key, _cfg, revalidate, { retryCount }) => {
    if (retryCount >= 2 || (error.status && error.status < 500)) return;
    setTimeout(() => revalidate({ retryCount }), 800 * (retryCount + 1));
  },
};

export function useGet<T>(path: string | null) {
  return useSWR<T, ApiError>(path, (p: string) => api.get<T>(p), opts);
}

/** POST used as a query (deterministic computation keyed on its body). */
export function usePostQuery<T>(path: string | null, body: unknown) {
  return useSWR<T, ApiError>(path ? [path, JSON.stringify(body)] : null, ([p, b]: [string, string]) => api.post<T>(p, JSON.parse(b)), opts);
}
