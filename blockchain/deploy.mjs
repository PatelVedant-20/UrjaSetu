import { readFile, writeFile } from 'node:fs/promises';
import solc from 'solc';
import { JsonRpcProvider, ContractFactory, Interface } from 'ethers';

const source = await readFile(new URL('./ReceiptRegistry.sol', import.meta.url), 'utf8');
const input = {language:'Solidity', sources:{'ReceiptRegistry.sol':{content:source}}, settings:{evmVersion:'paris', outputSelection:{'*':{'*':['abi','evm.bytecode.object']}}}};
const output = JSON.parse(solc.compile(JSON.stringify(input)));
const errors = output.errors?.filter(e=>e.severity==='error') || [];
if (errors.length) throw new Error(errors.map(e=>e.formattedMessage).join('\n'));
const artifact = output.contracts['ReceiptRegistry.sol'].ReceiptRegistry;
const provider = new JsonRpcProvider(process.env.BLOCKCHAIN_RPC_URL || 'http://127.0.0.1:8545');
const network = await provider.getNetwork();
if (network.chainId !== 1337n) throw new Error('This deploy script is restricted to the local development chain.');
const signer = await provider.getSigner(0);
try {
  const existing = JSON.parse(await readFile(new URL('./deployment.json', import.meta.url), 'utf8'));
  if (existing.chainId === Number(network.chainId) && await provider.getCode(existing.address) !== '0x') {
    console.log(JSON.stringify({network:existing.network,address:existing.address,reused:true}));
    process.exit(0);
  }
} catch (error) {
  if (error.code !== 'ENOENT') throw error;
}
const contract = await new ContractFactory(artifact.abi, artifact.evm.bytecode.object, signer).deploy();
await contract.waitForDeployment();
const iface = new Interface(artifact.abi);
const deployment = {network:'Local EVM development chain', chainId:Number(network.chainId), address:await contract.getAddress(), publisher:await signer.getAddress(), abi:artifact.abi, recordSelector:iface.getFunction('record').selector, readSelector:iface.getFunction('receipts').selector};
await writeFile(new URL('./deployment.json', import.meta.url), JSON.stringify(deployment,null,2));
console.log(JSON.stringify({network:deployment.network,address:deployment.address,chainId:deployment.chainId}));
