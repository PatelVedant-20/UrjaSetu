export class ApiError extends Error {
  constructor(
    message: string,
    public code: string,
    public requestId?: string,
  ) {
    super(message);
  }
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
