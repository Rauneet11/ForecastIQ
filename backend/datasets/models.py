from django.db import models
from accounts.models import User

class Dataset(models.Model):
    STATUS_CHOICES = [
        ('uploaded', 'Uploaded'),
        ('cleaning', 'Cleaning'),
        ('cleaned', 'Cleaned'),
        ('error', 'Error'),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='datasets')
    name = models.CharField(max_length=200)
    file = models.FileField(upload_to='datasets/')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='uploaded')
    rows = models.IntegerField(default=0)
    columns = models.IntegerField(default=0)
    cleaned_file = models.FileField(upload_to='cleaned_datasets/', null=True, blank=True)
    validation_report = models.JSONField(default=dict, blank=True)
    cleaning_report = models.JSONField(default=dict, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    cleaned_at = models.DateTimeField(null=True, blank=True)

    # Universal column-mapping support: lets the same pipeline work with
    # any CSV schema (Walmart, Rossmann, Supermarket Sales, custom, ...).
    detected_columns = models.JSONField(default=list, blank=True)
    suggested_mapping = models.JSONField(default=dict, blank=True)
    column_mapping = models.JSONField(default=dict, blank=True)
    MAPPING_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('mapped', 'Mapped'),
    ]
    mapping_status = models.CharField(max_length=20, choices=MAPPING_STATUS_CHOICES, default='pending')

    def __str__(self):
        return f'{self.name} ({self.user.username})'

    class Meta:
        ordering = ['-uploaded_at']
        indexes = [
            models.Index(fields=['user', '-uploaded_at']),
        ]
