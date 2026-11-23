# [dev <deployer>] fe_bar_order_intake_run / score_traces (run 327408329094283, as executed, with outputs)

Notebook `981c5ac5-2d53-4885-b7b5-68257f2659f0`, exported 2026-11-23 18:08 UTC from https://fevm-evan-aws-01.cloud.databricks.com via the Jobs export-run API.

## Quality 06 — LLM judges on new traces
Scores every trace in `quality_trace_index` that hasn't been scored yet with three judges (run on a stronger
model than the extractor). Each judge sees the parsed document (`inputs`) and the extracted orders
(`outputs`); results are attached to the traces as **LLM_JUDGE** feedback and summarized in an MLflow
evaluation run in the quality experiment.

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
[2K   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 12.6/12.6 MB 136.3 MB/s  0:00:00
[?25hDownloading http://package-proxy.host.local:8184/pypi/v1/packages/mlflow-skinny/3.18.0/mlflow_skinny-3.18.0-py3-none-any.whl (4.4 MB)
[?25l   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 0.0/4.4 MB ? eta -:--:--
[2K   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 4.4/4.4 MB 91.0 MB/s  0:00:00
[?25hDownloading http://package-proxy.host.local:8184/pypi/v1/packages/mlflow-tracing/3.18.0/mlflow_tracing-3.18.0-py3-none-any.whl (2.1 MB)
[?25l   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 0.0/2.1 MB ? eta -:--:--
[2K   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 2.1/2.1 MB 69.9 MB/s  0:00:00
[?25hDownloading http://package-proxy.host.local:8184/pypi/v1/packages/aiohttp/3.14.5/aiohttp-3.14.5-cp312-cp312-manylinux2014_aarch64.manylinux_2_17_aarch64.manylinux_2_28_aarch64.whl (1.9 MB)
[?25l   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 0.0/1.9 MB ? eta -:--:--
[2K   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 1.9/1.9 MB 72.5 MB/s  0:00:00
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
[2K   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 4.7/4.7 MB 112.0 MB/s  0:00:00
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
[2K   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 826.6/826.6 kB 38.3 MB/s  0:00:00
[?25hDownloading http://package-proxy.host.local:8184/pypi/v1/packages/werkzeug/3.1.9/werkzeug-3.1.9-py3-none-any.whl (228 kB)
Downloading http://package-proxy.host.local:8184/pypi/v1/packages/mako/1.4.3/mako-1.4.3-py3-none-any.whl (80 kB)
Installing collected packages: huey, werkzeug, wcwidth, sqlalchemy, python-multipart, propcache, multidict, Mako, itsdangerous, gunicorn, graphql-core, frozenlist, blinker, aiohappyeyeballs, yarl, prettytable, graphql-relay, Flask, docker, alembic, aiosignal, skops, graphene, Flask-CORS, aiohttp, mlflow-tracing, mlflow-skinny, mlflow
[?25l
[2K   ━╺━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  1/28 [werkzeug]
[2K  Attempting uninstall: wcwidth
   ━╺━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  1/28 [werkzeug]
[2K    Found existing installation: wcwidth 0.2.13
   ━╺━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  1/28 [werkzeug]
[2K    Not uninstalling wcwidth at /databricks/python3/lib/python3.12/site-packages, outside environment /local_disk0/.ephemeral_nfs/envs/pythonEnv-08be6ead-de90-43cf-9d06-67e9aed0840f
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
[2K   ━━━━━━━━╸━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  6/28 [multidict]
[2K   ━━━━━━━━━━━━╸━━━━━━━━━━━━━━━━━━━━━━━━━━━  9/28 [gunicorn]
[2K   ━━━━━━━━━━━━━━╺━━━━━━━━━━━━━━━━━━━━━━━━━ 10/28 [graphql-core]
[2K  Attempting uninstall: blinker
   ━━━━━━━━━━━━━━╺━━━━━━━━━━━━━━━━━━━━━━━━━ 10/28 [graphql-core]
[2K    Found existing installation: blinker 1.7.0
   ━━━━━━━━━━━━━━╺━━━━━━━━━━━━━━━━━━━━━━━━━ 10/28 [graphql-core]
[2K    Not uninstalling blinker at /usr/lib/python3/dist-packages, outside environment /local_disk0/.ephemeral_nfs/envs/pythonEnv-08be6ead-de90-43cf-9d06-67e9aed0840f
   ━━━━━━━━━━━━━━╺━━━━━━━━━━━━━━━━━━━━━━━━━ 10/28 [graphql-core]
[2K    Can't uninstall 'blinker'. No files were found to uninstall.
   ━━━━━━━━━━━━━━╺━━━━━━━━━━━━━━━━━━━━━━━━━ 10/28 [graphql-core]
[2K   ━━━━━━━━━━━━━━━━━━━━╺━━━━━━━━━━━━━━━━━━━ 14/28 [yarl]
[2K   ━━━━━━━━━━━━━━━━━━━━━━━━━╸━━━━━━━━━━━━━━ 18/28 [docker]
[2K   ━━━━━━━━━━━━━━━━━━━━━━━━━━━╺━━━━━━━━━━━━ 19/28 [alembic]
[2K   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╺━━━━━━━━━ 21/28 [skops]
[2K   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╺━━━━━ 24/28 [aiohttp]
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
[2K    Not uninstalling mlflow-skinny at /databricks/python3/lib/python3.12/site-packages, outside environment /local_disk0/.ephemeral_nfs/envs/pythonEnv-08be6ead-de90-43cf-9d06-67e9aed0840f
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
import os

for k, d in [("catalog", "main"), ("schema", "order_intake"), ("experiment", ""), ("warehouse_id", ""),
             ("judge_endpoint", "databricks-claude-sonnet-5")]:
    dbutils.widgets.text(k, d)
catalog, schema = dbutils.widgets.get("catalog"), dbutils.widgets.get("schema")
experiment, warehouse_id = dbutils.widgets.get("experiment"), dbutils.widgets.get("warehouse_id")
judge_model = f"databricks:/{dbutils.widgets.get('judge_endpoint')}"
S = f"{catalog}.{schema}"
os.environ["MLFLOW_TRACING_SQL_WAREHOUSE_ID"] = warehouse_id

import mlflow
from mlflow.entities.trace_location import UnityCatalog
from mlflow.genai.judges import make_judge

mlflow.set_tracking_uri("databricks")
exp = mlflow.set_experiment(experiment_name=experiment, trace_location=UnityCatalog(catalog, schema))

pending = [r["trace_id"] for r in spark.sql(
    f"SELECT trace_id FROM {S}.quality_trace_index WHERE NOT scored").collect()]
print(f"{len(pending)} trace(s) to score")
```

**Output:**

```
0 trace(s) to score
```

```python
SUPPLIER = ("Maison Solenne or any of its entities or brands (Solenne Paris, Kōri Botanicals, Atelier Noor, "
            "Velour Cosmetics, Thornfield Grooming, Mistral Hair, Lune Rouge, Ember & Oak)")
judges = [
    make_judge(
        name="customer_is_buyer",
        instructions=(
            "You review purchase orders extracted from a retailer's document. The parsed source document is in "
            "{{ inputs }} and the extraction is in {{ outputs }}. Is every order's customer_name the retailer, store, "
            f"salon or distributor that PLACED the order (not the supplier: {SUPPLIER})? A store whose name merely "
            "contains a brand counts as a customer. If customer_name is missing, answer true only if the document "
            "truly names no customer. Answer true or false."),
        feedback_value_type=bool, model=judge_model),
    make_judge(
        name="po_number_valid",
        instructions=(
            "The parsed source document is in {{ inputs }} and the extraction is in {{ outputs }}. For each order, is "
            "po_number the buyer's own order reference as printed in the document (not a date, document title, "
            "product code, customer/account number, invoice or page number)? If po_number is missing, answer true "
            "only if the document has no order reference. Answer true or false."),
        feedback_value_type=bool, model=judge_model),
    make_judge(
        name="lines_correct_and_complete",
        instructions=(
            "The parsed source document is in {{ inputs }} (spreadsheets appear cell by cell as 'S1R35: A=.. | E=3'; "
            "a missing column letter is an empty cell) and the extraction is in {{ outputs }}. Did the extraction "
            "capture every ORDERED line (rows where the customer entered a quantity greater than 0) with the right "
            "product code and quantity, and nothing else (no unordered catalog rows, no prices or pack sizes read as "
            "quantities)? Answer true or false and name any missed, extra or wrong lines in the rationale."),
        feedback_value_type=bool, model=judge_model),
]
```

```python
if pending:
    traces = mlflow.search_traces(experiment_ids=[exp.experiment_id], max_results=5000)
    traces = traces[traces["trace_id"].isin(set(pending))]
    print(f"scoring {len(traces)} trace(s) with {judge_model}")
    result = mlflow.genai.evaluate(data=traces, scorers=judges)
    print("evaluation run:", result.run_id, "| metrics:", result.metrics)
    ids = ",".join(f"'{t}'" for t in traces["trace_id"])
    if ids:
        spark.sql(f"UPDATE {S}.quality_trace_index SET scored = true WHERE trace_id IN ({ids})")
```

```python
# ---- mirror expert labels from labeling-session copies onto the original traces ----
# A labeling session works on COPIES of the traces. A copy keeps the creation-time tags (source_trace_id, set in
# 05_log_traces.py) and the original's request_time; older traces without the tag are matched on
# (document, request_time). Copy every HUMAN label onto the original once, so one trace per document holds the
# code checks, the judge scores, the Review App feedback and the expert labels.
from mlflow.entities import AssessmentSource

has_sessions = spark.catalog.tableExists(f"{S}.quality_review_sessions")
names = [r["session_name"] for r in spark.sql(
    f"SELECT DISTINCT session_name FROM {S}.quality_review_sessions").collect()] if has_sessions else []
mirrored = 0
if names:
    from mlflow.genai.labeling import get_labeling_sessions
    sessions = {x.name: x for x in get_labeling_sessions()}
    originals = mlflow.search_traces(experiment_ids=[exp.experiment_id], max_results=5000)
    indexed = {r["trace_id"] for r in spark.sql(f"SELECT trace_id FROM {S}.quality_trace_index").collect()}
    by_doc_time = {((r["tags"] or {}).get("document"), r["request_time"]): r["trace_id"]
                   for _, r in originals.iterrows() if r["trace_id"] in indexed}
    for name in names:
        sess = sessions.get(name)
        if sess is None:
            continue
        copies = mlflow.search_traces(run_id=sess.mlflow_run_id, max_results=5000)
        for _, c in copies.iterrows():
            original = (c["tags"] or {}).get("source_trace_id") or \
                by_doc_time.get(((c["tags"] or {}).get("document"), c["request_time"]))
            labels = [a for a in (c["assessments"] or []) if (a.get("source") or {}).get("source_type") == "HUMAN"]
            if not original or not labels:
                continue
            have = {(a.name, a.source.source_id) for a in (mlflow.get_trace(original).info.assessments or [])}
            for a in labels:
                key = (a.get("assessment_name"), (a.get("source") or {}).get("source_id"))
                value = (a.get("feedback") or {}).get("value")
                if key in have or value is None:
                    continue
                mlflow.log_feedback(trace_id=original, name=key[0], value=value,
                                    source=AssessmentSource(source_type="HUMAN", source_id=key[1]),
                                    rationale=a.get("rationale"), metadata={"labeling_session": name})
                mirrored += 1
print(f"mirrored {mirrored} expert label(s) onto original traces")
```

**Output:**

```
mirrored 0 expert label(s) onto original traces
```

