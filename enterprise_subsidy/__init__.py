"""
enterprise-subsidy module.
"""
# This repo is a deployed service (pyproject.toml's [tool.uv] package = false),
# not an installed package, so importlib.metadata.version() has nothing to look
# up here. Bump this alongside pyproject.toml's version on release.
__version__ = '1.0.1'
