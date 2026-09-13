// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// Platform-attested receipts. No currency, customer identities or meter readings.
contract ReceiptRegistry {
    address public immutable publisher;
    mapping(bytes32 => bytes32) public receipts;
    event ReceiptRecorded(bytes32 indexed key, bytes32 digest);
    constructor() { publisher = msg.sender; }
    function record(bytes32 key, bytes32 digest) external {
        require(msg.sender == publisher, "publisher only");
        require(digest != bytes32(0), "empty digest");
        require(receipts[key] == bytes32(0), "already recorded");
        receipts[key] = digest;
        emit ReceiptRecorded(key, digest);
    }
}
