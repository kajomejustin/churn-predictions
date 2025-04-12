from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

class ChurnPrediction(models.Model):
    customer_id = models.CharField(max_length=50, primary_key=True)
    age = models.IntegerField()
    gender = models.CharField(max_length=10)
    tenure = models.IntegerField()
    usage_frequency = models.IntegerField()
    support_calls = models.IntegerField()
    payment_delay = models.IntegerField()
    subscription_type = models.CharField(max_length=50)
    contract_length = models.CharField(max_length=50)
    total_spend = models.FloatField()
    last_interaction = models.IntegerField()
    churn_prediction = models.IntegerField()
    prediction_time = models.DateTimeField()
    customer_feedback = models.TextField()
    
    class Meta:
        db_table = 'dashboard_churnprediction'