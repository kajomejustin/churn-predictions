from django.shortcuts import render
from django.http import JsonResponse
from .models import ChurnPrediction
from django.db.models import Count, Avg, Q
from django.core.exceptions import ValidationError
import logging
import json
from decimal import Decimal
from datetime import datetime, timedelta

# Custom JSON encoder for Decimal
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)

logger = logging.getLogger(__name__)

def dashboard(request):
    """Render the main dashboard template."""
    return render(request, 'dashboard.html', {})

def dashboard_data(request):
    """Provide data for dashboard charts and summary stats."""
    try:
        subscription_type = request.GET.get('subscription_type', '')
        age_range = request.GET.get('age_range', '')
        churn_prediction = request.GET.get('churn_prediction', '')
        timeframe = request.GET.get('timeframe', '30')

        logger.info(f"Dashboard data request: subscription_type={subscription_type}, age_range={age_range}, churn_prediction={churn_prediction}, timeframe={timeframe}")

        # Optimize queryset: exclude customer_feedback
        predictions = ChurnPrediction.objects.only(
            'tenure', 'total_spend', 'age', 'churn_prediction', 'subscription_type', 'prediction_time'
        )

        # Apply timeframe filter
        try:
            days = int(timeframe)
            cutoff_date = datetime.now() - timedelta(days=days)
            predictions = predictions.filter(prediction_time__gte=cutoff_date)
        except ValueError:
            logger.warning(f"Invalid timeframe value: {timeframe}. Defaulting to 30 days.")
            cutoff_date = datetime.now() - timedelta(days=30)
            predictions = predictions.filter(prediction_time__gte=cutoff_date)

        # Apply filters
        if subscription_type:
            predictions = predictions.filter(subscription_type=subscription_type)
        if age_range:
            try:
                if age_range == '18-30':
                    predictions = predictions.filter(age__gte=18, age__lte=30)
                elif age_range == '31-50':
                    predictions = predictions.filter(age__gte=31, age__lte=50)
                elif age_range == '51+':
                    predictions = predictions.filter(age__gte=51)
            except ValidationError as e:
                logger.error(f"Age range filter error: {e}")
        if churn_prediction:
            try:
                churn_value = int(churn_prediction)
                predictions = predictions.filter(churn_prediction=churn_value)
            except ValueError as e:
                logger.error(f"Churn prediction filter error: {e}")

        total_customers = predictions.count()
        if total_customers == 0:
            return JsonResponse({
                'summary_stats': {'total_customers': 0, 'churn_rate': 0, 'avg_spend': 0},
                'bar_chart_data': {'labels': ['Churn', 'No Churn'], 'data': [0, 0], 'backgroundColor': ['#FF6B6B', '#4ECDC4']},
                'pie_chart_data': {'labels': [], 'data': [], 'backgroundColor': []},
                'scatter_data': [],
                'line_chart_data': {'labels': [], 'data': []}
            })

        # Summary Statistics
        churn_count = predictions.filter(churn_prediction=1).count()
        churn_rate = (churn_count / total_customers * 100) if total_customers > 0 else 0
        avg_spend = predictions.aggregate(Avg('total_spend'))['total_spend__avg'] or 0

        # Bar Chart: Churn Distribution
        bar_chart_data = {
            'labels': ['Churn', 'No Churn'],
            'data': [churn_count, total_customers - churn_count],
            'backgroundColor': ['#FF6B6B', '#4ECDC4']
        }

        # Pie Chart: Subscription Type Distribution
        subscription_counts = predictions.values('subscription_type').annotate(count=Count('subscription_type'))
        pie_labels = [item['subscription_type'] for item in subscription_counts]
        pie_data = [item['count'] for item in subscription_counts]
        color_map = {'Basic': '#FF6B6B', 'Standard': '#4ECDC4', 'Premium': '#FFD93D'}
        pie_colors = [color_map.get(sub, '#AAAAAA') for sub in pie_labels]
        pie_chart_data = {'labels': pie_labels, 'data': pie_data, 'backgroundColor': pie_colors}

        # Scatter Plot: Sample to 1000 records
        scatter_sample = predictions.order_by('-prediction_time')[:1000]  # Most recent records
        scatter_data = [
            {'tenure': pred.tenure, 'total_spend': float(pred.total_spend), 'churn': pred.churn_prediction}
            for pred in scatter_sample
        ]

        # Line Chart: Average Spend by Tenure
        tenure_buckets = [0, 10, 20, 30, 40, 50, 60]
        line_labels = [f"{b}-{b+10}" for b in tenure_buckets[:-1]]
        line_data = [
            float(predictions.filter(tenure__gte=start, tenure__lt=start+10).aggregate(Avg('total_spend'))['total_spend__avg'] or 0)
            for start in tenure_buckets[:-1]
        ]
        line_chart_data = {'labels': line_labels, 'data': line_data}

        response_data = {
            'summary_stats': {
                'total_customers': total_customers,
                'churn_rate': round(churn_rate, 2),
                'avg_spend': round(float(avg_spend), 2)
            },
            'bar_chart_data': bar_chart_data,
            'pie_chart_data': pie_chart_data,
            'scatter_data': scatter_data,
            'line_chart_data': line_chart_data
        }
        return JsonResponse(response_data, encoder=DecimalEncoder)

    except Exception as e:
        logger.error(f"Error in dashboard_data: {str(e)}", exc_info=True)
        return JsonResponse({'error': 'An error occurred', 'details': str(e)}, status=500)

def get_predictions(request):
    """Handle DataTables server-side processing."""
    try:
        draw = int(request.GET.get('draw', 1))
        start = int(request.GET.get('start', 0))
        length = min(int(request.GET.get('length', 10)), 50)  # Cap at 50 for performance
        search_value = request.GET.get('search[value]', '')
        order_column_idx = int(request.GET.get('order[0][column]', 0))
        order_dir = request.GET.get('order[0][dir]', 'asc')

        subscription_type = request.GET.get('subscription_type', '')
        age_range = request.GET.get('age_range', '')
        churn_prediction = request.GET.get('churn_prediction', '')

        logger.info(f"Get predictions: draw={draw}, start={start}, length={length}, search={search_value}")

        columns = [
            'customer_id', 'tenure', 'total_spend', 'age', 'usage_frequency',
            'support_calls', 'payment_delay', 'last_interaction', 'churn_prediction',
            'subscription_type', 'prediction_time'
        ]
        order_column = columns[min(order_column_idx, len(columns) - 1)]
        order_by = f"{'-' if order_dir == 'desc' else ''}{order_column}"

        # Optimize queryset
        predictions = ChurnPrediction.objects.only(*columns)

        # Apply filters
        if subscription_type:
            predictions = predictions.filter(subscription_type=subscription_type)
        if age_range:
            try:
                if age_range == '18-30':
                    predictions = predictions.filter(age__gte=18, age__lte=30)
                elif age_range == '31-50':
                    predictions = predictions.filter(age__gte=31, age__lte=50)
                elif age_range == '51+':
                    predictions = predictions.filter(age__gte=51)
            except ValidationError:
                pass
        if churn_prediction:
            try:
                churn_value = int(churn_prediction)
                predictions = predictions.filter(churn_prediction=churn_value)
            except ValueError:
                pass

        # Apply search
        if search_value:
            search_filter = (
                Q(customer_id__icontains=search_value) |
                Q(subscription_type__icontains=search_value)
            )
            predictions = predictions.filter(search_filter)

        total_records = ChurnPrediction.objects.count()
        filtered_records = predictions.count()

        # Paginate and sort
        predictions = predictions.order_by(order_by)[start:start + length]

        data = [
            {
                'customer_id': pred.customer_id,
                'tenure': pred.tenure,
                'total_spend': float(pred.total_spend),
                'age': pred.age,
                'usage_frequency': pred.usage_frequency,
                'support_calls': pred.support_calls,
                'payment_delay': pred.payment_delay,
                'last_interaction': pred.last_interaction,
                'churn_prediction': pred.churn_prediction,
                'subscription_type': pred.subscription_type,
                'prediction_time': pred.prediction_time.strftime('%Y-%m-%d %H:%M:%S')
            }
            for pred in predictions
        ]

        return JsonResponse({
            'draw': draw,
            'recordsTotal': total_records,
            'recordsFiltered': filtered_records,
            'data': data
        }, encoder=DecimalEncoder)

    except Exception as e:
        logger.error(f"Error in get_predictions: {str(e)}", exc_info=True)
        return JsonResponse({
            'error': 'An error occurred',
            'details': str(e),
            'draw': int(request.GET.get('draw', 1)),
            'recordsTotal': 0,
            'recordsFiltered': 0,
            'data': []
        }, status=500)