"""Defines account-scoped health tracking records."""

from datetime import datetime, timedelta

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from apps.users.models import HealthTrackUser


class Info(models.Model):
    name = models.CharField(max_length=255)
    age = models.PositiveIntegerField(validators=[MinValueValidator(1), MaxValueValidator(150)])
    address = models.CharField(max_length=255)
    email = models.EmailField(max_length=255, blank=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='infos',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'tblinfo'
        ordering = ['name']

    def __str__(self):
        return self.name


class HealthProfile(models.Model):
    id = models.AutoField(primary_key=True, db_column='health_profile_id')
    user = models.ForeignKey(HealthTrackUser, on_delete=models.CASCADE, related_name='health_profiles', db_column='user_id')
    height_cm = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)])
    weight_kg = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)])
    blood_type = models.CharField(max_length=5, blank=True)
    allergies = models.TextField(blank=True)
    existing_conditions = models.TextField(blank=True)
    emergency_contact_name = models.CharField(max_length=100, blank=True)
    emergency_contact_number = models.CharField(max_length=20, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'health_profiles'
        ordering = ['-updated_at']

    def __str__(self):
        return f'{self.user.email} health profile'


class HealthActivity(models.Model):
    class Mood(models.TextChoices):
        EXCELLENT = 'Excellent', 'Excellent'
        GOOD = 'Good', 'Good'
        NEUTRAL = 'Neutral', 'Neutral'
        POOR = 'Poor', 'Poor'
        VERY_POOR = 'Very Poor', 'Very Poor'

    class Stress(models.TextChoices):
        LOW = 'Low', 'Low'
        MODERATE = 'Moderate', 'Moderate'
        HIGH = 'High', 'High'
        VERY_HIGH = 'Very High', 'Very high'

    id = models.AutoField(primary_key=True, db_column='activity_id')
    user = models.ForeignKey(HealthTrackUser, on_delete=models.CASCADE, related_name='health_activities', db_column='user_id')
    activity_date = models.DateField()
    steps = models.PositiveIntegerField(default=0)
    calories_burned = models.DecimalField(max_digits=7, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    mood = models.CharField(max_length=10, choices=Mood.choices, blank=True)
    stress_level = models.CharField(max_length=10, choices=Stress.choices, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        db_table = 'health_activities'
        ordering = ['-activity_date', '-pk']


class Exercise(models.Model):
    class Intensity(models.TextChoices):
        LOW = 'Low', 'Low'
        MODERATE = 'Moderate', 'Moderate'
        HIGH = 'High', 'High'

    id = models.AutoField(primary_key=True, db_column='exercise_id')
    user = models.ForeignKey(HealthTrackUser, on_delete=models.CASCADE, related_name='exercises', db_column='user_id')
    exercise_date = models.DateField()
    exercise_type = models.CharField(max_length=100)
    duration_minutes = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    calories_burned = models.DecimalField(max_digits=7, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    intensity = models.CharField(max_length=10, choices=Intensity.choices, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        db_table = 'exercises'
        ordering = ['-exercise_date', '-pk']


class SleepRecord(models.Model):
    class Quality(models.TextChoices):
        POOR = 'Poor', 'Poor'
        FAIR = 'Fair', 'Fair'
        GOOD = 'Good', 'Good'
        EXCELLENT = 'Excellent', 'Excellent'

    id = models.AutoField(primary_key=True, db_column='sleep_id')
    user = models.ForeignKey(HealthTrackUser, on_delete=models.CASCADE, related_name='sleep_records', db_column='user_id')
    sleep_date = models.DateField()
    bedtime = models.TimeField()
    wake_time = models.TimeField()
    total_hours = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)])
    sleep_quality = models.CharField(max_length=10, choices=Quality.choices, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        db_table = 'sleep_records'
        ordering = ['-sleep_date', '-pk']

    def save(self, *args, **kwargs):
        start = datetime.combine(self.sleep_date, self.bedtime)
        end = datetime.combine(self.sleep_date, self.wake_time)
        if end <= start:
            end += timedelta(days=1)
        self.total_hours = round((end - start).total_seconds() / 3600, 2)
        super().save(*args, **kwargs)


class WaterIntake(models.Model):
    id = models.AutoField(primary_key=True, db_column='water_id')
    user = models.ForeignKey(HealthTrackUser, on_delete=models.CASCADE, related_name='water_intakes', db_column='user_id')
    intake_date = models.DateField()
    amount_ml = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    intake_time = models.TimeField(null=True, blank=True)

    class Meta:
        db_table = 'water_intake'
        ordering = ['-intake_date', '-intake_time', '-pk']


class Meal(models.Model):
    class MealType(models.TextChoices):
        BREAKFAST = 'Breakfast', 'Breakfast'
        LUNCH = 'Lunch', 'Lunch'
        DINNER = 'Dinner', 'Dinner'
        SNACK = 'Snack', 'Snack'

    id = models.AutoField(primary_key=True, db_column='meal_id')
    user = models.ForeignKey(HealthTrackUser, on_delete=models.CASCADE, related_name='meals', db_column='user_id')
    meal_date = models.DateField()
    meal_type = models.CharField(max_length=10, choices=MealType.choices)
    meal_description = models.CharField(max_length=255, blank=True)
    calories = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)])
    notes = models.TextField(blank=True)

    class Meta:
        db_table = 'meals'
        ordering = ['-meal_date', '-pk']


class HealthGoal(models.Model):
    class Status(models.TextChoices):
        NOT_STARTED = 'Not Started', 'Not started'
        IN_PROGRESS = 'In Progress', 'In progress'
        COMPLETED = 'Completed', 'Completed'
        CANCELLED = 'Cancelled', 'Cancelled'

    id = models.AutoField(primary_key=True, db_column='goal_id')
    user = models.ForeignKey(HealthTrackUser, on_delete=models.CASCADE, related_name='health_goals', db_column='user_id')
    goal_name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    target_value = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)])
    current_value = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    unit = models.CharField(max_length=30, blank=True)
    start_date = models.DateField(null=True, blank=True)
    target_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.NOT_STARTED)

    class Meta:
        db_table = 'health_goals'
        ordering = ['target_date', 'goal_name']


class HealthMeasurement(models.Model):
    id = models.AutoField(primary_key=True, db_column='measurement_id')
    user = models.ForeignKey(HealthTrackUser, on_delete=models.CASCADE, related_name='health_measurements', db_column='user_id')
    measurement_date = models.DateTimeField()
    systolic_bp = models.PositiveIntegerField(null=True, blank=True)
    diastolic_bp = models.PositiveIntegerField(null=True, blank=True)
    heart_rate = models.PositiveIntegerField(null=True, blank=True)
    temperature = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True, validators=[MinValueValidator(0)])
    blood_sugar = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)])
    weight_kg = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)])
    notes = models.TextField(blank=True)

    class Meta:
        db_table = 'health_measurements'
        ordering = ['-measurement_date', '-pk']


class HealthReminder(models.Model):
    class ReminderType(models.TextChoices):
        EXERCISE = 'Exercise', 'Exercise'
        WATER = 'Water', 'Water'
        MEAL = 'Meal', 'Meal'
        SLEEP = 'Sleep', 'Sleep'
        MEDICATION = 'Medication', 'Medication'
        CHECKUP = 'Checkup', 'Checkup'
        OTHER = 'Other', 'Other'

    class Status(models.TextChoices):
        PENDING = 'Pending', 'Pending'
        COMPLETED = 'Completed', 'Completed'
        CANCELLED = 'Cancelled', 'Cancelled'

    id = models.AutoField(primary_key=True, db_column='reminder_id')
    user = models.ForeignKey(HealthTrackUser, on_delete=models.CASCADE, related_name='health_reminders', db_column='user_id')
    reminder_title = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    reminder_date = models.DateField()
    reminder_time = models.TimeField()
    reminder_type = models.CharField(max_length=12, choices=ReminderType.choices, default=ReminderType.OTHER)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)

    class Meta:
        db_table = 'health_reminders'
        ordering = ['reminder_date', 'reminder_time']


class HealthReport(models.Model):
    class Period(models.TextChoices):
        DAILY = 'Daily', 'Daily'
        WEEKLY = 'Weekly', 'Weekly'
        MONTHLY = 'Monthly', 'Monthly'

    id = models.AutoField(primary_key=True, db_column='report_id')
    user = models.ForeignKey(HealthTrackUser, on_delete=models.CASCADE, related_name='health_reports', db_column='user_id')
    report_date = models.DateField()
    report_period = models.CharField(max_length=10, choices=Period.choices)
    summary = models.TextField(blank=True)
    recommendations = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'health_reports'
        ordering = ['-report_date', '-pk']
