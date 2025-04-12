import pandas as pd
import numpy as np
from datetime import datetime
import os
import time

def generate_data(n_rows, start_id):
    data = {
        "customer_id": [str(start_id + i) for i in range(n_rows)],
        "age": np.random.randint(18, 70, n_rows),
        "gender": np.random.choice(["Male", "Female"], n_rows),
        "tenure": np.random.randint(1, 36, n_rows),
        "usage_frequency": np.random.randint(1, 10, n_rows),
        "support_calls": np.random.randint(0, 10, n_rows),
        "payment_delay": np.random.randint(0, 30, n_rows),
        "subscription_type": np.random.choice(["Basic", "Standard", "Premium"], n_rows),
        "contract_length": np.random.choice(["Monthly", "Quarterly", "Annual"], n_rows),
        "total_spend": np.random.uniform(50, 1000, n_rows).round(2),
        "last_interaction": np.random.randint(1, 30, n_rows),
        "churn": np.random.randint(0, 2, n_rows),
        "customer_feedback": ["Generated feedback " + str(i) for i in range(n_rows)]
    }
    return pd.DataFrame(data)

os.makedirs("churn_data", exist_ok=True)
start_id = 1
while True:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"churn_data_{timestamp}.csv"
    local_path = f"churn_data/{filename}"
    hdfs_path = f"hdfs://localhost:9000/user/churn_data/{filename}"

    df = generate_data(n_rows=1000, start_id=start_id)  # Smaller batches for flow
    df.to_csv(local_path, index=False)
    os.system(f"hdfs dfs -put {local_path} {hdfs_path}")
    print(f"Uploaded {filename} to HDFS at {hdfs_path}")
    
    start_id += 1000  # Increment to avoid duplicates
    time.sleep(15)    # Simulate new files every 15s