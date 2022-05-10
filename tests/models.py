from django.contrib.auth.models import User
from django.db import models


class Project(models.Model):
    name = models.TextField()
    owner = models.ForeignKey(User, on_delete=models.PROTECT, related_name="projects")


class Expense(models.Model):
    amount = models.IntegerField()
    owner = models.ForeignKey(User, on_delete=models.PROTECT, related_name="expenses")
    project = models.ForeignKey(
        Project,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="expenses",
    )
