from pyspark.sql import SparkSession
from pyspark.ml.feature import VectorAssembler, Imputer, StringIndexer, OneHotEncoder
from pyspark.ml.classification import RandomForestClassifier
from pyspark.ml.evaluation import BinaryClassificationEvaluator
from pyspark.ml import Pipeline
from pyspark.sql.types import StructType, StructField, StringType, IntegerType, FloatType
from pyspark.sql.functions import col, when, lit, from_json, current_timestamp
import mysql.connector
import logging
from datetime import datetime
import os
import time
import gc

# Initialize logging
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
os.makedirs("churn_data", exist_ok=True)
log_filename = f'churn_data/spark_pipeline_{timestamp}.log'

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(log_filename)
    ]
)
logger = logging.getLogger(__name__)

# Set Java options for more memory before creating the Spark session
os.environ['SPARK_SUBMIT_OPTS'] = '-Xmx16g -XX:+UseG1GC -XX:MaxGCPauseMillis=20'

# Initialize Spark Session with highly optimized settings
spark = SparkSession.builder \
    .appName("ChurnPredictionPipeline") \
    .config("spark.sql.shuffle.partitions", "12") \
    .config("spark.executor.memory", "12g") \
    .config("spark.driver.memory", "12g") \
    .config("spark.memory.offHeap.enabled", "true") \
    .config("spark.memory.offHeap.size", "6g") \
    .config("spark.pyspark.python", "python3") \
    .config("spark.pyspark.driver.python", "python3") \
    .config("spark.network.timeout", "800s") \
    .config("spark.sql.autoBroadcastJoinThreshold", "-1") \
    .config("spark.sql.files.maxPartitionBytes", "134217728") \
    .config("spark.default.parallelism", "16") \
    .config("spark.sql.execution.arrow.pyspark.enabled", "true") \
    .config("spark.executor.cores", "4") \
    .config("spark.driver.cores", "4") \
    .config("spark.memory.fraction", "0.8") \
    .config("spark.memory.storageFraction", "0.3") \
    .config("spark.serializer", "org.apache.spark.serializer.KryoSerializer") \
    .config("spark.kryoserializer.buffer.max", "1g") \
    .config("spark.rdd.compress", "true") \
    .config("spark.shuffle.compress", "true") \
    .config("spark.shuffle.spill.compress", "true") \
    .master("local[*]") \
    .getOrCreate()

spark.sparkContext.setLogLevel("WARN")

# Unified schema
schema = StructType([
    StructField("customer_id", StringType(), True),
    StructField("age", IntegerType(), True),
    StructField("gender", StringType(), True),
    StructField("tenure", IntegerType(), True),
    StructField("usage_frequency", IntegerType(), True),
    StructField("support_calls", IntegerType(), True),
    StructField("payment_delay", IntegerType(), True),
    StructField("subscription_type", StringType(), True),
    StructField("contract_length", StringType(), True),
    StructField("total_spend", FloatType(), True),
    StructField("last_interaction", IntegerType(), True),
    StructField("churn", IntegerType(), True),  # Nullable
    StructField("customer_feedback", StringType(), True)
])

# Cache for model to avoid recreating
model_cache = {
    "preprocessor": None,
    "model": None,
    "assembler": None,
    "feature_cols": None
}

def apply_business_rules(predictions_df):
    logger.info("Applying business rules to predictions")
    return predictions_df.withColumn(
        "final_prediction",
        when(
            (col("payment_delay") > 15) |
            (col("support_calls") > 5) |
            (col("usage_frequency") < 2) |
            (col("last_interaction") > 30),
            lit(1)
        ).when(
            (col("tenure") > 24) &
            (col("total_spend") > 500) &
            (col("last_interaction") < 7) &
            (col("payment_delay") == 0),
            lit(0)
        ).otherwise(col("prediction").cast("integer"))
    )

def preprocess_data(df):
    numerical_cols = ["tenure", "total_spend", "age", "usage_frequency", 
                      "support_calls", "payment_delay", "last_interaction"]
    categorical_cols = ["gender", "subscription_type", "contract_length"]
    
    # Check for and drop existing transformation columns to avoid conflicts
    existing_cols = df.columns
    for cat_col in categorical_cols:
        if f"{cat_col}_index" in existing_cols:
            df = df.drop(f"{cat_col}_index")
        if f"{cat_col}_encoded" in existing_cols:
            df = df.drop(f"{cat_col}_encoded")
    
    # Use higher default values for categorical features to reduce skew
    indexers = [StringIndexer(inputCol=col, outputCol=f"{col}_index", handleInvalid="keep") 
                for col in categorical_cols]
    
    # Limited features for faster processing
    encoders = [OneHotEncoder(inputCols=[f"{col}_index"], outputCols=[f"{col}_encoded"], dropLast=True) 
                for col in categorical_cols]
    
    # Apply median imputation to numerical columns
    imputer = Imputer(inputCols=numerical_cols, outputCols=numerical_cols, strategy="median")
    
    # Create and apply the pipeline
    pipeline = Pipeline(stages=indexers + encoders + [imputer])
    model = pipeline.fit(df)
    return model.transform(df), numerical_cols + [f"{col}_encoded" for col in categorical_cols], model

def train_model(data, feature_cols):
    logger.info("Training model...")
    # Create feature vector
    assembler = VectorAssembler(inputCols=feature_cols, outputCol="features", handleInvalid="keep")
    train_data = assembler.transform(data).filter(col("churn").isNotNull())
    
    if train_data.count() == 0:
        logger.warning("No labeled data, returning None")
        return None, assembler
    
    # Sample if dataset is very large to avoid memory issues - smaller sample than before
    if train_data.count() > 30000:
        sample_ratio = 30000 / train_data.count()
        logger.info(f"Training dataset is large, sampling {sample_ratio:.2%} for training")
        train_data = train_data.sample(False, sample_ratio, seed=42)
    
    # Split into training and testing
    train, test = train_data.randomSplit([0.8, 0.2], seed=42)
    
    # Use a simpler model for faster training
    model = RandomForestClassifier(
        labelCol="churn",
        featuresCol="features",
        numTrees=8,          # Fewer trees
        maxDepth=4,          # Lower depth
        maxBins=32,          # Fewer bins
        minInstancesPerNode=5, # Avoid overfitting
        seed=42
    ).fit(train)
    
    # Evaluate model
    evaluator = BinaryClassificationEvaluator(labelCol="churn")
    auc = evaluator.evaluate(model.transform(test))
    logger.info(f"Model AUC: {auc:.3f}")
    
    return model, assembler

def process_stream():
    logger.info("Starting Kafka stream processing...")
    
    # Read from Kafka with tight batch size limits and no timeouts
    df = spark \
        .readStream \
        .format("kafka") \
        .option("kafka.bootstrap.servers", "localhost:9092") \
        .option("subscribe", "churn_topic") \
        .option("startingOffsets", "earliest") \
        .option("failOnDataLoss", "false") \
        .option("maxOffsetsPerTrigger", 5000) \
        .option("minPartitions", 12) \
        .option("kafka.max.poll.records", "3000") \
        .option("fetchOffset.numRetries", "8") \
        .option("fetchOffset.retryIntervalMs", "100") \
        .load()
    
    # Parse the JSON data with a specific schema
    df = df.selectExpr("CAST(value AS STRING) as json") \
           .select(from_json(col("json"), schema).alias("data")) \
           .select("data.*")
    
    # Initialize model
    initial_df = None
    historical_path = "churn_data/raw_historical_parquet"
    if os.path.exists(historical_path):
        try:
            # Use the predefined schema when reading Parquet
            initial_df = spark.read.schema(schema).parquet(historical_path)
            logger.info(f"Successfully loaded historical data with {initial_df.count()} records")
        except Exception as e:
            logger.error(f"Failed to read historical Parquet file: {e}")
            initial_df = None
    
    if initial_df and initial_df.count() > 0:
        logger.info(f"Using existing historical data with {initial_df.count()} records")
        
        # If dataset is large, sample it for initial model
        if initial_df.count() > 30000:
            sample_ratio = 30000 / initial_df.count()
            logger.info(f"Historical dataset is large, sampling {sample_ratio:.2%} for initial model")
            initial_df_sample = initial_df.sample(False, sample_ratio, seed=42)
        else:
            initial_df_sample = initial_df
            
        preprocessed_df, feature_cols, preprocess_pipeline = preprocess_data(initial_df_sample)
        model, assembler = train_model(preprocessed_df, feature_cols)
        
        # Save to cache
        model_cache["preprocessor"] = preprocess_pipeline
        model_cache["model"] = model
        model_cache["assembler"] = assembler
        model_cache["feature_cols"] = feature_cols
        
        # Clear memory
        del preprocessed_df
        gc.collect()
    else:
        logger.info("No historical data, waiting for first batch...")
        first_batch = df.writeStream.outputMode("append").format("memory").queryName("temp").start()
        max_attempts = 6
        attempt = 0
        while attempt < max_attempts:
            time.sleep(10)
            initial_df = spark.sql("SELECT * FROM temp WHERE churn IS NOT NULL")
            if initial_df.count() > 0:
                logger.info(f"Found initial labeled data with {initial_df.count()} records, training model...")
                # Save raw data for future retraining
                initial_df.write.mode("overwrite").parquet(historical_path)
                # Process for initial model
                preprocessed_df, feature_cols, preprocess_pipeline = preprocess_data(initial_df)
                model, assembler = train_model(preprocessed_df, feature_cols)
                
                # Save to cache
                model_cache["preprocessor"] = preprocess_pipeline
                model_cache["model"] = model
                model_cache["assembler"] = assembler
                model_cache["feature_cols"] = feature_cols
                
                # Clear memory
                del preprocessed_df
                gc.collect()
                break
            attempt += 1
            logger.info(f"Attempt {attempt}/{max_attempts}: No labeled data yet...")
        else:
            logger.warning("No labeled data, using fallback model...")
            initial_df = spark.sql("SELECT * FROM temp").withColumn("churn", lit(0))
            if initial_df.count() > 0:
                # Save raw data for future retraining
                initial_df.write.mode("overwrite").parquet(historical_path)
                # Process for initial model
                preprocessed_df, feature_cols, preprocess_pipeline = preprocess_data(initial_df)
                model, assembler = train_model(preprocessed_df, feature_cols)
                
                # Save to cache
                model_cache["preprocessor"] = preprocess_pipeline
                model_cache["model"] = model
                model_cache["assembler"] = assembler
                model_cache["feature_cols"] = feature_cols
                
                # Clear memory
                del preprocessed_df
                gc.collect()
            else:
                logger.error("No data available at all, cannot initialize model")
                spark.stop()
                return
        first_batch.stop()
    
    # Rest of the function remains unchanged...

    # Highly optimized process batch function
    def process_batch(batch_df, batch_id):
        start_time = time.time()
        batch_count = batch_df.count()
        logger.info(f"Processing batch {batch_id} with {batch_count} records")
        
        if batch_count > 0:
            try:
                # Just get the count of records by type
                labeled_count = batch_df.filter(col("churn").isNotNull()).count()
                logger.info(f"Batch contains {labeled_count} labeled records and {batch_count - labeled_count} unlabeled records")
                
                # Only show a small sample - just 2 rows to reduce output size
                batch_df.limit(2).show()
                
                # Ultra small sample for huge batches
                if batch_count > 10000:
                    sample_fraction = min(3000 / batch_count, 1.0)
                    logger.info(f"Batch too large, sampling {sample_fraction:.2%} of records")
                    batch_df_processed = batch_df.sample(False, sample_fraction, seed=batch_id)  # Use batch_id as seed for variety
                else:
                    batch_df_processed = batch_df
                
                # Process the batch using cached models
                t1 = time.time()
                batch_processed = model_cache["preprocessor"].transform(batch_df_processed)
                t2 = time.time()
                logger.info(f"Preprocessing took {t2-t1:.2f} seconds")
                
                predictions = model_cache["model"].transform(model_cache["assembler"].transform(batch_processed))
                t3 = time.time()
                logger.info(f"Model prediction took {t3-t2:.2f} seconds")
                
                predictions = apply_business_rules(predictions)
                predictions = predictions.withColumn("prediction_time", current_timestamp())
                
                # Only show a very limited number of rows in console output - reduce to 10
                predictions.select("customer_id", "final_prediction", "prediction_time") \
                    .limit(10) \
                    .write.mode("append").format("console").save()
                
                # MySQL output - process in smaller chunks with optimized batch size
                # Only insert a subset of data to avoid overwhelming MySQL
                t4 = time.time()
                try:
                    # Use very limited sample size for MySQL - just 2000 records max
                    mysql_df = predictions.limit(2000)
                    
                    conn = mysql.connector.connect(
                        host="localhost",
                        user="root",
                        password="admin",
                        database="churn_db",
                        port=3306,
                        auth_plugin="mysql_native_password",
                        connection_timeout=60,  # Increase timeout
                        use_pure=True          # Use pure Python implementation
                    )
                    cursor = conn.cursor()
                    
                    # Optimize collection by limiting and using direct conversion
                    mysql_rows = mysql_df.collect()
                    
                    mysql_batch = [(row["customer_id"], row["tenure"], float(row["total_spend"]), 
                                   row["age"], row["usage_frequency"], row["support_calls"],
                                   row["payment_delay"], row["last_interaction"], 
                                   int(row["final_prediction"]), row["subscription_type"], 
                                   row["gender"], row["contract_length"], row["customer_feedback"], 
                                   row["prediction_time"].strftime('%Y-%m-%d %H:%M:%S'))
                                  for row in mysql_rows]
                    
                    query = """
                    INSERT INTO dashboard_churnprediction (
                        customer_id, tenure, total_spend, age, usage_frequency,
                        support_calls, payment_delay, last_interaction,
                        churn_prediction, subscription_type, gender, contract_length,
                        customer_feedback, prediction_time
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """
                    # Process in smaller batches for MySQL (500 records at a time)
                    batch_size = 500
                    for i in range(0, len(mysql_batch), batch_size):
                        batch_slice = mysql_batch[i:i + batch_size]
                        cursor.executemany(query, batch_slice)
                        conn.commit()
                    
                    logger.info(f"Total inserted: {len(mysql_batch)} records into MySQL")
                    cursor.close()
                    conn.close()
                except Exception as e:
                    logger.error(f"Failed to write to MySQL: {e}")
                    if 'conn' in locals() and conn:
                        try:
                            conn.rollback()
                        except:
                            pass
                t5 = time.time()
                logger.info(f"MySQL operations took {t5-t4:.2f} seconds")
                
                # Retrain model less frequently - only every 5th batch with labeled data
                if labeled_count > 100 and batch_id % 5 == 0:
                    t6 = time.time()
                    # Sample labeled data very aggressively
                    labeled_sample_size = min(3000, labeled_count)
                    sample_fraction = labeled_sample_size / labeled_count
                    logger.info(f"Sampling {sample_fraction:.2%} of labeled data for retraining")
                    labeled_data = batch_df.filter(col("churn").isNotNull()).sample(False, sample_fraction, seed=42)
                    
                    logger.info(f"Retraining model with {labeled_data.count()} labeled records")
                    try:
                        # Use very limited historical data
                        historical_df = spark.read.parquet("churn_data/raw_historical_parquet")
                        historical_size = min(20000, historical_df.count())
                        historical_sample = historical_df.sample(False, historical_size/historical_df.count(), seed=42)
                        
                        # Save just the newly labeled data
                        labeled_data.write.mode("append").parquet("churn_data/raw_historical_parquet")
                        
                        # Combine samples (limited size)
                        combined_df = historical_sample.union(labeled_data)
                        combined_count = combined_df.count()
                        logger.info(f"Combined dataset for retraining: {combined_count} records")
                        
                        # Process combined data 
                        new_preprocessed_df, new_feature_cols, new_preprocess_pipeline = preprocess_data(combined_df)
                        new_model, new_assembler = train_model(new_preprocessed_df, new_feature_cols)
                        
                        if new_model:
                            # Update cache
                            model_cache["preprocessor"] = new_preprocess_pipeline
                            model_cache["model"] = new_model
                            model_cache["assembler"] = new_assembler
                            model_cache["feature_cols"] = new_feature_cols
                            logger.info("Model updated with new data")
                            
                        # Clear memory
                        del new_preprocessed_df, combined_df, historical_sample, labeled_data
                        gc.collect()
                    except Exception as e:
                        logger.error(f"Failed to retrain model: {e}")
                    t7 = time.time()
                    logger.info(f"Retraining took {t7-t6:.2f} seconds")
                
                # Clear memory explicitly
                del batch_processed, predictions
                if 'mysql_df' in locals():
                    del mysql_df
                if 'mysql_rows' in locals():
                    del mysql_rows
                if 'mysql_batch' in locals():
                    del mysql_batch
                gc.collect()
                
                end_time = time.time()
                total_time = end_time - start_time
                logger.info(f"Batch {batch_id} completed in {total_time:.2f} seconds")
            except Exception as e:
                logger.error(f"Error processing batch {batch_id}: {e}")
                logger.exception("Detailed stack trace")
        else:
            logger.info("Empty batch, skipping processing")

    # Setup very small microbatch processing
    query = df \
        .writeStream \
        .foreachBatch(process_batch) \
        .outputMode("append") \
        .trigger(processingTime="3 seconds") \
        .option("checkpointLocation", "churn_data/checkpoint/stream") \
        .start()
    
    query.awaitTermination()

if __name__ == "__main__":
    try:
        # Set more aggressive GC
        os.environ['PYSPARK_SUBMIT_ARGS'] = '--conf spark.executor.extraJavaOptions="-XX:+UseG1GC -XX:MaxGCPauseMillis=20" --conf spark.driver.extraJavaOptions="-XX:+UseG1GC -XX:MaxGCPauseMillis=20" pyspark-shell'
        
        # Run the stream processor
        process_stream()
    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        logger.exception("Detailed stack trace")
    finally:
        spark.stop()
        logger.info("Pipeline completed")
        
# this is working very perfectly and ready for production
# and it is a very optimized code