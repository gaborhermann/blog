from airflow import DAG
from airflow.utils import timezone
from airflow.operators.dummy_operator import DummyOperator

dag = DAG(
    dag_id="dummy",
    schedule_interval=None,
    catchup=False,
    default_args=dict(start_date=timezone.datetime(2022, 1, 1)),
)

DummyOperator(task_id="dummy", dag=dag)
