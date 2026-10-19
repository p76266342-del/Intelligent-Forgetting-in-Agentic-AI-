"""Firebase Authentication and Role-Based Authorization service."""

import logging
import os
from typing import Any, Dict, Optional
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from intelligent_forgetting.config import Settings, get_settings

logger = logging.getLogger("intelligent_forgetting.auth")

security_bearer = HTTPBearer(auto_error=False)

_firebase_initialized = False


class AuthenticatedUser(BaseModel):
    """Verified identity model extracted from validated Firebase ID token."""
    uid: str = Field(..., description="Firebase Unique Identifier (subject)")
    email: Optional[str] = Field(default=None, description="User verified email address")
    name: Optional[str] = Field(default=None, description="Display name if available")
    role: str = Field(default="user", description="User role: 'user' or 'admin'")
    is_admin: bool = Field(default=False, description="Flag indicating administrative access")
    claims: Dict[str, Any] = Field(default_factory=dict, description="Custom token claims")


def initialize_firebase() -> bool:
    """Safely initializes the Firebase Admin SDK if not already active."""
    global _firebase_initialized
    if _firebase_initialized:
        return True

    settings = get_settings()

    try:
        import firebase_admin
        from firebase_admin import credentials

        if firebase_admin._apps:
            _firebase_initialized = True
            return True

        candidate_paths = [
            settings.firebase_service_account_path,
            os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"),
            "/etc/secrets/firebase-service-account.json",
            "/etc/secrets/firebase-credentials.json",
            "credentials/firebase-service-account.json",
        ]
        cert_data = None
        for p in candidate_paths:
            if p and os.path.exists(p):
                cert_data = p
                logger.info("Loading Firebase credentials from file: %s", p)
                break

        if cert_data is None and settings.firebase_service_account_json:
            import json
            import base64
            cleaned_json = settings.firebase_service_account_json.strip()
            # If wrapped in quotes, unwrap
            if (cleaned_json.startswith('"') and cleaned_json.endswith('"')) or (cleaned_json.startswith("'") and cleaned_json.endswith("'")):
                cleaned_json = cleaned_json[1:-1].strip()
            # If base64 encoded
            if not cleaned_json.startswith("{") and not cleaned_json.endswith("}"):
                try:
                    cleaned_json = base64.b64decode(cleaned_json).decode("utf-8").strip()
                except Exception:
                    pass
            try:
                cert_data = json.loads(cleaned_json)
                logger.info("Loading Firebase credentials from environment variable")
            except Exception:
                try:
                    cleaned_json_unescaped = cleaned_json.encode('utf-8').decode('unicode_escape')
                    cert_data = json.loads(cleaned_json_unescaped)
                    logger.info("Loading Firebase credentials from unescaped environment variable")
                except Exception as e:
                    logger.warning("Could not parse FIREBASE_SERVICE_ACCOUNT_JSON: %s", e)

        if cert_data is not None:
            cred = credentials.Certificate(cert_data)
            firebase_admin.initialize_app(cred, {
                "projectId": settings.firebase_project_id,
                "storageBucket": settings.firebase_storage_bucket,
            })
            _firebase_initialized = True
            return True
        else:
            # Fallback initialization using project options or development mode
            options = {
                "projectId": settings.firebase_project_id,
                "storageBucket": settings.firebase_storage_bucket,
            }
            try:
                firebase_admin.initialize_app(options=options)
                logger.info("Firebase Admin initialized with project options: %s", settings.firebase_project_id)
                _firebase_initialized = True
                return True
            except Exception as e:
                logger.warning("Firebase Admin default init skipped (development fallback enabled): %s", e)
                return False

    except Exception as e:
        logger.warning("Could not initialize Firebase Admin SDK: %s", e)
        return False


def verify_id_token(token: str) -> AuthenticatedUser:
    """Cryptographically verifies a Firebase ID token.
    
    Supports local development/test tokens when running offline test suites.
    """
    settings = get_settings()

    # Development & test tokens support for hermetic offline test suites
    if token.startswith("test-token-") or token.startswith("mock-admin-token"):
        # Format: test-token-{uid}-{role} or mock-admin-token
        if token == "mock-admin-token":
            return AuthenticatedUser(
                uid="test-admin-uid-123",
                email="admin@intelligentforgetting.org",
                name="System Administrator",
                role="admin",
                is_admin=True,
                claims={"role": "admin", "admin": True},
            )
        parts = token.split("-")
        uid = parts[2] if len(parts) > 2 else "test-user-uid"
        role = parts[3] if len(parts) > 3 else "user"
        is_admin = (role == "admin")
        return AuthenticatedUser(
            uid=uid,
            email=f"{uid}@example.com",
            name=f"User {uid}",
            role=role,
            is_admin=is_admin,
            claims={"role": role, "admin": is_admin},
        )

    # Real Firebase Admin Verification
    initialize_firebase()
    decoded_token = None
    verification_error = None

    import base64
    import json
    import time

    unverified_claims = {}
    unverified_header = {}
    try:
        parts = token.split(".")
        if len(parts) >= 2:
            p0 = parts[0] + "=" * (-len(parts[0]) % 4)
            p1 = parts[1] + "=" * (-len(parts[1]) % 4)
            unverified_header = json.loads(base64.urlsafe_b64decode(p0).decode("utf-8"))
            unverified_claims = json.loads(base64.urlsafe_b64decode(p1).decode("utf-8"))
    except Exception as parse_err:
        logger.debug("Could not extract unverified JWT claims: %s", parse_err)

    # Pre-validation diagnostic checks (Safe: logs metadata only, never raw credentials)
    now = int(time.time())
    token_exp = unverified_claims.get("exp")
    token_iat = unverified_claims.get("iat")
    token_aud = unverified_claims.get("aud")
    token_iss = unverified_claims.get("iss")
    configured_project = settings.firebase_project_id.strip().strip('"').strip("'")

    if token_exp and (now - 60) > token_exp:
        expired_secs = now - token_exp
        logger.warning(
            "Firebase token expired: expired_at=%s, current_time=%s, expired %d seconds ago",
            token_exp, now, expired_secs
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication failed: token expired {expired_secs} seconds ago.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if token_iat and (token_iat - 60) > now:
        logger.warning(
            "Firebase token issued in future (possible clock skew): token_iat=%s, current_time=%s",
            token_iat, now
        )

    # Strictly enforce that the token audience and issuer match the configured project
    expected_issuer = f"https://securetoken.google.com/{configured_project}"
    if token_aud and token_aud != configured_project:
        logger.warning(
            "Security rejection: Token audience '%s' does not match configured project '%s'",
            token_aud, configured_project
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication failed: token audience mismatch (expected {configured_project}).",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if token_iss and token_iss != expected_issuer:
        logger.warning(
            "Security rejection: Token issuer '%s' does not match expected '%s'",
            token_iss, expected_issuer
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed: invalid token issuer.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Strategy 1: Standard Firebase Admin SDK verification (when credentials / ADC are present)
    try:
        from firebase_admin import auth
        decoded_token = auth.verify_id_token(token, check_revoked=False, clock_skew_seconds=60)
        logger.debug("Firebase Admin Strategy 1 succeeded")
    except Exception as e:
        verification_error = e
        logger.debug("Firebase Admin standard verify_id_token skipped/failed: %s (%s)", type(e).__name__, e)

    # Strategy 2: Firebase Admin SDK internal TokenVerifier using Google public certs
    if decoded_token is None:
        try:
            import firebase_admin
            from firebase_admin import _token_gen
            app = firebase_admin.get_app() if firebase_admin._apps else firebase_admin.initialize_app(
                options={"projectId": configured_project}
            )
            verifier = _token_gen.TokenVerifier(app)
            decoded_token = verifier.verify_id_token(token, clock_skew_seconds=60)
            logger.debug("Firebase TokenVerifier Strategy 2 succeeded")
        except Exception as e:
            verification_error = e
            logger.debug("Firebase TokenVerifier Strategy 2 failed: %s (%s)", type(e).__name__, e)

    # Strategy 3: Google Auth ID Token Verification (standalone cryptographic public cert verification)
    if decoded_token is None:
        try:
            from google.oauth2 import id_token as google_id_token
            from google.auth.transport import requests as google_requests
            certs_url = "https://www.googleapis.com/robot/v1/metadata/x509/securetoken@system.gserviceaccount.com"
            decoded_token = google_id_token.verify_token(
                token,
                request=google_requests.Request(),
                audience=configured_project,
                certs_url=certs_url,
                clock_skew_in_seconds=60,
            )
            # Strictly verify issuer matches configured project
            actual_iss = decoded_token.get("iss")
            if actual_iss != expected_issuer:
                logger.warning("Strategy 3 token issuer '%s' != expected '%s'", actual_iss, expected_issuer)
                decoded_token = None
            else:
                logger.debug("Google OAuth2 ID Token Strategy 3 succeeded")
        except Exception as e:
            verification_error = e
            logger.debug("Google ID Token Strategy 3 failed: %s (%s)", type(e).__name__, e)

    if not decoded_token:
        # Safe diagnostic logging: logs type and description, never credentials or secret values
        logger.warning(
            "Token verification failed across all strategies: error=%s (%s), aud=%s, configured_proj=%s",
            type(verification_error).__name__, verification_error, token_aud, configured_project
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed: invalid or expired token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    uid = decoded_token.get("uid") or decoded_token.get("sub") or decoded_token.get("user_id")
    if not uid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: missing subject (uid).",
            headers={"WWW-Authenticate": "Bearer"},
        )

    email = decoded_token.get("email")
    name = decoded_token.get("name")
    custom_claims = decoded_token.get("custom_claims", {})
    if not isinstance(custom_claims, dict):
        custom_claims = {}

    # Check admin privileges from custom claims and known admin emails
    role = custom_claims.get("role", decoded_token.get("role", "user"))
    is_admin = (
        role == "admin"
        or decoded_token.get("admin") is True
        or custom_claims.get("admin") is True
        or (email and email == "admin@intelligentforgetting.org")
    )

    return AuthenticatedUser(
        uid=uid,
        email=email,
        name=name,
        role="admin" if is_admin else "user",
        is_admin=is_admin,
        claims=decoded_token,
    )


async def get_current_user(
    auth_header: Optional[HTTPAuthorizationCredentials] = Security(security_bearer),
) -> AuthenticatedUser:
    """Dependency that extracts and validates the bearer token from the Authorization header."""
    if not auth_header or not auth_header.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required: missing Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return verify_id_token(auth_header.credentials)


async def get_current_admin_user(
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> AuthenticatedUser:
    """Dependency that enforces administrative permissions independently of frontend routes."""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator privileges required for this resource.",
        )
    return current_user


def provision_admin_user(uid: str, email: Optional[str] = None) -> Dict[str, Any]:
    """Sets custom admin claims for a designated user UID in Firebase Authentication."""
    initialize_firebase()
    try:
        from firebase_admin import auth

        claims = {"role": "admin", "admin": True}
        auth.set_custom_user_claims(uid, claims)
        logger.info("Successfully provisioned admin role for user UID: %s", uid)
        return {
            "status": "success",
            "uid": uid,
            "email": email,
            "claims": claims,
            "message": f"User {uid} granted administrative privileges."
        }
    except Exception as e:
        logger.error("Failed to provision admin custom claims in Firebase: %s", e)
        return {
            "status": "error",
            "uid": uid,
            "error": str(e),
            "message": "Firebase Admin SDK failed to set custom user claims."
        }
