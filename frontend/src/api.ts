import type {
  AiReportResponse,
  AiProvider,
  AskResponse,
  CacheStatus,
  DashboardSummary,
  FaultCode,
  Machine,
  MachinePromptResponse,
  SyncFleetResponse,
  SyncLog,
  TelemetrySnapshot
} from "./types";

const API_BASE = "http://127.0.0.1:8890";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, options);
  if (!response.ok) {
    throw new Error(`API request failed: ${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<T>;
}

export function fetchSummary(): Promise<DashboardSummary> {
  return request<DashboardSummary>("/dashboard/summary");
}

export function fetchCacheStatus(): Promise<CacheStatus> {
  return request<CacheStatus>("/cache/status");
}

export function fetchSyncLogs(): Promise<SyncLog[]> {
  return request<SyncLog[]>("/sync/logs");
}

export function syncTrackunitFleet(): Promise<SyncFleetResponse> {
  return request<SyncFleetResponse>("/sync/trackunit/fleet", {
    method: "POST"
  });
}

export function fetchMachines(): Promise<Machine[]> {
  return request<Machine[]>("/machines");
}

export function fetchTelemetry(machineId: string): Promise<TelemetrySnapshot[]> {
  return request<TelemetrySnapshot[]>(`/machines/${machineId}/telemetry`);
}

export function fetchFaults(machineId: string): Promise<FaultCode[]> {
  return request<FaultCode[]>(`/machines/${machineId}/faults`);
}

export function generateMachinePrompt(machineId: string): Promise<MachinePromptResponse> {
  return request<MachinePromptResponse>(`/analysis/machine/${machineId}/prompt`, {
    method: "POST"
  });
}

export function generateMachineAiReport(machineId: string, aiProvider: AiProvider): Promise<AiReportResponse> {
  return request<AiReportResponse>(`/analysis/machine/${machineId}/ai-report`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({ ai_provider: aiProvider })
  });
}

export function generateFleetAiReport(aiProvider: AiProvider): Promise<AiReportResponse> {
  return request<AiReportResponse>("/analysis/fleet/ai-report", {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({ ai_provider: aiProvider })
  });
}

export function askFleetAssistant(question: string, language: "zh" | "en" | "auto" = "auto", aiProvider: AiProvider = "ollama_local"): Promise<AskResponse> {
  return request<AskResponse>("/ask", {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({ question, language, ai_provider: aiProvider })
  });
}
