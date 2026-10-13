from .models import HealthTrackUser


def mirror_healthtrack_account(auth_user):
    email = auth_user.email.strip()
    if not email:
        return None

    account = HealthTrackUser.objects.filter(email__iexact=email).first()
    if account is None:
        return HealthTrackUser.objects.create(
            first_name=auth_user.first_name[:50],
            last_name=auth_user.last_name[:50],
            email=email,
            password=auth_user.password,
        )

    account.first_name = auth_user.first_name[:50]
    account.last_name = auth_user.last_name[:50]
    account.password = auth_user.password
    account.save(update_fields=['first_name', 'last_name', 'password'])
    return account