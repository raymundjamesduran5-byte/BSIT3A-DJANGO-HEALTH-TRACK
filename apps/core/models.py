from django.db import models

from apps.users.models import HealthTrackUser


class DailyRecommendation(models.Model):
    user = models.ForeignKey(
        HealthTrackUser,
        on_delete=models.CASCADE,
        related_name='daily_recommendations',
    )
    recommendation_date = models.DateField()
    items = models.JSONField()
    recorded_summary = models.JSONField(default=list)
    missing_data = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'daily_health_recommendations'
        constraints = [
            models.UniqueConstraint(
                fields=('user', 'recommendation_date'),
                name='unique_daily_recommendation_per_user',
            ),
        ]
        ordering = ['-recommendation_date']
