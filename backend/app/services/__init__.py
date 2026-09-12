"""Services — coordinate repositories and own transaction boundaries.

A service knows nothing about HTTP: it takes plain values and domain types,
raises domain errors, and returns persistence or domain objects. Translating
those errors into status codes is handled once by the exception handlers in
`app.core.errors`.

Service-layer errors live in `app.core.errors` (`NotFoundError`,
`ConflictError`, `UnprocessableError`) rather than here, so the whole error
contract has exactly one home.
"""
