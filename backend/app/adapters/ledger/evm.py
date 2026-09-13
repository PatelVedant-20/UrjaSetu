"""Local EVM publication and readback. Does not silently invent receipts."""

import hashlib
import json
from pathlib import Path
from typing import Any

import httpx

from app.core.config import get_settings
from app.db.models import Receipt

DEPLOYMENT = Path(__file__).resolve().parents[4] / "blockchain" / "deployment.json"


def rpc(method: str, params: list[Any]) -> Any:
    config = get_settings()
    # Unlocked account RPC is explicitly a local development integration.
    from urllib.parse import urlparse

    if urlparse(config.blockchain_rpc_url).hostname not in ("localhost", "127.0.0.1"):
        raise ValueError("Unlocked signing is restricted to a local development node.")
    response = httpx.post(
        config.blockchain_rpc_url,
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
        timeout=5,
    )
    response.raise_for_status()
    result = response.json()
    if "error" in result:
        raise ValueError(result["error"].get("message", "RPC failure"))
    return result["result"]


def deployment() -> dict[str, Any]:
    data = json.loads(DEPLOYMENT.read_text())
    if int(rpc("eth_chainId", []), 16) != data["chainId"] or data["chainId"] != 1337:
        raise ValueError("Deployment network mismatch.")
    if rpc("eth_getCode", [data["address"], "latest"]) == "0x":
        raise ValueError("Receipt contract is not deployed on this node.")
    return data


def key_for(receipt: Receipt) -> str:
    return hashlib.sha256(("urjasetu-receipt-1:" + str(receipt.id)).encode()).hexdigest()


def publish(receipt: Receipt) -> None:
    data = deployment()
    key = key_for(receipt)
    existing = rpc(
        "eth_call", [{"to": data["address"], "data": data["readSelector"] + key}, "latest"]
    )
    if existing != "0x" + "00" * 32 and existing != "0x" + receipt.payload_hash:
        raise ValueError("On-chain receipt conflicts with database evidence.")
    if not receipt.transaction_hash and existing == "0x" + receipt.payload_hash:
        # Recover publication after a process crash between chain mining and DB commit.
        logs = rpc(
            "eth_getLogs",
            [
                {
                    "address": data["address"],
                    "fromBlock": "0x0",
                    "toBlock": "latest",
                    "topics": [None, "0x" + key],
                }
            ],
        )
        if not logs:
            raise ValueError("Receipt hash exists but its publication event is missing.")
        receipt.transaction_hash = logs[0]["transactionHash"]
    if not receipt.transaction_hash and existing == "0x" + "00" * 32:
        receipt.transaction_hash = rpc(
            "eth_sendTransaction",
            [
                {
                    "from": data["publisher"],
                    "to": data["address"],
                    "gas": hex(150000),
                    "data": data["recordSelector"] + key + receipt.payload_hash,
                }
            ],
        )
    if receipt.transaction_hash:
        tx = rpc("eth_getTransactionReceipt", [receipt.transaction_hash])
        if not tx:
            receipt.status = "submitted"
            return
        if int(tx["status"], 16) != 1:
            raise ValueError("Receipt transaction reverted.")
        receipt.block_number = int(tx["blockNumber"], 16)
    receipt.chain_id = data["chainId"]
    receipt.contract_address = data["address"]
    receipt.status, receipt.error = "confirmed", None


def verify_receipt(receipt: Receipt) -> dict[str, Any]:
    calculated = hashlib.sha256(
        json.dumps(receipt.payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    try:
        data = deployment()
        value = rpc(
            "eth_call",
            [{"to": data["address"], "data": data["readSelector"] + key_for(receipt)}, "latest"],
        )
        return {
            "verified": calculated == receipt.payload_hash and value == "0x" + calculated,
            "network": data["network"],
            "chain_id": data["chainId"],
            "contract": data["address"],
            "transaction_hash": receipt.transaction_hash,
            "block_number": receipt.block_number,
            "meaning": "Record integrity; energy measurements and INR accounting are simulated.",
        }
    except Exception as exc:
        return {"verified": False, "error": str(exc)}
