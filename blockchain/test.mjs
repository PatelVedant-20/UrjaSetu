import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {randomBytes} from 'node:crypto';
import {Contract, JsonRpcProvider, hexlify} from 'ethers';

const deployment = JSON.parse(await readFile(new URL('./deployment.json',import.meta.url),'utf8'));
const provider = new JsonRpcProvider('http://127.0.0.1:8545');
assert.equal((await provider.getNetwork()).chainId,1337n);
const contract = new Contract(deployment.address,deployment.abi,await provider.getSigner(0));
const key = hexlify(randomBytes(32)), hash = hexlify(randomBytes(32));
const tx = await contract.record(key,hash);
const receipt = await tx.wait();
assert.equal(receipt.status,1);
assert.equal(await contract.receipts(key),hash);
await assert.rejects(contract.record(key,hexlify(randomBytes(32))), 'Receipt must be immutable');
const stranger = contract.connect(await provider.getSigner(1));
await assert.rejects(stranger.record(hexlify(randomBytes(32)),hash),'Only publisher may write');
assert.equal(await contract.receipts(key),hash);
console.log('4 contract checks passed: mined receipt, readback, duplicate refusal, publisher authorization.');
