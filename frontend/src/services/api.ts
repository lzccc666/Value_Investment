export type HealthResponse = {
  status: "ok";
  service: string;
  version: string;
  environment: string;
  checked_at: string;
};

export type Company = {
  id: number;
  ticker: string;
  exchange: string;
  name: string;
  industry: string | null;
  description: string | null;
  listed_date: string | null;
  status: string;
  tags: string[];
  created_at: string;
  updated_at: string;
};

export type CompanyListResponse = {
  items: Company[];
  total: number;
  limit: number;
  offset: number;
};

type RequestJsonOptions = {
  signal?: AbortSignal;
};

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "/api";

async function fetchJson<T>(path: string, options: RequestJsonOptions = {}): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    signal: options.signal
  });

  if (!response.ok) {
    const detail = await readErrorDetail(response);
    throw new Error(detail ?? `Request failed: ${response.status}`);
  }

  return response.json() as Promise<T>;
}

async function readErrorDetail(response: Response): Promise<string | null> {
  try {
    const payload = (await response.json()) as { detail?: string };
    return payload.detail ?? null;
  } catch {
    return null;
  }
}

export async function getHealth(): Promise<HealthResponse> {
  return fetchJson<HealthResponse>("/health");
}

export async function getCompanies(
  params: { q?: string; limit?: number; offset?: number; signal?: AbortSignal } = {}
): Promise<CompanyListResponse> {
  const searchParams = new URLSearchParams();

  if (params.q) {
    searchParams.set("q", params.q);
  }
  if (typeof params.limit === "number") {
    searchParams.set("limit", String(params.limit));
  }
  if (typeof params.offset === "number") {
    searchParams.set("offset", String(params.offset));
  }

  const queryString = searchParams.toString();
  return fetchJson<CompanyListResponse>(`/companies${queryString ? `?${queryString}` : ""}`, {
    signal: params.signal
  });
}

export async function getCompany(companyId: number, signal?: AbortSignal): Promise<Company> {
  return fetchJson<Company>(`/companies/${companyId}`, { signal });
}
