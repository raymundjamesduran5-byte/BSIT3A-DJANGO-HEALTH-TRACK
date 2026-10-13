from django.db import models


class HealthTrackUser(models.Model):
	GENDER_CHOICES = (
		('Male', 'Male'),
		('Female', 'Female'),
		('Other', 'Other'),
	)

	user_id = models.AutoField(primary_key=True)
	first_name = models.CharField(max_length=50)
	last_name = models.CharField(max_length=50)
	email = models.EmailField(max_length=100, unique=True)
	password = models.CharField(max_length=255)
	date_of_birth = models.DateField(null=True, blank=True)
	gender = models.CharField(max_length=6, choices=GENDER_CHOICES, null=True, blank=True)
	contact_number = models.CharField(max_length=20, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		db_table = 'users'

	def __str__(self):
		return self.email
