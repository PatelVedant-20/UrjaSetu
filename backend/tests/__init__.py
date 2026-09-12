"""UrjaSetu backend test suite.

This file makes `tests` a regular package so every test package below it gets a
fully-qualified module name. Without it, `tests/forecast/` and
`tests/fixtures/forecast/` both resolved to the top-level name `forecast` and
collided, which stopped the whole suite from being collected.
"""
