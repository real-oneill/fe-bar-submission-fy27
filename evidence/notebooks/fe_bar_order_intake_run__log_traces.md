# [dev <deployer>] fe_bar_order_intake_run / log_traces (run 366501624352316, as executed, with outputs)

Notebook `af7b3db6-697f-48f8-8099-05220e9f7395`, exported 2026-11-23 19:28 UTC from https://fevm-evan-aws-01.cloud.databricks.com via the Jobs export-run API.

## Quality 05 — Log one MLflow trace per extracted document
Writes each newly extracted document to the quality experiment as a trace (root span = the document and its
extracted orders; child span = the `ai_query` call), attaches the deterministic extraction checks as **CODE**
feedback, records the trace in `quality_trace_index` (so a document is traced once per prompt version), and
stamps `trace_id` onto `review_orders` so the Review App can log reviewer feedback to the right trace.

Traces are stored in Unity Catalog (`<catalog>.<schema>`), which requires a SQL warehouse for reads/writes.
Also grants the app's service principal what it needs to log feedback (experiment edit + trace tables).

```python
%pip install "mlflow[databricks]>=3.16"
```

**Output:**

```
Looking in indexes: [REDACTED]
Collecting mlflow>=3.16 (from mlflow[databricks]>=3.16)
  Downloading http://package-proxy.host.local:8184/pypi/v1/packages/mlflow/3.18.0/mlflow-3.18.0-py3-none-any.whl.metadata (50 kB)
Collecting mlflow-skinny==3.18.0 (from mlflow>=3.16->mlflow[databricks]>=3.16)
  Downloading http://package-proxy.host.local:8184/pypi/v1/packages/mlflow-skinny/3.18.0/mlflow_skinny-3.18.0-py3-none-any.whl.metadata (51 kB)
Collecting mlflow-tracing==3.18.0 (from mlflow>=3.16->mlflow[databricks]>=3.16)
  Downloading http://package-proxy.host.local:8184/pypi/v1/packages/mlflow-tracing/3.18.0/mlflow_tracing-3.18.0-py3-none-any.whl.metadata (19 kB)
Collecting Flask-CORS=3.16->mlflow[databricks]>=3.16)
  Downloading http://package-proxy.host.local:8184/pypi/v1/packages/flask-cors/6.0.5/flask_cors-6.0.5-py3-none-any.whl.metadata (5.4 kB)
Collecting Flask=3.16->mlflow[databricks]>=3.16)
  Downloading http://package-proxy.host.local:8184/pypi/v1/packages/flask/3.1.3/flask-3.1.3-py3-none-any.whl.metadata (3.2 kB)
Collecting aiohttp=3.7.0 (from mlflow>=3.16->mlflow[databricks]>=3.16)
  Downloading http://package-proxy.host.local:8184/pypi/v1/packages/aiohttp/3.14.5/aiohttp-3.14.5-cp312-cp312-manylinux2014_aarch64.manylinux_2_17_aarch64.manylinux_2_28_aarch64.whl.metadata (8.3 kB)
Collecting alembic!=1.10.0,=3.16->mlflow[databricks]>=3.16)
  Downloading http://package-proxy.host.local:8184/pypi/v1/packages/alembic/1.20.1/alembic-1.20.1-py3-none-any.whl.metadata (7.3 kB)
Requirement already satisfied: cryptography=43.0.0 in /databricks/python/lib/python3.12/site-packages (from mlflow>=3.16->mlflow[databricks]>=3.16) (46.0.3)
Collecting docker=4.0.0 (from mlflow>=3.16->mlflow[databricks]>=3.16)
  Downloading http://package-proxy.host.local:8184/pypi/v1/packages/docker/7.2.0/docker-7.2.0-py3-none-any.whl.metadata (3.8 kB)
Collecting graphene=3.16->mlflow[databricks]>=3.16)
  Downloading http://package-proxy.host.local:8184/pypi/v1/packages/graphene/3.4.3/graphene-3.4.3-py2.py3-none-any.whl.metadata (6.9 kB)
Collecting gunicorn=3.16->mlflow[databricks]>=3.16)
  Downloading http://package-proxy.host.local:8184/pypi/v1/packages/gunicorn/26.2.0/gunicorn-26.2.0-py3-none-any.whl.metadata (5.5 kB)
Collecting huey=2.5.4 (from mlflow>=3.16->mlflow[databricks]>=3.16)
  Downloading http://package-proxy.host.local:8184/pypi/v1/packages/huey/3.5.4/huey-3.5.4-py3-none-any.whl.metadata (5.7 kB)
Requirement already satisfied: matplotlib=3.16->mlflow[databricks]>=3.16) (3.10.6)
Requirement already satisfied: numpy=3.16->mlflow[databricks]>=3.16) (2.3.4)
Requirement already satisfied: pandas=3.16->mlflow[databricks]>=3.16) (2.3.3)
Requirement already satisfied: pyarrow=4.0.0 in /databricks/python/lib/python3.12/site-packages (from mlflow>=3.16->mlflow[databricks]>=3.16) (21.0.0)
Requirement already satisfied: scikit-learn=3.16->mlflow[databricks]>=3.16) (1.7.2)
Requirement already satisfied: scipy=3.16->mlflow[databricks]>=3.16) (1.16.3)
Collecting skops=3.16->mlflow[databricks]>=3.16)
  Downloading http://package-proxy.host.local:8184/pypi/v1/packages/skops/0.16.0/skops-0.16.0-py3-none-any.whl.metadata (4.3 kB)
Collecting sqlalchemy=1.4.0 (from mlflow>=3.16->mlflow[databricks]>=3.16)
  Downloading http://package-proxy.host.local:8184/pypi/v1/packages/sqlalchemy/2.1.9/sqlalchemy-2.1.9-cp312-cp312-manylinux2014_aarch64.manylinux_2_17_aarch64.manylinux_2_28_aarch64.whl.metadata (9.7 kB)
Requirement already satisfied: anyio!=4.15.0,=3.6.2 in /databricks/python/lib/python3.12/site-packages (from mlflow-skinny==3.18.0->mlflow>=3.16->mlflow[databricks]>=3.16) (4.10.0)
Requirement already satisfied: cachetools=5.0.0 in /databricks/python/lib/python3.12/site-packages (from mlflow-skinny==3.18.0->mlflow>=3.16->mlflow[databricks]>=3.16) (5.5.1)
Requirement already satisfied: click=7.0 in /databricks/python/lib/python3.12/site-packages (from mlflow-skinny==3.18.0->mlflow>=3.16->mlflow[databricks]>=3.16) (8.2.1)
Requirement already satisfied: cloudpicklemlflow>=3.16->mlflow[databricks]>=3.16) (3.1.1)
Requirement already satisfied: databricks-sdk=0.20.0 in /databricks/python/lib/python3.12/site-packages (from mlflow-skinny==3.18.0->mlflow>=3.16->mlflow[databricks]>=3.16) (0.122.0)
Requirement already satisfied: fastapimlflow>=3.16->mlflow[databricks]>=3.16) (0.136.3)
Requirement already satisfied: gitpython=3.1.9 in /databricks/python/lib/python3.12/site-packages (from mlflow-skinny==3.18.0->mlflow>=3.16->mlflow[databricks]>=3.16) (3.1.45)
Requirement already satisfied: importlib_metadata!=4.7.0,=3.7.0 in /databricks/python/lib/python3.12/site-packages (from mlflow-skinny==3.18.0->mlflow>=3.16->mlflow[databricks]>=3.16) (8.7.0)
Requirement already satisfied: opentelemetry-api=1.9.0 in /databricks/python/lib/python3.12/site-packages (from mlflow-skinny==3.18.0->mlflow>=3.16->mlflow[databricks]>=3.16) (1.42.1)
Requirement already satisfied: opentelemetry-proto=1.9.0 in /databricks/python/lib/python3.12/site-packages (from mlflow-skinny==3.18.0->mlflow>=3.16->mlflow[databricks]>=3.16) (1.42.1)
Requirement already satisfied: opentelemetry-sdk=1.9.0 in /databricks/python/lib/python3.12/site-packages (from mlflow-skinny==3.18.0->mlflow>=3.16->mlflow[databricks]>=3.16) (1.42.1)
Requirement already satisfied: packagingmlflow>=3.16->mlflow[databricks]>=3.16) (25.0)
Requirement already satisfied: protobuf=3.12.0 in /databricks/python/lib/python3.12/site-packages (from mlflow-skinny==3.18.0->mlflow>=3.16->mlflow[databricks]>=3.16) (6.33.5)
Requirement already satisfied: pydantic=2.0.0 in /databricks/python/lib/python3.12/site-packages (from mlflow-skinny==3.18.0->mlflow>=3.16->mlflow[databricks]>=3.16) (2.13.3)
Requirement already satisfied: python-dotenv=0.19.0 in /databricks/python/lib/python3.12/site-packages (from mlflow-skinny==3.18.0->mlflow>=3.16->mlflow[databricks]>=3.16) (1.2.2)
Collecting python-multipart=0.0.18 (from mlflow-skinny==3.18.0->mlflow>=3.16->mlflow[databricks]>=3.16)
  Downloading http://package-proxy.host.local:8184/pypi/v1/packages/python-multipart/0.0.34/python_multipart-0.0.34-py3-none-any.whl.metadata (6.3 kB)
Requirement already satisfied: pyyaml=5.1 in /databricks/python/lib/python3.12/site-packages (from mlflow-skinny==3.18.0->mlflow>=3.16->mlflow[databricks]>=3.16) (6.0.3)
Requirement already satisfied: requests=2.17.3 in /databricks/python/lib/python3.12/site-packages (from mlflow-skinny==3.18.0->mlflow>=3.16->mlflow[databricks]>=3.16) (2.32.5)
Requirement already satisfied: sqlparse=0.4.0 in /databricks/python/lib/python3.12/site-packages (from mlflow-skinny==3.18.0->mlflow>=3.16->mlflow[databricks]>=3.16) (0.5.5)
Requirement already satisfied: starlettemlflow>=3.16->mlflow[databricks]>=3.16) (0.52.1)
Requirement already satisfied: typing-extensions=4.0.0 in /databricks/python/lib/python3.12/site-packages (from mlflow-skinny==3.18.0->mlflow>=3.16->mlflow[databricks]>=3.16) (4.15.0)
Requirement already satisfied: uvicornmlflow>=3.16->mlflow[databricks]>=3.16) (0.48.0)
Collecting aiohappyeyeballs>=2.5.0 (from aiohttp=3.7.0->mlflow>=3.16->mlflow[databricks]>=3.16)
  Downloading http://package-proxy.host.local:8184/pypi/v1/packages/aiohappyeyeballs/2.7.1/aiohappyeyeballs-2.7.1-py3-none-any.whl.metadata (5.9 kB)
Collecting aiosignal>=1.4.0 (from aiohttp=3.7.0->mlflow>=3.16->mlflow[databricks]>=3.16)
  Downloading http://package-proxy.host.local:8184/pypi/v1/packages/aiosignal/1.4.0/aiosignal-1.4.0-py3-none-any.whl.metadata (3.7 kB)
Requirement already satisfied: attrs>=17.3.0 in /databricks/python/lib/python3.12/site-packages (from aiohttp=3.7.0->mlflow>=3.16->mlflow[databricks]>=3.16) (25.4.0)
Collecting frozenlist>=1.1.1 (from aiohttp=3.7.0->mlflow>=3.16->mlflow[databricks]>=3.16)
  Downloading http://package-proxy.host.local:8184/pypi/v1/packages/frozenlist/1.8.0/frozenlist-1.8.0-cp312-cp312-manylinux2014_aarch64.manylinux_2_17_aarch64.manylinux_2_28_aarch64.whl.metadata (20 kB)
Collecting multidict=4.5 (from aiohttp=3.7.0->mlflow>=3.16->mlflow[databricks]>=3.16)
  Downloading http://package-proxy.host.local:8184/pypi/v1/packages/multidict/7.2.1/multidict-7.2.1-cp312-cp312-manylinux2014_aarch64.manylinux_2_17_aarch64.manylinux_2_28_aarch64.whl.metadata (6.1 kB)
Collecting propcache>=0.2.0 (from aiohttp=3.7.0->mlflow>=3.16->mlflow[databricks]>=3.16)
  Downloading http://package-proxy.host.local:8184/pypi/v1/packages/propcache/0.5.4/propcache-0.5.4-cp312-cp312-manylinux2014_aarch64.manylinux_2_17_aarch64.manylinux_2_28_aarch64.whl.metadata (25 kB)
Collecting yarl=1.25.1 (from aiohttp=3.7.0->mlflow>=3.16->mlflow[databricks]>=3.16)
  Downloading http://package-proxy.host.local:8184/pypi/v1/packages/yarl/1.25.1/yarl-1.25.1-cp312-cp312-manylinux2014_aarch64.manylinux_2_17_aarch64.manylinux_2_28_aarch64.whl.metadata (111 kB)
Collecting Mako (from alembic!=1.10.0,mlflow>=3.16->mlflow[databricks]>=3.16)
  Downloading http://package-proxy.host.local:8184/pypi/v1/packages/mako/1.4.3/mako-1.4.3-py3-none-any.whl.metadata (2.9 kB)
Requirement already satisfied: idna>=2.8 in /databricks/python/lib/python3.12/site-packages (from anyio!=4.15.0,=3.6.2->mlflow-skinny==3.18.0->mlflow>=3.16->mlflow[databricks]>=3.16) (3.11)
Requirement already satisfied: sniffio>=1.1 in /databricks/python/lib/python3.12/site-packages (from anyio!=4.15.0,=3.6.2->mlflow-skinny==3.18.0->mlflow>=3.16->mlflow[databricks]>=3.16) (1.3.0)
Requirement already satisfied: cffi>=2.0.0 in /databricks/python/lib/python3.12/site-packages (from cryptography=43.0.0->mlflow>=3.16->mlflow[databricks]>=3.16) (2.0.0)
Requirement already satisfied: google-auth~=2.0 in /databricks/python/lib/python3.12/site-packages (from databricks-sdk=0.20.0->mlflow-skinny==3.18.0->mlflow>=3.16->mlflow[databricks]>=3.16) (2.53.0)
Requirement already satisfied: urllib3=1.26 in /databricks/python/lib/python3.12/site-packages (from databricks-sdk=0.20.0->mlflow-skinny==3.18.0->mlflow>=3.16->mlflow[databricks]>=3.16) (2.5.0)
Requirement already satisfied: typing-inspection>=0.4.2 in /databricks/python/lib/python3.12/site-packages (from fastapimlflow-skinny==3.18.0->mlflow>=3.16->mlflow[databricks]>=3.16) (0.4.2)
Requirement already satisfied: annotated-doc>=0.0.2 in /databricks/python/lib/python3.12/site-packages (from fastapimlflow-skinny==3.18.0->mlflow>=3.16->mlflow[databricks]>=3.16) (0.0.4)
Collecting blinker>=1.9.0 (from Flaskmlflow>=3.16->mlflow[databricks]>=3.16)
  Downloading http://package-proxy.host.local:8184/pypi/v1/packages/blinker/1.9.0/blinker-1.9.0-py3-none-any.whl.metadata (1.6 kB)
Collecting itsdangerous>=2.2.0 (from Flaskmlflow>=3.16->mlflow[databricks]>=3.16)
  Downloading http://package-proxy.host.local:8184/pypi/v1/packages/itsdangerous/2.2.0/itsdangerous-2.2.0-py3-none-any.whl.metadata (1.9 kB)
Requirement already satisfied: jinja2>=3.1.2 in /databricks/python/lib/python3.12/site-packages (from Flaskmlflow>=3.16->mlflow[databricks]>=3.16) (3.1.6)
Requirement already satisfied: markupsafe>=2.1.1 in /databricks/python/lib/python3.12/site-packages (from Flaskmlflow>=3.16->mlflow[databricks]>=3.16) (3.0.2)
Collecting werkzeug>=3.1.0 (from Flaskmlflow>=3.16->mlflow[databricks]>=3.16)
  Downloading http://package-proxy.host.local:8184/pypi/v1/packages/werkzeug/3.1.9/werkzeug-3.1.9-py3-none-any.whl.metadata (4.1 kB)
Requirement already satisfied: gitdb=4.0.1 in /databricks/python/lib/python3.12/site-packages (from gitpython=3.1.9->mlflow-skinny==3.18.0->mlflow>=3.16->mlflow[databricks]>=3.16) (4.0.11)
Requirement already satisfied: smmap=3.0.1 in /databricks/python/lib/python3.12/site-packages (from gitdb=4.0.1->gitpython=3.1.9->mlflow-skinny==3.18.0->mlflow>=3.16->mlflow[databricks]>=3.16) (5.0.0)
Requirement already satisfied: pyasn1-modules>=0.2.1 in /databricks/python/lib/python3.12/site-packages (from google-auth~=2.0->databricks-sdk=0.20.0->mlflow-skinny==3.18.0->mlflow>=3.16->mlflow[databricks]>=3.16) (0.4.2)
Collecting graphql-core=3.1 (from graphenemlflow>=3.16->mlflow[databricks]>=3.16)
  Downloading http://package-proxy.host.local:8184/pypi/v1/packages/graphql-core/3.2.14/graphql_core-3.2.14-py3-none-any.whl.metadata (11 kB)
Collecting graphql-relay=3.1 (from graphenemlflow>=3.16->mlflow[databricks]>=3.16)
  Downloading http://package-proxy.host.local:8184/pypi/v1/packages/graphql-relay/3.2.0/graphql_relay-3.2.0-py3-none-any.whl.metadata (12 kB)
Requirement already satisfied: python-dateutil=2.7.0 in /databricks/python/lib/python3.12/site-packages (from graphenemlflow>=3.16->mlflow[databricks]>=3.16) (2.9.0.post0)
Requirement already satisfied: zipp>=3.20 in /databricks/python/lib/python3.12/site-packages (from importlib_metadata!=4.7.0,=3.7.0->mlflow-skinny==3.18.0->mlflow>=3.16->mlflow[databricks]>=3.16) (3.23.0)
Requirement already satisfied: contourpy>=1.0.1 in /databricks/python/lib/python3.12/site-packages (from matplotlibmlflow>=3.16->mlflow[databricks]>=3.16) (1.3.3)
Requirement already satisfied: cycler>=0.10 in /databricks/python/lib/python3.12/site-packages (from matplotlibmlflow>=3.16->mlflow[databricks]>=3.16) (0.11.0)
Requirement already satisfied: fonttools>=4.22.0 in /databricks/python/lib/python3.12/site-packages (from matplotlibmlflow>=3.16->mlflow[databricks]>=3.16) (4.60.1)
Requirement already satisfied: kiwisolver>=1.3.1 in /databricks/python/lib/python3.12/site-packages (from matplotlibmlflow>=3.16->mlflow[databricks]>=3.16) (1.4.8)
Requirement already satisfied: pillow>=8 in /databricks/python/lib/python3.12/site-packages (from matplotlibmlflow>=3.16->mlflow[databricks]>=3.16) (12.0.0)
Requirement already satisfied: pyparsing>=2.3.1 in /databricks/python/lib/python3.12/site-packages (from matplotlibmlflow>=3.16->mlflow[databricks]>=3.16) (3.2.5)
Requirement already satisfied: opentelemetry-semantic-conventions==0.63b1 in /databricks/python/lib/python3.12/site-packages (from opentelemetry-sdk=1.9.0->mlflow-skinny==3.18.0->mlflow>=3.16->mlflow[databricks]>=3.16) (0.63b1)
Requirement already satisfied: pytz>=2020.1 in /databricks/python/lib/python3.12/site-packages (from pandasmlflow>=3.16->mlflow[databricks]>=3.16) (2026.5)
Requirement already satisfied: tzdata>=2022.7 in /databricks/python/lib/python3.12/site-packages (from pandasmlflow>=3.16->mlflow[databricks]>=3.16) (2026.5)
Requirement already satisfied: annotated-types>=0.6.0 in /databricks/python/lib/python3.12/site-packages (from pydantic=2.0.0->mlflow-skinny==3.18.0->mlflow>=3.16->mlflow[databricks]>=3.16) (0.7.0)
Requirement already satisfied: pydantic-core==2.46.3 in /databricks/python/lib/python3.12/site-packages (from pydantic=2.0.0->mlflow-skinny==3.18.0->mlflow>=3.16->mlflow[databricks]>=3.16) (2.46.3)
Requirement already satisfied: six>=1.5 in /databricks/python/lib/python3.12/site-packages (from python-dateutil=2.7.0->graphenemlflow>=3.16->mlflow[databricks]>=3.16) (1.17.0)
Requirement already satisfied: charset_normalizer=2 in /databricks/python/lib/python3.12/site-packages (from requests=2.17.3->mlflow-skinny==3.18.0->mlflow>=3.16->mlflow[databricks]>=3.16) (3.4.4)
Requirement already satisfied: certifi>=2017.4.17 in /databricks/python/lib/python3.12/site-packages (from requests=2.17.3->mlflow-skinny==3.18.0->mlflow>=3.16->mlflow[databricks]>=3.16) (2026.10.19)
Requirement already satisfied: joblib>=1.2.0 in /databricks/python/lib/python3.12/site-packages (from scikit-learnmlflow>=3.16->mlflow[databricks]>=3.16) (1.5.2)
Requirement already satisfied: threadpoolctl>=3.1.0 in /databricks/python/lib/python3.12/site-packages (from scikit-learnmlflow>=3.16->mlflow[databricks]>=3.16) (3.5.0)
Collecting prettytable>=3.9 (from skopsmlflow>=3.16->mlflow[databricks]>=3.16)
  Downloading http://package-proxy.host.local:8184/pypi/v1/packages/prettytable/3.19.0/prettytable-3.19.0-py3-none-any.whl.metadata (37 kB)
Requirement already satisfied: h11>=0.8 in /databricks/python/lib/python3.12/site-packages (from uvicornmlflow-skinny==3.18.0->mlflow>=3.16->mlflow[databricks]>=3.16) (0.16.0)
Requirement already satisfied: pycparser in /databricks/python/lib/python3.12/site-packages (from cffi>=2.0.0->cryptography=43.0.0->mlflow>=3.16->mlflow[databricks]>=3.16) (2.23)
Requirement already satisfied: azure-storage-file-datalake>12 in /databricks/python/lib/python3.12/site-packages (from mlflow[databricks]>=3.16) (12.24.0)
Requirement already satisfied: google-cloud-storage>=1.30.0 in /databricks/python/lib/python3.12/site-packages (from mlflow[databricks]>=3.16) (3.10.1)
Requirement already satisfied: boto3>1 in /databricks/python/lib/python3.12/site-packages (from mlflow[databricks]>=3.16) (1.40.46)
Requirement already satisfied: botocore in /databricks/python/lib/python3.12/site-packages (from mlflow[databricks]>=3.16) (1.40.46)
Requirement already satisfied: databricks-agents=1.2.0 in /databricks/python/lib/python3.12/site-packages (from mlflow[databricks]>=3.16) (1.11.0)
Requirement already satisfied: dataclasses-json=1.2.0->mlflow[databricks]>=3.16) (0.6.7)
Requirement already satisfied: googleapis-common-protos=1.2.0->mlflow[databricks]>=3.16) (1.71.0)
Requirement already satisfied: tenacity=8.5 in /databricks/python/lib/python3.12/site-packages (from databricks-agents=1.2.0->mlflow[databricks]>=3.16) (9.1.2)
Requirement already satisfied: tiktoken=0.8.0 in /databricks/python/lib/python3.12/site-packages (from databricks-agents=1.2.0->mlflow[databricks]>=3.16) (0.13.0)
Requirement already satisfied: tqdm=1.2.0->mlflow[databricks]>=3.16) (4.67.1)
Requirement already satisfied: whenever==0.7.3 in /databricks/python/lib/python3.12/site-packages (from databricks-agents=1.2.0->mlflow[databricks]>=3.16) (0.7.3)
Requirement already satisfied: jmespath=0.7.1 in /databricks/python/lib/python3.12/site-packages (from boto3>1->mlflow[databricks]>=3.16) (1.0.1)
Requirement already satisfied: s3transfer=0.14.0 in /databricks/python/lib/python3.12/site-packages (from boto3>1->mlflow[databricks]>=3.16) (0.14.0)
Requirement already satisfied: marshmallow=3.18.0 in /databricks/python/lib/python3.12/site-packages (from dataclasses-jsondatabricks-agents=1.2.0->mlflow[databricks]>=3.16) (3.26.2)
Requirement already satisfied: typing-inspect=0.4.0 in /databricks/python/lib/python3.12/site-packages (from dataclasses-jsondatabricks-agents=1.2.0->mlflow[databricks]>=3.16) (0.9.0)
Requirement already satisfied: regex in /databricks/python/lib/python3.12/site-packages (from tiktoken=0.8.0->databricks-agents=1.2.0->mlflow[databricks]>=3.16) (2025.9.1)
Requirement already satisfied: mypy-extensions>=0.3.0 in /databricks/python/lib/python3.12/site-packages (from typing-inspect=0.4.0->dataclasses-jsondatabricks-agents=1.2.0->mlflow[databricks]>=3.16) (1.0.0)
Requirement already satisfied: azure-core>=1.37.0 in /databricks/python/lib/python3.12/site-packages (from azure-storage-file-datalake>12->mlflow[databricks]>=3.16) (1.41.0)
Requirement already satisfied: azure-storage-blob>=12.29.0 in /databricks/python/lib/python3.12/site-packages (from azure-storage-file-datalake>12->mlflow[databricks]>=3.16) (12.29.0)
Requirement already satisfied: isodate>=0.6.1 in /databricks/python/lib/python3.12/site-packages (from azure-storage-file-datalake>12->mlflow[databricks]>=3.16) (0.7.2)
Requirement already satisfied: google-api-core=2.27.0 in /databricks/python/lib/python3.12/site-packages (from google-cloud-storage>=1.30.0->mlflow[databricks]>=3.16) (2.30.3)
Requirement already satisfied: google-cloud-core=2.4.2 in /databricks/python/lib/python3.12/site-packages (from google-cloud-storage>=1.30.0->mlflow[databricks]>=3.16) (2.6.0)
Requirement already satisfied: google-resumable-media=2.7.2 in /databricks/python/lib/python3.12/site-packages (from google-cloud-storage>=1.30.0->mlflow[databricks]>=3.16) (2.9.0)
Requirement already satisfied: google-crc32c=1.1.3 in /databricks/python/lib/python3.12/site-packages (from google-cloud-storage>=1.30.0->mlflow[databricks]>=3.16) (1.8.0)
Requirement already satisfied: proto-plus=1.22.3 in /databricks/python/lib/python3.12/site-packages (from google-api-core=2.27.0->google-cloud-storage>=1.30.0->mlflow[databricks]>=3.16) (1.28.0)
Collecting wcwidth>=0.3.5 (from prettytable>=3.9->skopsmlflow>=3.16->mlflow[databricks]>=3.16)
  Downloading http://package-proxy.host.local:8184/pypi/v1/packages/wcwidth/0.9.5/wcwidth-0.9.5-cp310-abi3-manylinux2014_aarch64.manylinux_2_17_aarch64.whl.metadata (26 kB)
Requirement already satisfied: pyasn1=0.6.1 in /databricks/python/lib/python3.12/site-packages (from pyasn1-modules>=0.2.1->google-auth~=2.0->databricks-sdk=0.20.0->mlflow-skinny==3.18.0->mlflow>=3.16->mlflow[databricks]>=3.16) (0.6.1)
Downloading http://package-proxy.host.local:8184/pypi/v1/packages/mlflow/3.18.0/mlflow-3.18.0-py3-none-any.whl (12.6 MB)
[?25l   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 0.0/12.6 MB ? eta -:--:--
[2K   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 12.6/12.6 MB 111.6 MB/s  0:00:00
[?25hDownloading http://package-proxy.host.local:8184/pypi/v1/packages/mlflow-skinny/3.18.0/mlflow_skinny-3.18.0-py3-none-any.whl (4.4 MB)
[?25l   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 0.0/4.4 MB ? eta -:--:--
[2K   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 4.4/4.4 MB 112.7 MB/s  0:00:00
[?25hDownloading http://package-proxy.host.local:8184/pypi/v1/packages/mlflow-tracing/3.18.0/mlflow_tracing-3.18.0-py3-none-any.whl (2.1 MB)
[?25l   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 0.0/2.1 MB ? eta -:--:--
[2K   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 2.1/2.1 MB 81.2 MB/s  0:00:00
[?25hDownloading http://package-proxy.host.local:8184/pypi/v1/packages/aiohttp/3.14.5/aiohttp-3.14.5-cp312-cp312-manylinux2014_aarch64.manylinux_2_17_aarch64.manylinux_2_28_aarch64.whl (1.9 MB)
[?25l   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 0.0/1.9 MB ? eta -:--:--
[2K   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 1.9/1.9 MB 83.3 MB/s  0:00:00
[?25hDownloading http://package-proxy.host.local:8184/pypi/v1/packages/alembic/1.20.1/alembic-1.20.1-py3-none-any.whl (270 kB)
Downloading http://package-proxy.host.local:8184/pypi/v1/packages/docker/7.2.0/docker-7.2.0-py3-none-any.whl (148 kB)
Downloading http://package-proxy.host.local:8184/pypi/v1/packages/flask/3.1.3/flask-3.1.3-py3-none-any.whl (103 kB)
Downloading http://package-proxy.host.local:8184/pypi/v1/packages/flask-cors/6.0.5/flask_cors-6.0.5-py3-none-any.whl (16 kB)
Downloading http://package-proxy.host.local:8184/pypi/v1/packages/graphene/3.4.3/graphene-3.4.3-py2.py3-none-any.whl (114 kB)
Downloading http://package-proxy.host.local:8184/pypi/v1/packages/graphql-core/3.2.14/graphql_core-3.2.14-py3-none-any.whl (279 kB)
Downloading http://package-proxy.host.local:8184/pypi/v1/packages/graphql-relay/3.2.0/graphql_relay-3.2.0-py3-none-any.whl (16 kB)
Downloading http://package-proxy.host.local:8184/pypi/v1/packages/gunicorn/26.2.0/gunicorn-26.2.0-py3-none-any.whl (228 kB)
Downloading http://package-proxy.host.local:8184/pypi/v1/packages/huey/3.5.4/huey-3.5.4-py3-none-any.whl (135 kB)
Downloading http://package-proxy.host.local:8184/pypi/v1/packages/multidict/7.2.1/multidict-7.2.1-cp312-cp312-manylinux2014_aarch64.manylinux_2_17_aarch64.manylinux_2_28_aarch64.whl (506 kB)
Downloading http://package-proxy.host.local:8184/pypi/v1/packages/python-multipart/0.0.34/python_multipart-0.0.34-py3-none-any.whl (32 kB)
Downloading http://package-proxy.host.local:8184/pypi/v1/packages/skops/0.16.0/skops-0.16.0-py3-none-any.whl (148 kB)
Downloading http://package-proxy.host.local:8184/pypi/v1/packages/sqlalchemy/2.1.9/sqlalchemy-2.1.9-cp312-cp312-manylinux2014_aarch64.manylinux_2_17_aarch64.manylinux_2_28_aarch64.whl (4.7 MB)
[?25l   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 0.0/4.7 MB ? eta -:--:--
[2K   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 4.7/4.7 MB 111.6 MB/s  0:00:00
[?25hDownloading http://package-proxy.host.local:8184/pypi/v1/packages/yarl/1.25.1/yarl-1.25.1-cp312-cp312-manylinux2014_aarch64.manylinux_2_17_aarch64.manylinux_2_28_aarch64.whl (115 kB)
Downloading http://package-proxy.host.local:8184/pypi/v1/packages/aiohappyeyeballs/2.7.1/aiohappyeyeballs-2.7.1-py3-none-any.whl (15 kB)
Downloading http://package-proxy.host.local:8184/pypi/v1/packages/aiosignal/1.4.0/aiosignal-1.4.0-py3-none-any.whl (7.5 kB)
Downloading http://package-proxy.host.local:8184/pypi/v1/packages/blinker/1.9.0/blinker-1.9.0-py3-none-any.whl (8.5 kB)
Downloading http://package-proxy.host.local:8184/pypi/v1/packages/frozenlist/1.8.0/frozenlist-1.8.0-cp312-cp312-manylinux2014_aarch64.manylinux_2_17_aarch64.manylinux_2_28_aarch64.whl (243 kB)
Downloading http://package-proxy.host.local:8184/pypi/v1/packages/itsdangerous/2.2.0/itsdangerous-2.2.0-py3-none-any.whl (16 kB)
Downloading http://package-proxy.host.local:8184/pypi/v1/packages/prettytable/3.19.0/prettytable-3.19.0-py3-none-any.whl (37 kB)
Downloading http://package-proxy.host.local:8184/pypi/v1/packages/propcache/0.5.4/propcache-0.5.4-cp312-cp312-manylinux2014_aarch64.manylinux_2_17_aarch64.manylinux_2_28_aarch64.whl (251 kB)
Downloading http://package-proxy.host.local:8184/pypi/v1/packages/wcwidth/0.9.5/wcwidth-0.9.5-cp310-abi3-manylinux2014_aarch64.manylinux_2_17_aarch64.whl (826 kB)
[?25l   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 0.0/826.6 kB ? eta -:--:--
[2K   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 826.6/826.6 kB 31.1 MB/s  0:00:00
[?25hDownloading http://package-proxy.host.local:8184/pypi/v1/packages/werkzeug/3.1.9/werkzeug-3.1.9-py3-none-any.whl (228 kB)
Downloading http://package-proxy.host.local:8184/pypi/v1/packages/mako/1.4.3/mako-1.4.3-py3-none-any.whl (80 kB)
Installing collected packages: huey, werkzeug, wcwidth, sqlalchemy, python-multipart, propcache, multidict, Mako, itsdangerous, gunicorn, graphql-core, frozenlist, blinker, aiohappyeyeballs, yarl, prettytable, graphql-relay, Flask, docker, alembic, aiosignal, skops, graphene, Flask-CORS, aiohttp, mlflow-tracing, mlflow-skinny, mlflow
[?25l
[2K   ━╺━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  1/28 [werkzeug]
[2K  Attempting uninstall: wcwidth
   ━╺━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  1/28 [werkzeug]
[2K    Found existing installation: wcwidth 0.2.13
   ━╺━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  1/28 [werkzeug]
[2K    Not uninstalling wcwidth at /databricks/python3/lib/python3.12/site-packages, outside environment /local_disk0/.ephemeral_nfs/envs/pythonEnv-43f455b8-3e61-44bc-a017-296f413bab3f
   ━╺━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  1/28 [werkzeug]
[2K    Can't uninstall 'wcwidth'. No files were found to uninstall.
   ━╺━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  1/28 [werkzeug]
[2K   ━━╸━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  2/28 [wcwidth]
[2K   ━━╸━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  2/28 [wcwidth]
[2K   ━━━━╺━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  3/28 [sqlalchemy]
[2K   ━━━━╺━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  3/28 [sqlalchemy]
[2K   ━━━━╺━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  3/28 [sqlalchemy]
[2K   ━━━━╺━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  3/28 [sqlalchemy]
[2K   ━━━━╺━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  3/28 [sqlalchemy]
[2K   ━━━━╺━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  3/28 [sqlalchemy]
[2K   ━━━━━━━╺━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  5/28 [propcache]
[2K   ━━━━━━━━━━━━╸━━━━━━━━━━━━━━━━━━━━━━━━━━━  9/28 [gunicorn]
[2K   ━━━━━━━━━━━━━━╺━━━━━━━━━━━━━━━━━━━━━━━━━ 10/28 [graphql-core]
[2K  Attempting uninstall: blinker
   ━━━━━━━━━━━━━━╺━━━━━━━━━━━━━━━━━━━━━━━━━ 10/28 [graphql-core]
[2K    Found existing installation: blinker 1.7.0
   ━━━━━━━━━━━━━━╺━━━━━━━━━━━━━━━━━━━━━━━━━ 10/28 [graphql-core]
[2K    Not uninstalling blinker at /usr/lib/python3/dist-packages, outside environment /local_disk0/.ephemeral_nfs/envs/pythonEnv-43f455b8-3e61-44bc-a017-296f413bab3f
   ━━━━━━━━━━━━━━╺━━━━━━━━━━━━━━━━━━━━━━━━━ 10/28 [graphql-core]
[2K    Can't uninstall 'blinker'. No files were found to uninstall.
   ━━━━━━━━━━━━━━╺━━━━━━━━━━━━━━━━━━━━━━━━━ 10/28 [graphql-core]
[2K   ━━━━━━━━━━━━━━━━━━━━╺━━━━━━━━━━━━━━━━━━━ 14/28 [yarl]
[2K   ━━━━━━━━━━━━━━━━━━━━━━━━━╸━━━━━━━━━━━━━━ 18/28 [docker]
[2K   ━━━━━━━━━━━━━━━━━━━━━━━━━━━╺━━━━━━━━━━━━ 19/28 [alembic]
[2K   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╺━━━━━━━━━ 21/28 [skops]
[2K   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╺━━━━━━━━ 22/28 [graphene]
[2K   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╺━━━━━ 24/28 [aiohttp]
[2K   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╸━━━━ 25/28 [mlflow-tracing]
[2K   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╸━━━━ 25/28 [mlflow-tracing]
[2K   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╸━━━━ 25/28 [mlflow-tracing]
[2K   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╸━━━━ 25/28 [mlflow-tracing]
[2K   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╸━━━━ 25/28 [mlflow-tracing]
[2K   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╸━━━━ 25/28 [mlflow-tracing]
[2K   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╸━━━━ 25/28 [mlflow-tracing]
[2K  Attempting uninstall: mlflow-skinny
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╸━━━━ 25/28 [mlflow-tracing]
[2K    Found existing installation: mlflow-skinny 3.12.0
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╸━━━━ 25/28 [mlflow-tracing]
[2K    Not uninstalling mlflow-skinny at /databricks/python3/lib/python3.12/site-packages, outside environment /local_disk0/.ephemeral_nfs/envs/pythonEnv-43f455b8-3e61-44bc-a017-296f413bab3f
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╸━━━━ 25/28 [mlflow-tracing]
[2K    Can't uninstall 'mlflow-skinny'. No files were found to uninstall.
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╸━━━━ 25/28 [mlflow-tracing]
[2K   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╺━━ 26/28 [mlflow-skinny]
[2K   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╺━━ 26/28 [mlflow-skinny]
[2K   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╺━━ 26/28 [mlflow-skinny]
[2K   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╺━━ 26/28 [mlflow-skinny]
[2K   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╺━━ 26/28 [mlflow-skinny]
[2K   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╺━━ 26/28 [mlflow-skinny]
[2K   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╺━━ 26/28 [mlflow-skinny]
[2K   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╺━━ 26/28 [mlflow-skinny]
[2K   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╺━━ 26/28 [mlflow-skinny]
[2K   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╺━━ 26/28 [mlflow-skinny]
[2K   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╺━━ 26/28 [mlflow-skinny]
[2K   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╺━━ 26/28 [mlflow-skinny]
[2K   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╺━━ 26/28 [mlflow-skinny]
[2K   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╺━━ 26/28 [mlflow-skinny]
[2K   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╸━ 27/28 [mlflow]
[2K   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╸━ 27/28 [mlflow]
[2K   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╸━ 27/28 [mlflow]
[2K   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╸━ 27/28 [mlflow]
[2K   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╸━ 27/28 [mlflow]
[2K   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╸━ 27/28 [mlflow]
[2K   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╸━ 27/28 [mlflow]
[2K   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╸━ 27/28 [mlflow]
[2K   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╸━ 27/28 [mlflow]
[2K   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╸━ 27/28 [mlflow]
[2K   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╸━ 27/28 [mlflow]
[2K   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╸━ 27/28 [mlflow]
[2K   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╸━ 27/28 [mlflow]
[2K   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╸━ 27/28 [mlflow]
[2K   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╸━ 27/28 [mlflow]
[2K   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╸━ 27/28 [mlflow]
[2K   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 28/28 [mlflow]
[?25h
[1A[2KSuccessfully installed Flask-3.1.3 Flask-CORS-6.0.5 Mako-1.4.3 aiohappyeyeballs-2.7.1 aiohttp-3.14.5 aiosignal-1.4.0 alembic-1.20.1 blinker-1.9.0 docker-7.2.0 frozenlist-1.8.0 graphene-3.4.3 graphql-core-3.2.14 graphql-relay-3.2.0 gunicorn-26.2.0 huey-3.5.4 itsdangerous-2.2.0 mlflow-3.18.0 mlflow-skinny-3.18.0 mlflow-tracing-3.18.0 multidict-7.2.1 prettytable-3.19.0 propcache-0.5.4 python-multipart-0.0.34 skops-0.16.0 sqlalchemy-2.1.9 wcwidth-0.9.5 werkzeug-3.1.9 yarl-1.25.1
Note: you may need to restart the kernel using %restart_python or dbutils.library.restartPython() to use updated packages.
```

```python
dbutils.library.restartPython()
```

```python
import json
import os

for k, d in [("catalog", "main"), ("schema", "order_intake"), ("experiment", ""), ("warehouse_id", ""),
             ("serving_endpoint", "databricks-claude-haiku-4-5"), ("app_name", "order-intake-review"),
             ("max_text_chars", "30000")]:
    dbutils.widgets.text(k, d)
catalog, schema = dbutils.widgets.get("catalog"), dbutils.widgets.get("schema")
experiment, warehouse_id = dbutils.widgets.get("experiment"), dbutils.widgets.get("warehouse_id")
endpoint, app_name = dbutils.widgets.get("serving_endpoint"), dbutils.widgets.get("app_name")
max_chars = int(dbutils.widgets.get("max_text_chars"))
S = f"{catalog}.{schema}"
if not experiment or not warehouse_id:
    raise ValueError("experiment and warehouse_id are required (traces live in UC and need a SQL warehouse)")
os.environ["MLFLOW_TRACING_SQL_WAREHOUSE_ID"] = warehouse_id

import mlflow
from mlflow.entities import AssessmentSource
from mlflow.entities.trace_location import UnityCatalog

mlflow.set_tracking_uri("databricks")
exp = mlflow.set_experiment(experiment_name=experiment, trace_location=UnityCatalog(catalog, schema))
print(f"experiment {experiment} ({exp.experiment_id}); traces in {S}")
```

**Output:**

```
experiment /Users/<deployer>/fe-bar-fy27-quality (318810030266689); traces in evan_aws_01_catalog.fe_bar_fy27
```

```python
# ---- which documents still need a trace (new docs, or re-extracted with a new prompt version) ----
spark.sql(f"""CREATE TABLE IF NOT EXISTS {S}.quality_trace_index (
  doc_key STRING, content_hash STRING, prompt_version STRING, trace_id STRING,
  logged_at TIMESTAMP, scored BOOLEAN)
  COMMENT 'One row per document traced to the quality experiment (written by src/quality/05_log_traces.py)'""")

props = {r["key"]: r["value"] for r in spark.sql(f"SHOW TBLPROPERTIES {S}.extracted_parsed").collect()}
# hybrid extraction (03_gold): extractor + fallback_reason per document; older Gold tables -> NULL
_ep_cols = set(spark.table(f"{S}.extracted_parsed").columns)
_x = (", e.extractor, e.fallback_reason" if {"extractor", "fallback_reason"} <= _ep_cols
      else ", CAST(NULL AS STRING) extractor, CAST(NULL AS STRING) fallback_reason")
prompt_uri, prompt_version = props.get("prompt_uri", ""), props.get("prompt_version", "")

docs = spark.sql(f"""
  WITH o AS (   -- order-level checks + reasons per document
    SELECT source_path, attachment_filename,
      min(order_confidence) order_confidence,
      avg(CASE WHEN line_verified THEN 1.0 ELSE 0.0 END) lines_verified_share,
      min(completeness) completeness, bool_and(po_ok) po_valid, bool_or(customer_is_supplier) customer_is_supplier,
      count(*) n_lines,
      array_join(array_distinct(filter(collect_list(review_reasons), x -> x <> '')), '; ') review_reasons
    FROM {S}.purchase_orders GROUP BY 1, 2)
  SELECT concat(e.source_path, ' :: ', e.attachment_filename) doc_key, e.source_path, e.attachment_filename,
    e.content_hash, e.extraction_status, e.ai_error, e.raw_response, to_json(e.po) po_json{_x},
    p.parse_method, p.parse_confidence, substr(p.parsed_content, 1, {max_chars}) parsed_text,
    o.order_confidence, o.lines_verified_share, o.completeness, o.po_valid, o.customer_is_supplier, o.n_lines,
    o.review_reasons,
    (SELECT concat_ws(',', collect_list(r.order_id)) FROM {S}.review_orders r
      WHERE r.source_path = e.source_path AND r.attachment_filename = e.attachment_filename) order_ids
  FROM {S}.extracted_parsed e
  LEFT JOIN {S}.parsed_attachments p ON e.source_path = p.source_path AND e.attachment_filename = p.attachment_filename
  LEFT JOIN o ON e.source_path = o.source_path AND e.attachment_filename = o.attachment_filename
  LEFT ANTI JOIN {S}.quality_trace_index t
    ON t.doc_key = concat(e.source_path, ' :: ', e.attachment_filename)
   AND t.content_hash <=> e.content_hash AND t.prompt_version = '{prompt_version}'
  WHERE e.extraction_status <> 'duplicate'
""").toPandas()
print(f"{len(docs)} document(s) to trace (prompt v{prompt_version})")
```

**Output:**

```
0 document(s) to trace (prompt v1)
```

```python
def _clean(v):
    """NaN/NumPy -> plain JSON-able Python."""
    if v is None:
        return None
    try:
        if v != v:  # NaN
            return None
    except Exception:
        pass
    return v.item() if hasattr(v, "item") else v


code = AssessmentSource(source_type="CODE", source_id="extraction_checks")


def _checks(trace_id, r):
    """Deterministic checks as CODE feedback — one scalar per assessment (the server rejects dict values)."""
    if r["order_confidence"] is None:
        return
    items = [
        ("order_confidence", float(r["order_confidence"]), r["review_reasons"] or "all checks passed"),
        ("po_valid", bool(r["po_valid"]), None),
        ("customer_not_supplier", not bool(r["customer_is_supplier"]), None),
        ("lines_verified_share", round(float(r["lines_verified_share"] or 0), 3), None),
        ("completeness", round(float(r["completeness"] or 0), 3), None),
    ]
    for name, value, rationale in items:
        mlflow.log_feedback(trace_id=trace_id, name=name, value=value, source=code, rationale=rationale)


from concurrent.futures import ThreadPoolExecutor

index_rows, futures, errors = [], [], []
pool = ThreadPoolExecutor(max_workers=8)
try:
    for r in docs.to_dict("records"):
        r = {k: _clean(v) for k, v in r.items()}
        orders = (json.loads(r["po_json"]) or {}).get("orders") if r.get("po_json") else None
        with mlflow.start_span(name="extract_order", span_type="CHAIN") as root:
            root.set_inputs({"document": r["attachment_filename"], "source_path": r["source_path"],
                             "parse_method": r["parse_method"], "parsed_text": r["parsed_text"]})
            with mlflow.start_span(name=r.get("extractor") or "ai_query", span_type="LLM") as llm:
                llm.set_inputs({"endpoint": endpoint if (r.get("extractor") or "ai_query") == "ai_query" else "ai_extract",
                                "prompt_uri": prompt_uri, "prompt_version": prompt_version,
                                "extractor": r.get("extractor"), "fallback_reason": r.get("fallback_reason")})
                llm.set_outputs({"raw_response": (r["raw_response"] or "")[:max_chars], "ai_error": r["ai_error"]})
            root.set_outputs({"orders": orders, "extraction_status": r["extraction_status"]})
            mlflow.update_current_trace(tags={
                # source_trace_id is set at creation so labeling-session copies inherit it (tags added later aren't copied)
                "source_trace_id": root.trace_id,
                "document": r["attachment_filename"], "prompt_version": prompt_version,
                "extraction_status": r["extraction_status"], "order_ids": r["order_ids"] or "",
                "parse_method": r["parse_method"] or "",
                "extractor": r.get("extractor") or "ai_query", "fallback_reason": (r.get("fallback_reason") or "")[:250]})
            trace_id = root.trace_id
        index_rows.append((r["doc_key"], r["content_hash"], prompt_version, trace_id))
        futures.append(pool.submit(_checks, trace_id, r))
    for f in futures:
        try:
            f.result()
        except Exception as e:  # noqa — a failed check annotation shouldn't lose the trace
            errors.append(str(e).splitlines()[0][:200])
finally:
    pool.shutdown(wait=True)
    # record whatever was traced, even on failure, so a re-run doesn't trace the same documents twice
    if index_rows:
        (spark.createDataFrame(index_rows, "doc_key string, content_hash string, prompt_version string, trace_id string")
         .selectExpr("*", "current_timestamp() logged_at", "false scored")
         .write.mode("append").saveAsTable(f"{S}.quality_trace_index"))
print(f"logged {len(index_rows)} trace(s); {len(errors)} check-annotation error(s)" + (f": {errors[:3]}" if errors else ""))
```

**Output:**

```
logged 0 trace(s); 0 check-annotation error(s)
```

```python
# ---- stamp trace_id onto the review queue ----

if "trace_id" not in [f.name for f in spark.table(f"{S}.review_orders").schema.fields]:
    spark.sql(f"ALTER TABLE {S}.review_orders ADD COLUMNS (trace_id STRING)")
spark.sql(f"""
  MERGE INTO {S}.review_orders r
  USING (SELECT doc_key, max_by(trace_id, logged_at) trace_id FROM {S}.quality_trace_index GROUP BY doc_key) t
  ON concat(r.source_path, ' :: ', r.attachment_filename) = t.doc_key
  WHEN MATCHED THEN UPDATE SET r.trace_id = t.trace_id""")
```

**Output:**

```
{"text/plain": "DataFrame[num_affected_rows: bigint, num_updated_rows: bigint, num_deleted_rows: bigint, num_inserted_rows: bigint]"}
```

```python
# ---- let the Review App log human feedback: experiment edit + the UC trace tables ----
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.ml import ExperimentAccessControlRequest, ExperimentPermissionLevel

w = WorkspaceClient()
app_sp = w.apps.get(name=app_name).service_principal_client_id
w.experiments.update_permissions(exp.experiment_id, access_control_list=[ExperimentAccessControlRequest(
    service_principal_name=app_sp, permission_level=ExperimentPermissionLevel.CAN_EDIT)])
prefix = exp.experiment_id
for t in spark.sql(f"SHOW TABLES IN {S}").collect():
    name = t["tableName"]
    if name.startswith(prefix) or name.startswith("mlflow_experiment_trace"):
        for privs in ("SELECT, MODIFY", "SELECT"):      # views can't take MODIFY
            try:
                spark.sql(f"GRANT {privs} ON TABLE {S}.`{name}` TO `{app_sp}`")
                break
            except Exception as e:  # noqa — best effort; reported, never fatal
                err = str(e).splitlines()[0][:120]
        else:
            print(f"could not grant on {name}: {err}")
print(f"app {app_name} ({app_sp}): CAN_EDIT on experiment + trace-table grants")
```

**Output:**

```
app fe-bar-fy27-review (a95d3fff-082a-4c8a-974f-06194ba895c5): CAN_EDIT on experiment + trace-table grants
```

