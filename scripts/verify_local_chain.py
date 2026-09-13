"""Exercise the real Python EVM adapter; requires the local chain and deployment."""

import hashlib
import json
from uuid import uuid4

from app.adapters.ledger.evm import publish, verify_receipt
from app.db.models import Receipt

payload = {"schema": "adapter-test-1", "source": "synthetic", "nonce": str(uuid4())}
digest = hashlib.sha256(
    json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
).hexdigest()
receipt = Receipt(id=uuid4(), payload=payload, payload_hash=digest, status="pending")
publish(receipt)
assert receipt.status == "confirmed" and receipt.transaction_hash and receipt.block_number
assert verify_receipt(receipt)["verified"]
transaction = receipt.transaction_hash
publish(receipt)
assert receipt.transaction_hash == transaction
# Simulate process loss after mining but before PostgreSQL saved the transaction.
receipt.transaction_hash = None
receipt.block_number = None
publish(receipt)
assert receipt.transaction_hash == transaction and receipt.block_number
receipt.payload = {**payload, "source": "tampered"}
assert not verify_receipt(receipt)["verified"]
print("5 adapter checks passed: publication, readback, retry, crash recovery, tamper detection.")
