export class ApiError extends Error {
  constructor(
    message: string,
    public code: string,
    public requestId?: string,
  ) {
    super(message);
  }
}

/** Cookie-authenticated API. The custom header and strict cookies protect writes. */
export async function workspaceRequest<T>(
  path: string,
  body?: unknown,
  method?: string,
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch(`/api/v1${path}`, {
    method: method || (body === undefined ? "GET" : "POST"),
    credentials: "same-origin",
    signal,
    cache: "no-store",
    headers: {
      "Content-Type": "application/json",
      "X-Requested-With": "UrjaSetu",
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const detail =
      typeof data?.detail === "string" ? data.detail : data?.error?.message;
    throw new ApiError(
      detail ||
        `Request failed (${response.status}). Check the supplied fields.`,
      String(response.status),
    );
  }
  if (data === null)
    throw new ApiError(
      "API returned no JSON. Check the backend connection.",
      "INVALID_RESPONSE",
    );
  return data as T;
}

export function subscribeWorkspace(
  refresh: () => void,
  status: (value: string) => void,
) {
  let stopped = false;
  let socket: WebSocket | undefined;
  let timer: ReturnType<typeof setTimeout>;
  let attempt = 0;
  const connect = () => {
    status("Connecting");
    socket = new WebSocket(
      `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/workspace`,
    );
    socket.onopen = () => {
      attempt = 0;
      status("Connected");
    };
    socket.onmessage = () => refresh();
    socket.onclose = () => {
      status("Reconnecting");
      if (!stopped)
        timer = setTimeout(connect, Math.min(30000, 1000 * 2 ** attempt++));
    };
    socket.onerror = () => status("Connection interrupted");
  };
  connect();
  return () => {
    stopped = true;
    clearTimeout(timer);
    socket?.close();
  };
}
export async function request<T>(
  path: string,
  userId = "",
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch(path, {
    headers: userId ? { "X-User-Id": userId } : {},
    signal,
  });
  const body = await response.json().catch(() => null);
  if (!response.ok)
    throw new ApiError(
      body?.error?.message || `Request failed (${response.status})`,
      body?.error?.code || "HTTP_ERROR",
      body?.error?.request_id,
    );
  if (body === null)
    throw new ApiError(
      "The server did not return JSON. Check your API proxy.",
      "INVALID_RESPONSE",
    );
  return body as T;
}
export type Connection = { userId: string; siteId: string; sessionId: string };
export function readConnection(): Connection {
  try {
    return {
      ...{ userId: "", siteId: "", sessionId: "" },
      ...JSON.parse(localStorage.getItem("urjasetu.connection") || "{}"),
    };
  } catch {
    return { userId: "", siteId: "", sessionId: "" };
  }
}
export function subscribe(
  channel: "market" | "grid" | "telemetry",
  userId: string,
  onRefresh: () => void,
  onStatus: (s: string) => void,
) {
  let stopped = false;
  let socket: WebSocket;
  let timer: ReturnType<typeof setTimeout>;
  let attempt = 0;
  function connect() {
    onStatus("Connecting");
    socket = new WebSocket(
      `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/${channel}?user_id=${encodeURIComponent(userId)}`,
    );
    socket.onopen = () => {
      attempt = 0;
      onStatus("Connected");
    };
    socket.onmessage = () => onRefresh();
    socket.onerror = () => onStatus("Connection error");
    socket.onclose = () => {
      onStatus("Disconnected");
      if (!stopped)
        timer = setTimeout(connect, Math.min(30000, 1000 * 2 ** attempt++));
    };
  }
  connect();
  return () => {
    stopped = true;
    clearTimeout(timer);
    socket?.close();
  };
}
