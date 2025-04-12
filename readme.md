# Churn Data Management

## Technologies Used

1. Django Framework
2. Apache Spark 3.5.5
3. Apache Hadoop 3.3.6
4. Amazon RDS MySQL Server 8.0.4 / Local can work as well
5. Kafka 3.9.0 and Zookeeper
6. Redis - realtime data streaming
7. Uvicorn - for running Django applications

## Start Hadoop and Spark

1. Start Zookeeper and Kafka.
2. `start-dfs.sh`
3. `start-yarn.sh`
4. `start-master.sh`
5. `start-worker.sh spark://localhost:9000`
6. Check if all these processes are running using `jps` in the terminal.
7. Ensure MySQL server is running using `sudo systemctl status`.

## Django Configuration

1. Create MySQL database called `churn_db`.
2. Run Django migrations: `python manage.py makemigrations` & `python manage.py migrate`.

## Create Directory in HDFS and Put in the Customer Data

```bash
hdfs dfs -rm -r /user/churn_data/*  # Remove any existing data files
hdfs dfs -mkdir -p /user/churn_data  # Create the HDFS directory where customer data will be saved
hdfs dfs -ls /user/churn_data/  # Check if there are data files in this directory
```

## Create and Run Kafka Topic That Will Be Used by Kafka Producer

```bash
$KAFKA_HOME/bin/kafka-topics.sh --list --bootstrap-server localhost:9092  # Check if there exist Kafka topics
$KAFKA_HOME/bin/kafka-topics.sh --delete --topic churn_topic --bootstrap-server localhost:9092  # Delete existing topics to avoid duplications
$KAFKA_HOME/bin/kafka-topics.sh --create --topic churn_topic --bootstrap-server localhost:9092 --partitions 1 --replication-factor 1  # Create new Kafka topic

$KAFKA_HOME/bin/kafka-console-consumer.sh --bootstrap-server localhost:9092 --topic churn_topic --from-beginning | head -n 10  # Read first 10 records in the Kafka topic
```

## Connection String to Amazon RDS MySQL

```bash
mysql -h churndb.ch00akqyaago.eu-north-1.rds.amazonaws.com -u admin -p
```

## Exporting Current Python Version to Spark

```bash
export PYSPARK_PYTHON=$(which python)
```

## Running the Project

1. Install the requirements file using `pip install -r requirements.txt`.
2. `python scripts/data_generator.py &`
3. `spark-submit scripts/kafka_producer.py &`
4. `spark-submit --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.2.0 scripts/spark_pipeline.py &`
5. `uvicorn churnpredictions.asgi:application`

By following the above guidelines, the project will work perfectly.

## Setting Up Hadoop, Spark, and Django with Uvicorn on Ubuntu

This guide outlines how to configure Hadoop, Spark, and a Django application (served by Uvicorn) to start automatically after Ubuntu boots. The setup assumes:

- Hadoop is installed at `/usr/local/hadoop`.
- Spark is installed at `/usr/local/spark`.
- Django project is at `/home/kajome/BDE/churnpredictions` with a virtual environment at `/home/kajome/BDE/churnpredictions/.venv`.
- All services run as user `kajome`.
- Spark worker connects to `spark://localhost:9000`.

## Preparatory Steps

Ensure the environment is ready with correct permissions and dependencies.

### Set Permissions

```bash
sudo chown -R kajome:kajome /home/kajome/BDE/churnpredictions
```

### Install Required Packages

Recreate Virtual Environment (if needed):

```bash
cd /home/kajome/BDE/churnpredictions
rm -rf .venv
python3 -m venv .venv
source .venv/bin/activate
pip install uvicorn django
# Add other dependencies, e.g., pip install -r requirements.txt
deactivate
```

### Verify Hadoop and Spark Paths

```bash
echo $HADOOP_HOME
echo $SPARK_HOME
```

## Systemd Service Configurations

Create systemd service files for Hadoop, Spark, and Django.

### Hadoop Service

`sudo nano /etc/systemd/system/hadoop-hdfs.service`

```bash
[Unit]
Description=Hadoop HDFS
After=network.target

[Service]
Type=oneshot
User=kajome
Environment=HADOOP_HOME=/usr/local/hadoop
ExecStart=/usr/local/hadoop/sbin/start-dfs.sh
RemainAfterExit=yes
Restart=on-failure
TimeoutStartSec=300

[Install]
WantedBy=multi-user.target
```

### Hadoop YARN Service

`sudo nano /etc/systemd/system/hadoop-yarn.service`

```bash
[Unit]
Description=Hadoop YARN
After=hadoop-hdfs.service

[Service]
Type=forking
User=kajome
Environment=HADOOP_HOME=/usr/local/hadoop
ExecStart=/usr/local/hadoop/sbin/start-yarn.sh
ExecStop=/usr/local/hadoop/sbin/stop-yarn.sh
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

### Spark Master Service

`sudo nano /etc/systemd/system/spark-master.service`

```bash
[Unit]
Description=Spark Master
After=network.target hadoop-yarn.service

[Service]
Type=forking
User=kajome
Environment=SPARK_HOME=/usr/local/spark
ExecStart=/usr/local/spark/sbin/start-master.sh
ExecStop=/usr/local/spark/sbin/stop-master.sh
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

### Spark Worker Service

`sudo nano /etc/systemd/system/spark-worker.service`

```bash
[Unit]
Description=Spark Worker
After=spark-master.service

[Service]
Type=forking
User=kajome
Environment=SPARK_HOME=/usr/local/spark
ExecStart=/usr/local/spark/sbin/start-worker.sh spark://localhost:9000
ExecStop=/usr/local/spark/sbin/stop-worker.sh
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

### Django Uvicorn Service

`sudo nano /etc/systemd/system/django-uvicorn.service`

```bash
[Unit]
Description=Django Churn Predictions served by Uvicorn
After=network.target hadoop-hdfs.service hadoop-yarn.service spark-master.service spark-worker.service

[Service]
User=kajome
Group=kajome
WorkingDirectory=/home/kajome/BDE/churnpredictions
Environment="PATH=/home/kajome/BDE/churnpredictions/.venv/bin:/usr/local/bin:/usr/bin:/bin"
Environment="PYTHONPATH=/home/kajome/BDE/churnpredictions"
ExecStart=/home/kajome/BDE/churnpredictions/.venv/bin/python -m uvicorn churnpredictions.asgi:application --host 0.0.0.0 --port 8000
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### Kafka Service

`sudo nano /etc/systemd/system/kafka.service`

```bash
[Unit]
Description=Apache Kafka Server
After=network.target zookeeper.service
Requires=zookeeper.service

[Service]
Type=forking
User=kajome
ExecStart=/usr/local/kafka/bin/kafka-server-start.sh -daemon /usr/local/kafka/config/server.properties
ExecStop=/usr/local/kafka/bin/kafka-server-stop.sh
Restart=on-failure
RestartSec=5
WorkingDirectory=/usr/local/kafka

[Install]
WantedBy=multi-user.target
```

### Zookeeper Service

`sudo nano /etc/systemd/system/zookeeper.service`

```bash
[Unit]
Description=Apache Zookeeper Server
After=network.target

[Service]
Type=forking
User=kajome
ExecStart=/usr/local/kafka/bin/zookeeper-server-start.sh -daemon /usr/local/kafka/config/zookeeper.properties
ExecStop=/usr/local/kafka/bin/zookeeper-server-stop.sh
Restart=on-failure
RestartSec=5
WorkingDirectory=/usr/local/kafka

[Install]
WantedBy=multi-user.target
```

### Redis Service

`sudo nano /etc/systemd/system/redis.service`

```bash
[Unit]
Description=Advanced key-value store
After=network.target
Documentation=http://redis.io/documentation, man:redis-server(1)

[Service]
Type=notify
ExecStart=/usr/bin/redis-server /etc/redis/redis.conf --supervised systemd --daemonize no
PIDFile=/run/redis/redis-server.pid
TimeoutStopSec=0
Restart=always
User=redis
Group=redis
RuntimeDirectory=redis
RuntimeDirectoryMode=2755

UMask=007
PrivateTmp=true
LimitNOFILE=65535
PrivateDevices=true
ProtectHome=true
ProtectSystem=strict
ReadWritePaths=-/var/lib/redis
ReadWritePaths=-/var/log/redis
ReadWritePaths=-/var/run/redis

[Install]
WantedBy=multi-user.target
Alias=redis.service
```

### Reload Systemd

```bash
sudo systemctl daemon-reload
```

### Enable Services to Start on Boot

```bash
sudo systemctl enable hadoop-hdfs.service
sudo systemctl enable hadoop-yarn.service
sudo systemctl enable spark-master.service
sudo systemctl enable spark-worker.service
sudo systemctl enable django-uvicorn.service
sudo systemctl enable kafka.service
sudo systemctl enable zookeeper.service
sudo systemctl enable redis.service
```

### Start Services

```bash
sudo systemctl start hadoop-hdfs.service
sudo systemctl start hadoop-yarn.service
sudo systemctl start spark-master.service
sudo systemctl start spark-worker.service
sudo systemctl start django-uvicorn.service
sudo systemctl start kafka.service
sudo systemctl start zookeeper.service
sudo systemctl start redis.service
```

### Check Status of Services

```bash
sudo systemctl status hadoop-hdfs.service
sudo systemctl status hadoop-yarn.service
sudo systemctl status spark-master.service
sudo systemctl status spark-worker.service
sudo systemctl status django-uvicorn.service
sudo systemctl status kafka.service
sudo systemctl status zookeeper.service
sudo systemctl status redis.service
```

### Check Logs

```bash
journalctl -u django-uvicorn.service
journalctl -u hadoop-hdfs.service
journalctl -u hadoop-yarn.service
journalctl -u spark-master.service
journalctl -u spark-worker.service
journalctl -u kafka.service
journalctl -u zookeeper.service
journalctl -u redis.service
```

### Access Django Application

Open a web browser and navigate to `http://localhost:8000` or `http://<your-server-ip>:8000` to access the Django application.

### Access Hadoop Web UI

Open a web browser and navigate to `http://localhost:9870` for the Hadoop NameNode UI and `http://localhost:8088` for the YARN ResourceManager UI.

### Access Spark Web UI

Open a web browser and navigate to `http://localhost:8080` for the Spark Master UI and `http://localhost:8081` for the Spark Worker UI.

### Access Kafka Web UI

Open a web browser and navigate to `http://localhost:9000` for the Kafka UI.

### Access Redis CLI

```bash
redis-cli
```

### Verify Processes

```bash
jps  # Check if Hadoop and Spark processes are running
```

Or:

```bash
ps aux | grep hadoop
ps aux | grep spark
ps aux | grep django
ps aux | grep kafka
ps aux | grep zookeeper
ps aux | grep redis
```
