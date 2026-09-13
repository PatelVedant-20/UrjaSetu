# Local receipt registry

`npm ci`, then `npm run node` in one terminal and `npm run deploy` in another. `npm test` exercises the deployed contract. The root `make demo` handles these steps after dependencies are installed.

Ganache is bound to localhost with chain ID 1337 and deterministic development accounts. These are public test credentials, not accounts for real assets. Deployment reuses an existing contract on the same persistent chain. `.chain/` and `deployment.json` are runtime state excluded from Git.

The registry accepts one SHA-256 digest per opaque receipt key. Only its deployment publisher may write. The API worker stores transaction/block references, retries pending publications and recovers mined events after a process interruption. Browser verification compares canonical database payloads with contract storage. See `../scripts/verify_local_chain.py` for real adapter checks.

The lock file marks Ganache's bundled Darwin-only `fsevents` package optional, matching its parent chokidar dependency; otherwise npm's generated bundled metadata makes Linux `npm ci` fail with EBADPLATFORM. The Solidity compiler and EVM dependencies are pinned in package.json.

A production network needs authenticated signing, durable key custody and independently operated validators. This local demonstration does not provide those properties.
