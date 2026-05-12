from secrets import compare_digest


def verify_legacy_password(
    submitted_password: str,
    stored_credential: str,
) -> bool:
    return compare_digest(submitted_password, stored_credential)
