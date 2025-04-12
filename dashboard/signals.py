from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import ChurnPrediction
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

@receiver(post_save, sender=ChurnPrediction)
def broadcast_new_prediction(sender, instance, created, **kwargs):
    if created:
        channel_layer = get_channel_layer()
        data = {
            "customer_id": instance.customer_id,
            "tenure": instance.tenure,
            "total_spend": float(instance.total_spend),
            "age": instance.age,
            "usage_frequency": instance.usage_frequency,
            "support_calls": instance.support_calls,
            "payment_delay": instance.payment_delay,
            "last_interaction": instance.last_interaction,
            "churn_prediction": instance.churn_prediction,
            "subscription_type": instance.subscription_type,
            "gender": instance.gender,
            "contract_length": instance.contract_length,
            "customer_feedback": instance.customer_feedback,
            "prediction_time": instance.prediction_time.strftime('%Y-%m-%d %H:%M:%S')
        }
        async_to_sync(channel_layer.group_send)(
            "dashboard",
            {
                "type": "new_prediction",
                "data": data
            }
        )
