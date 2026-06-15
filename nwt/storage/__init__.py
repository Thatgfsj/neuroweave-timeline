"""Local filesystem storage for NWT.

Everything lives under a single ``.nwt/`` directory inside the project root.
The on-disk layout mirrors the spec — see ``docs/architecture.md`` for the
full picture and the rationale for keeping storage dead simple.
"""
