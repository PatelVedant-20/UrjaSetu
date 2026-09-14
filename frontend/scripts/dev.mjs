import { spawn } from "node:child_process";
import { existsSync, mkdirSync, openSync, closeSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { setTimeout as delay } from "node:timers/promises";

const frontend = fileURLToPath(new URL("../", import.meta.url));
const root = fileURLToPath(new URL("../../", import.meta.url));
const target = process.env.BACKEND_TARGET || "http://127.0.0.1:8000";
const children = new Set();
let stopping = false;

function stop(code) {
  if (stopping) return;
  stopping = true;
  process.exitCode = code;
  for (const child of children) child.kill("SIGTERM");
  const timeout = setTimeout(() => {
    for (const child of children) child.kill("SIGKILL");
  }, 5000);
  timeout.unref();
}

process.on("SIGINT", () => stop(130));
process.on("SIGTERM", () => stop(143));

function start(command, args, cwd, persistent = true, log) {
  const fd = log ? openSync(log, "a") : undefined;
  const child = spawn(command, args, {
    cwd,
    stdio: fd === undefined ? "inherit" : ["ignore", fd, fd],
  });
  if (fd !== undefined) closeSync(fd);
  children.add(child);
  child.on("error", (error) => {
    console.error(`[dev] Could not start ${command}: ${error.message}`);
    children.delete(child);
    stop(1);
  });
  child.on("exit", (code) => {
    children.delete(child);
    if (!stopping && (persistent || code !== 0)) {
      console.error(`[dev] ${command} exited; stopping development servers.`);
      stop(code || 1);
    }
  });
  return child;
}

async function probe(path) {
  try {
    return await fetch(new URL(path, target), {
      signal: AbortSignal.timeout(1500),
    });
  } catch {
    return null;
  }
}

async function chainReady() {
  try {
    const response = await fetch(
      process.env.BLOCKCHAIN_RPC_URL || "http://127.0.0.1:8545",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          jsonrpc: "2.0",
          id: 1,
          method: "eth_chainId",
          params: [],
        }),
        signal: AbortSignal.timeout(1500),
      },
    );
    const result = await response.json();
    return response.ok && result.result === "0x539";
  } catch {
    return false;
  }
}

async function startBlockchain() {
  const blockchain = `${root}blockchain`;
  if (!existsSync(`${blockchain}/node_modules/ganache/dist/node/cli.js`))
    throw new Error(
      "Install blockchain dependencies: npm --prefix blockchain ci (from the repository root).",
    );
  if (!(await chainReady())) {
    if (process.env.BLOCKCHAIN_RPC_URL)
      throw new Error(
        "Configured BLOCKCHAIN_RPC_URL is unavailable or is not local chain 1337.",
      );
    mkdirSync(`${root}.runtime`, { recursive: true });
    console.log(
      "[dev] Starting persistent local blockchain. Logs: .runtime/blockchain.log",
    );
    start(
      process.execPath,
      [
        "node_modules/ganache/dist/node/cli.js",
        "--server.host",
        "127.0.0.1",
        "--chain.chainId",
        "1337",
        "--wallet.deterministic",
        "--database.dbPath",
        ".chain",
        "--logging.quiet",
      ],
      blockchain,
      true,
      `${root}.runtime/blockchain.log`,
    );
    const deadline = Date.now() + 15000;
    while (!stopping && Date.now() < deadline && !(await chainReady()))
      await delay(300);
    if (stopping) return;
    if (!(await chainReady()))
      throw new Error(
        "Local blockchain did not start. Inspect .runtime/blockchain.log.",
      );
  }
  const deploy = start(process.execPath, ["deploy.mjs"], blockchain, false);
  await new Promise((resolve, reject) => {
    deploy.on("error", reject);
    deploy.on("exit", (code) =>
      code === 0
        ? resolve()
        : reject(new Error("Receipt contract setup failed.")),
    );
  });
}

try {
  if (!process.env.BACKEND_TARGET) await startBlockchain();
  if (stopping) process.exit(process.exitCode || 1);
  let ready = await probe("/health/ready");
  if (!ready?.ok) {
    // An existing API with an unavailable database must not be started twice.
    const live = await probe("/health");
    if (!live && !ready && !process.env.BACKEND_TARGET) {
      const python = `${root}.venv/bin/python`;
      if (!existsSync(python)) {
        throw new Error(
          "Python environment missing. Run make install from the repository root.",
        );
      }
      console.log("[dev] Starting the energy API on http://127.0.0.1:8000…");
      start(
        python,
        [
          "-m",
          "uvicorn",
          "app.main:app",
          "--app-dir",
          "backend",
          "--host",
          "127.0.0.1",
          "--port",
          "8000",
        ],
        root,
      );
    }
    console.log(`[dev] Waiting for the energy service at ${target}…`);
    const deadline = Date.now() + 30000;
    while (!stopping && !ready?.ok && Date.now() < deadline) {
      await delay(500);
      ready = await probe("/health/ready");
    }
    if (!stopping && !ready?.ok) {
      throw new Error(
        "Energy service is not ready. Check the API output and PostgreSQL. " +
          "For first-time local setup, run make up and make migrate bootstrap from the repository root. " +
          "If BACKEND_TARGET is set, ensure that service is running and reachable.",
      );
    }
  }
  if (!stopping) {
    console.log("[dev] Energy service ready. Starting the website.");
    start(
      process.execPath,
      [
        `${frontend}node_modules/vite/bin/vite.js`,
        "--host",
        "0.0.0.0",
        ...process.argv.slice(2),
      ],
      frontend,
    );
  }
} catch (error) {
  console.error(`[dev] ${error.message}`);
  stop(1);
}
