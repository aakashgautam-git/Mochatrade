"""Shared pytest fixtures.

riskengine tests must not need the `db` fixture. If one does, a Django
dependency has leaked into the engine and test_engine_purity will catch it.
"""
