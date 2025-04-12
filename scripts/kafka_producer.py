from kafka import KafkaProducer
import json
import subprocess
import time
import pandas as pd
from io import StringIO
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

producer = KafkaProducer(
    bootstrap_servers='localhost:9092',
    value_serializer=lambda v: json.dumps(v).encode('utf-8'),
    acks=1,  # Wait for leader ack only, faster
    batch_size=16384  # Default, tweak if needed
)

hdfs_dir = "hdfs://localhost:9000/user/churn_data/"
processed_files = set()

def get_hdfs_files():
    try:
        result = subprocess.run(["hdfs", "dfs", "-ls", hdfs_dir], capture_output=True, text=True, check=True)
        files = [line.split()[-1] for line in result.stdout.splitlines() if line.startswith("-") and line.endswith(".csv")]
        return files
    except subprocess.CalledProcessError as e:
        logger.error(f"HDFS ls failed: {e}")
        return []

while True:
    try:
        files = get_hdfs_files()
        logger.info(f"Found {len(files)} files in HDFS: {files}")
        
        new_files_found = False
        for file_path in files:
            if file_path not in processed_files and "customer_data.csv" not in file_path:
                logger.info(f"Detected new file: {file_path}")
                csv_content = subprocess.check_output(["hdfs", "dfs", "-cat", file_path], text=True)
                df = pd.read_csv(StringIO(csv_content))
                
                for _, row in df.iterrows():
                    message = row.to_dict()
                    producer.send('churn_topic', message)
                    logger.info(f"Sent from {file_path}: {message['customer_id']}")
                
                producer.flush()
                processed_files.add(file_path)
                new_files_found = True
                logger.info(f"Finished processing {file_path}")
        
        if not new_files_found:
            logger.info("No new files found, waiting...")
        
        time.sleep(10)
    
    except Exception as e:
        logger.error(f"Error in producer loop: {e}")
        time.sleep(10)

producer.flush()
logger.info("Producer shutting down")  # Moved outside loop