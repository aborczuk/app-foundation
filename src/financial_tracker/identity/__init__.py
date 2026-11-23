"""Identity resolution and authorization primitives for financial tracker data."""

from .resolver import (
    AuthorizationError,
    AuthorizationScope,
    IdentityResolutionError,
    IssuerTickerAlias,
    build_authorization_scope,
    normalize_cik,
    normalize_ticker,
    require_issuer_access,
    require_portfolio_access,
    resolve_issuer,
)

__all__ = [
    "AuthorizationError",
    "AuthorizationScope",
    "IdentityResolutionError",
    "IssuerTickerAlias",
    "build_authorization_scope",
    "normalize_cik",
    "normalize_ticker",
    "require_issuer_access",
    "require_portfolio_access",
    "resolve_issuer",
]
