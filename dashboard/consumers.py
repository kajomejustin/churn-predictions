# REMOVE this import entirely from top of consumers.py

from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
import json

class DashboardConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.group_name = "dashboard"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.send_initial_data()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def send_initial_data(self):
        predictions = await self.get_initial_predictions()
        data = [
            {
                "customer_id": pred.customer_id,
                "tenure": pred.tenure,
                "total_spend": float(pred.total_spend),
                "age": pred.age,
                "usage_frequency": pred.usage_frequency,
                "support_calls": pred.support_calls,
                "payment_delay": pred.payment_delay,
                "last_interaction": pred.last_interaction,
                "churn_prediction": pred.churn_prediction,
                "subscription_type": pred.subscription_type,
                "gender": pred.gender,
                "contract_length": pred.contract_length,
                "customer_feedback": pred.customer_feedback,
                "prediction_time": pred.prediction_time.strftime('%Y-%m-%d %H:%M:%S')
            }
            for pred in predictions
        ]
        await self.send(text_data=json.dumps({
            "type": "predictions",
            "data": data
        }))

    @database_sync_to_async
    def get_initial_predictions(self):
        from .models import ChurnPrediction  # ✅ Move model import HERE
        return list(ChurnPrediction.objects.order_by('-prediction_time')[:10])

    async def new_prediction(self, event):
        await self.send(text_data=json.dumps({
            "type": "new_prediction",
            "data": event["data"]
        }))
