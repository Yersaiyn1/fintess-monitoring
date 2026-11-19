"""Middleware module.

NOTE (Stage 1 Security Hardening):
The legacy `ContextSetterMiddleware` (which opened a separate DB session and ran
`SET LOCAL` from unauthenticated `x-user-id` / `x-doctor-id` headers before
closing the transaction) and the header-based `DoctorAccessLogMiddleware` have
been removed.

Authentication, ownership checks, and `Access_Log` auditing are now enforced
directly in `app/api/deps.py` (`get_current_user`, `get_current_doctor`,
`get_verified_doctor`) using verified Bearer JWT claims within the request's
database transaction.
"""
