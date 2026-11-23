# [dev <deployer>] fe_bar_order_intake_bootstrap / register_prompt (run 968671532196404, as executed, with outputs)

Notebook `4816fd86-66de-4957-92ca-1d4d78228444`, exported 2026-11-23 18:08 UTC from https://fevm-evan-aws-01.cloud.databricks.com via the Jobs export-run API.

## Setup 02 — Register the extraction prompt in the MLflow Prompt Registry
Registers `order_extraction` (template + JSON response schema) into the customer's
UC schema and aliases it `production`. **Must run BEFORE the pipeline** — the Gold
stage loads `prompts:/<catalog>.<schema>.order_extraction@production` at runtime.

Prompt-governance workflow: edit the template below (or in the UI) -> `register_prompt`
creates v2 -> compare eval runs -> `set_prompt_alias(..,'production',2)` to promote (or deploy with
`--var promote_prompt=true`). Re-running is safe: an unchanged template is not re-registered and
@production only moves on first install or when promote=true.

```python
%pip install "mlflow>=3.1"
```

**Output:**

```
Looking in indexes: [REDACTED]
Collecting mlflow>=3.1
  Downloading http://package-proxy.host.local:8184/pypi/v1/packages/mlflow/3.18.0/mlflow-3.18.0-py3-none-any.whl.metadata (50 kB)
Collecting mlflow-skinny==3.18.0 (from mlflow>=3.1)
  Downloading http://package-proxy.host.local:8184/pypi/v1/packages/mlflow-skinny/3.18.0/mlflow_skinny-3.18.0-py3-none-any.whl.metadata (51 kB)
Collecting mlflow-tracing==3.18.0 (from mlflow>=3.1)
  Downloading http://package-proxy.host.local:8184/pypi/v1/packages/mlflow-tracing/3.18.0/mlflow_tracing-3.18.0-py3-none-any.whl.metadata (19 kB)
Collecting Flask-CORS=3.1)
  Downloading http://package-proxy.host.local:8184/pypi/v1/packages/flask-cors/6.0.5/flask_cors-6.0.5-py3-none-any.whl.metadata (5.4 kB)
Collecting Flask=3.1)
  Downloading http://package-proxy.host.local:8184/pypi/v1/packages/flask/3.1.3/flask-3.1.3-py3-none-any.whl.metadata (3.2 kB)
Collecting aiohttp=3.7.0 (from mlflow>=3.1)
  Downloading http://package-proxy.host.local:8184/pypi/v1/packages/aiohttp/3.14.5/aiohttp-3.14.5-cp312-cp312-manylinux2014_aarch64.manylinux_2_17_aarch64.manylinux_2_28_aarch64.whl.metadata (8.3 kB)
Collecting alembic!=1.10.0,=3.1)
  Downloading http://package-proxy.host.local:8184/pypi/v1/packages/alembic/1.20.1/alembic-1.20.1-py3-none-any.whl.metadata (7.3 kB)
Requirement already satisfied: cryptography=43.0.0 in /databricks/python/lib/python3.12/site-packages (from mlflow>=3.1) (46.0.3)
Collecting docker=4.0.0 (from mlflow>=3.1)
  Downloading http://package-proxy.host.local:8184/pypi/v1/packages/docker/7.2.0/docker-7.2.0-py3-none-any.whl.metadata (3.8 kB)
Collecting graphene=3.1)
  Downloading http://package-proxy.host.local:8184/pypi/v1/packages/graphene/3.4.3/graphene-3.4.3-py2.py3-none-any.whl.metadata (6.9 kB)
Collecting gunicorn=3.1)
  Downloading http://package-proxy.host.local:8184/pypi/v1/packages/gunicorn/26.2.0/gunicorn-26.2.0-py3-none-any.whl.metadata (5.5 kB)
Collecting huey=2.5.4 (from mlflow>=3.1)
  Downloading http://package-proxy.host.local:8184/pypi/v1/packages/huey/3.5.4/huey-3.5.4-py3-none-any.whl.metadata (5.7 kB)
Requirement already satisfied: matplotlib=3.1) (3.10.6)
Requirement already satisfied: numpy=3.1) (2.3.4)
Requirement already satisfied: pandas=3.1) (2.3.3)
Requirement already satisfied: pyarrow=4.0.0 in /databricks/python/lib/python3.12/site-packages (from mlflow>=3.1) (21.0.0)
Requirement already satisfied: scikit-learn=3.1) (1.7.2)
Requirement already satisfied: scipy=3.1) (1.16.3)
Collecting skops=3.1)
  Downloading http://package-proxy.host.local:8184/pypi/v1/packages/skops/0.16.0/skops-0.16.0-py3-none-any.whl.metadata (4.3 kB)
Collecting sqlalchemy=1.4.0 (from mlflow>=3.1)
  Downloading http://package-proxy.host.local:8184/pypi/v1/packages/sqlalchemy/2.1.9/sqlalchemy-2.1.9-cp312-cp312-manylinux2014_aarch64.manylinux_2_17_aarch64.manylinux_2_28_aarch64.whl.metadata (9.7 kB)
Requirement already satisfied: anyio!=4.15.0,=3.6.2 in /databricks/python/lib/python3.12/site-packages (from mlflow-skinny==3.18.0->mlflow>=3.1) (4.10.0)
Requirement already satisfied: cachetools=5.0.0 in /databricks/python/lib/python3.12/site-packages (from mlflow-skinny==3.18.0->mlflow>=3.1) (5.5.1)
Requirement already satisfied: click=7.0 in /databricks/python/lib/python3.12/site-packages (from mlflow-skinny==3.18.0->mlflow>=3.1) (8.2.1)
Requirement already satisfied: cloudpicklemlflow>=3.1) (3.1.1)
Requirement already satisfied: databricks-sdk=0.20.0 in /databricks/python/lib/python3.12/site-packages (from mlflow-skinny==3.18.0->mlflow>=3.1) (0.122.0)
Requirement already satisfied: fastapimlflow>=3.1) (0.136.3)
Requirement already satisfied: gitpython=3.1.9 in /databricks/python/lib/python3.12/site-packages (from mlflow-skinny==3.18.0->mlflow>=3.1) (3.1.45)
Requirement already satisfied: importlib_metadata!=4.7.0,=3.7.0 in /databricks/python/lib/python3.12/site-packages (from mlflow-skinny==3.18.0->mlflow>=3.1) (8.7.0)
Requirement already satisfied: opentelemetry-api=1.9.0 in /databricks/python/lib/python3.12/site-packages (from mlflow-skinny==3.18.0->mlflow>=3.1) (1.42.1)
Requirement already satisfied: opentelemetry-proto=1.9.0 in /databricks/python/lib/python3.12/site-packages (from mlflow-skinny==3.18.0->mlflow>=3.1) (1.42.1)
Requirement already satisfied: opentelemetry-sdk=1.9.0 in /databricks/python/lib/python3.12/site-packages (from mlflow-skinny==3.18.0->mlflow>=3.1) (1.42.1)
Requirement already satisfied: packagingmlflow>=3.1) (25.0)
Requirement already satisfied: protobuf=3.12.0 in /databricks/python/lib/python3.12/site-packages (from mlflow-skinny==3.18.0->mlflow>=3.1) (6.33.5)
Requirement already satisfied: pydantic=2.0.0 in /databricks/python/lib/python3.12/site-packages (from mlflow-skinny==3.18.0->mlflow>=3.1) (2.13.3)
Requirement already satisfied: python-dotenv=0.19.0 in /databricks/python/lib/python3.12/site-packages (from mlflow-skinny==3.18.0->mlflow>=3.1) (1.2.2)
Collecting python-multipart=0.0.18 (from mlflow-skinny==3.18.0->mlflow>=3.1)
  Downloading http://package-proxy.host.local:8184/pypi/v1/packages/python-multipart/0.0.34/python_multipart-0.0.34-py3-none-any.whl.metadata (6.3 kB)
Requirement already satisfied: pyyaml=5.1 in /databricks/python/lib/python3.12/site-packages (from mlflow-skinny==3.18.0->mlflow>=3.1) (6.0.3)
Requirement already satisfied: requests=2.17.3 in /databricks/python/lib/python3.12/site-packages (from mlflow-skinny==3.18.0->mlflow>=3.1) (2.32.5)
Requirement already satisfied: sqlparse=0.4.0 in /databricks/python/lib/python3.12/site-packages (from mlflow-skinny==3.18.0->mlflow>=3.1) (0.5.5)
Requirement already satisfied: starlettemlflow>=3.1) (0.52.1)
Requirement already satisfied: typing-extensions=4.0.0 in /databricks/python/lib/python3.12/site-packages (from mlflow-skinny==3.18.0->mlflow>=3.1) (4.15.0)
Requirement already satisfied: uvicornmlflow>=3.1) (0.48.0)
Collecting aiohappyeyeballs>=2.5.0 (from aiohttp=3.7.0->mlflow>=3.1)
  Downloading http://package-proxy.host.local:8184/pypi/v1/packages/aiohappyeyeballs/2.7.1/aiohappyeyeballs-2.7.1-py3-none-any.whl.metadata (5.9 kB)
Collecting aiosignal>=1.4.0 (from aiohttp=3.7.0->mlflow>=3.1)
  Downloading http://package-proxy.host.local:8184/pypi/v1/packages/aiosignal/1.4.0/aiosignal-1.4.0-py3-none-any.whl.metadata (3.7 kB)
Requirement already satisfied: attrs>=17.3.0 in /databricks/python/lib/python3.12/site-packages (from aiohttp=3.7.0->mlflow>=3.1) (25.4.0)
Collecting frozenlist>=1.1.1 (from aiohttp=3.7.0->mlflow>=3.1)
  Downloading http://package-proxy.host.local:8184/pypi/v1/packages/frozenlist/1.8.0/frozenlist-1.8.0-cp312-cp312-manylinux2014_aarch64.manylinux_2_17_aarch64.manylinux_2_28_aarch64.whl.metadata (20 kB)
Collecting multidict=4.5 (from aiohttp=3.7.0->mlflow>=3.1)
  Downloading http://package-proxy.host.local:8184/pypi/v1/packages/multidict/7.2.1/multidict-7.2.1-cp312-cp312-manylinux2014_aarch64.manylinux_2_17_aarch64.manylinux_2_28_aarch64.whl.metadata (6.1 kB)
Collecting propcache>=0.2.0 (from aiohttp=3.7.0->mlflow>=3.1)
  Downloading http://package-proxy.host.local:8184/pypi/v1/packages/propcache/0.5.4/propcache-0.5.4-cp312-cp312-manylinux2014_aarch64.manylinux_2_17_aarch64.manylinux_2_28_aarch64.whl.metadata (25 kB)
Collecting yarl=1.25.1 (from aiohttp=3.7.0->mlflow>=3.1)
  Downloading http://package-proxy.host.local:8184/pypi/v1/packages/yarl/1.25.1/yarl-1.25.1-cp312-cp312-manylinux2014_aarch64.manylinux_2_17_aarch64.manylinux_2_28_aarch64.whl.metadata (111 kB)
Collecting Mako (from alembic!=1.10.0,mlflow>=3.1)
  Downloading http://package-proxy.host.local:8184/pypi/v1/packages/mako/1.4.3/mako-1.4.3-py3-none-any.whl.metadata (2.9 kB)
Requirement already satisfied: idna>=2.8 in /databricks/python/lib/python3.12/site-packages (from anyio!=4.15.0,=3.6.2->mlflow-skinny==3.18.0->mlflow>=3.1) (3.11)
Requirement already satisfied: sniffio>=1.1 in /databricks/python/lib/python3.12/site-packages (from anyio!=4.15.0,=3.6.2->mlflow-skinny==3.18.0->mlflow>=3.1) (1.3.0)
Requirement already satisfied: cffi>=2.0.0 in /databricks/python/lib/python3.12/site-packages (from cryptography=43.0.0->mlflow>=3.1) (2.0.0)
Requirement already satisfied: google-auth~=2.0 in /databricks/python/lib/python3.12/site-packages (from databricks-sdk=0.20.0->mlflow-skinny==3.18.0->mlflow>=3.1) (2.53.0)
Requirement already satisfied: urllib3=1.26 in /databricks/python/lib/python3.12/site-packages (from databricks-sdk=0.20.0->mlflow-skinny==3.18.0->mlflow>=3.1) (2.5.0)
Requirement already satisfied: typing-inspection>=0.4.2 in /databricks/python/lib/python3.12/site-packages (from fastapimlflow-skinny==3.18.0->mlflow>=3.1) (0.4.2)
Requirement already satisfied: annotated-doc>=0.0.2 in /databricks/python/lib/python3.12/site-packages (from fastapimlflow-skinny==3.18.0->mlflow>=3.1) (0.0.4)
Collecting blinker>=1.9.0 (from Flaskmlflow>=3.1)
  Downloading http://package-proxy.host.local:8184/pypi/v1/packages/blinker/1.9.0/blinker-1.9.0-py3-none-any.whl.metadata (1.6 kB)
Collecting itsdangerous>=2.2.0 (from Flaskmlflow>=3.1)
  Downloading http://package-proxy.host.local:8184/pypi/v1/packages/itsdangerous/2.2.0/itsdangerous-2.2.0-py3-none-any.whl.metadata (1.9 kB)
Requirement already satisfied: jinja2>=3.1.2 in /databricks/python/lib/python3.12/site-packages (from Flaskmlflow>=3.1) (3.1.6)
Requirement already satisfied: markupsafe>=2.1.1 in /databricks/python/lib/python3.12/site-packages (from Flaskmlflow>=3.1) (3.0.2)
Collecting werkzeug>=3.1.0 (from Flaskmlflow>=3.1)
  Downloading http://package-proxy.host.local:8184/pypi/v1/packages/werkzeug/3.1.9/werkzeug-3.1.9-py3-none-any.whl.metadata (4.1 kB)
Requirement already satisfied: gitdb=4.0.1 in /databricks/python/lib/python3.12/site-packages (from gitpython=3.1.9->mlflow-skinny==3.18.0->mlflow>=3.1) (4.0.11)
Requirement already satisfied: smmap=3.0.1 in /databricks/python/lib/python3.12/site-packages (from gitdb=4.0.1->gitpython=3.1.9->mlflow-skinny==3.18.0->mlflow>=3.1) (5.0.0)
Requirement already satisfied: pyasn1-modules>=0.2.1 in /databricks/python/lib/python3.12/site-packages (from google-auth~=2.0->databricks-sdk=0.20.0->mlflow-skinny==3.18.0->mlflow>=3.1) (0.4.2)
Collecting graphql-core=3.1 (from graphenemlflow>=3.1)
  Downloading http://package-proxy.host.local:8184/pypi/v1/packages/graphql-core/3.2.14/graphql_core-3.2.14-py3-none-any.whl.metadata (11 kB)
Collecting graphql-relay=3.1 (from graphenemlflow>=3.1)
  Downloading http://package-proxy.host.local:8184/pypi/v1/packages/graphql-relay/3.2.0/graphql_relay-3.2.0-py3-none-any.whl.metadata (12 kB)
Requirement already satisfied: python-dateutil=2.7.0 in /databricks/python/lib/python3.12/site-packages (from graphenemlflow>=3.1) (2.9.0.post0)
Requirement already satisfied: zipp>=3.20 in /databricks/python/lib/python3.12/site-packages (from importlib_metadata!=4.7.0,=3.7.0->mlflow-skinny==3.18.0->mlflow>=3.1) (3.23.0)
Requirement already satisfied: contourpy>=1.0.1 in /databricks/python/lib/python3.12/site-packages (from matplotlibmlflow>=3.1) (1.3.3)
Requirement already satisfied: cycler>=0.10 in /databricks/python/lib/python3.12/site-packages (from matplotlibmlflow>=3.1) (0.11.0)
Requirement already satisfied: fonttools>=4.22.0 in /databricks/python/lib/python3.12/site-packages (from matplotlibmlflow>=3.1) (4.60.1)
Requirement already satisfied: kiwisolver>=1.3.1 in /databricks/python/lib/python3.12/site-packages (from matplotlibmlflow>=3.1) (1.4.8)
Requirement already satisfied: pillow>=8 in /databricks/python/lib/python3.12/site-packages (from matplotlibmlflow>=3.1) (12.0.0)
Requirement already satisfied: pyparsing>=2.3.1 in /databricks/python/lib/python3.12/site-packages (from matplotlibmlflow>=3.1) (3.2.5)
Requirement already satisfied: opentelemetry-semantic-conventions==0.63b1 in /databricks/python/lib/python3.12/site-packages (from opentelemetry-sdk=1.9.0->mlflow-skinny==3.18.0->mlflow>=3.1) (0.63b1)
Requirement already satisfied: pytz>=2020.1 in /databricks/python/lib/python3.12/site-packages (from pandasmlflow>=3.1) (2026.5)
Requirement already satisfied: tzdata>=2022.7 in /databricks/python/lib/python3.12/site-packages (from pandasmlflow>=3.1) (2026.5)
Requirement already satisfied: annotated-types>=0.6.0 in /databricks/python/lib/python3.12/site-packages (from pydantic=2.0.0->mlflow-skinny==3.18.0->mlflow>=3.1) (0.7.0)
Requirement already satisfied: pydantic-core==2.46.3 in /databricks/python/lib/python3.12/site-packages (from pydantic=2.0.0->mlflow-skinny==3.18.0->mlflow>=3.1) (2.46.3)
Requirement already satisfied: six>=1.5 in /databricks/python/lib/python3.12/site-packages (from python-dateutil=2.7.0->graphenemlflow>=3.1) (1.17.0)
Requirement already satisfied: charset_normalizer=2 in /databricks/python/lib/python3.12/site-packages (from requests=2.17.3->mlflow-skinny==3.18.0->mlflow>=3.1) (3.4.4)
Requirement already satisfied: certifi>=2017.4.17 in /databricks/python/lib/python3.12/site-packages (from requests=2.17.3->mlflow-skinny==3.18.0->mlflow>=3.1) (2026.10.19)
Requirement already satisfied: joblib>=1.2.0 in /databricks/python/lib/python3.12/site-packages (from scikit-learnmlflow>=3.1) (1.5.2)
Requirement already satisfied: threadpoolctl>=3.1.0 in /databricks/python/lib/python3.12/site-packages (from scikit-learnmlflow>=3.1) (3.5.0)
Collecting prettytable>=3.9 (from skopsmlflow>=3.1)
  Downloading http://package-proxy.host.local:8184/pypi/v1/packages/prettytable/3.19.0/prettytable-3.19.0-py3-none-any.whl.metadata (37 kB)
Requirement already satisfied: h11>=0.8 in /databricks/python/lib/python3.12/site-packages (from uvicornmlflow-skinny==3.18.0->mlflow>=3.1) (0.16.0)
Requirement already satisfied: pycparser in /databricks/python/lib/python3.12/site-packages (from cffi>=2.0.0->cryptography=43.0.0->mlflow>=3.1) (2.23)
Collecting wcwidth>=0.3.5 (from prettytable>=3.9->skopsmlflow>=3.1)
  Downloading http://package-proxy.host.local:8184/pypi/v1/packages/wcwidth/0.9.5/wcwidth-0.9.5-cp310-abi3-manylinux2014_aarch64.manylinux_2_17_aarch64.whl.metadata (26 kB)
Requirement already satisfied: pyasn1=0.6.1 in /databricks/python/lib/python3.12/site-packages (from pyasn1-modules>=0.2.1->google-auth~=2.0->databricks-sdk=0.20.0->mlflow-skinny==3.18.0->mlflow>=3.1) (0.6.1)
Downloading http://package-proxy.host.local:8184/pypi/v1/packages/mlflow/3.18.0/mlflow-3.18.0-py3-none-any.whl (12.6 MB)
[?25l   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 0.0/12.6 MB ? eta -:--:--
[2K   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 12.6/12.6 MB 108.8 MB/s  0:00:00
[?25hDownloading http://package-proxy.host.local:8184/pypi/v1/packages/mlflow-skinny/3.18.0/mlflow_skinny-3.18.0-py3-none-any.whl (4.4 MB)
[?25l   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 0.0/4.4 MB ? eta -:--:--
[2K   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 4.4/4.4 MB 129.0 MB/s  0:00:00
[?25hDownloading http://package-proxy.host.local:8184/pypi/v1/packages/mlflow-tracing/3.18.0/mlflow_tracing-3.18.0-py3-none-any.whl (2.1 MB)
[?25l   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 0.0/2.1 MB ? eta -:--:--
[2K   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 2.1/2.1 MB 109.9 MB/s  0:00:00
[?25hDownloading http://package-proxy.host.local:8184/pypi/v1/packages/aiohttp/3.14.5/aiohttp-3.14.5-cp312-cp312-manylinux2014_aarch64.manylinux_2_17_aarch64.manylinux_2_28_aarch64.whl (1.9 MB)
[?25l   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 0.0/1.9 MB ? eta -:--:--
[2K   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 1.9/1.9 MB 95.8 MB/s  0:00:00
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
[2K   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 4.7/4.7 MB 87.2 MB/s  0:00:00
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
[2K   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 826.6/826.6 kB 42.7 MB/s  0:00:00
[?25hDownloading http://package-proxy.host.local:8184/pypi/v1/packages/werkzeug/3.1.9/werkzeug-3.1.9-py3-none-any.whl (228 kB)
Downloading http://package-proxy.host.local:8184/pypi/v1/packages/mako/1.4.3/mako-1.4.3-py3-none-any.whl (80 kB)
Installing collected packages: huey, werkzeug, wcwidth, sqlalchemy, python-multipart, propcache, multidict, Mako, itsdangerous, gunicorn, graphql-core, frozenlist, blinker, aiohappyeyeballs, yarl, prettytable, graphql-relay, Flask, docker, alembic, aiosignal, skops, graphene, Flask-CORS, aiohttp, mlflow-tracing, mlflow-skinny, mlflow
[?25l
[2K   ━╺━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  1/28 [werkzeug]
[2K  Attempting uninstall: wcwidth
   ━╺━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  1/28 [werkzeug]
[2K    Found existing installation: wcwidth 0.2.13
   ━╺━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  1/28 [werkzeug]
[2K    Not uninstalling wcwidth at /databricks/python3/lib/python3.12/site-packages, outside environment /local_disk0/.ephemeral_nfs/envs/pythonEnv-f52a3e1f-d878-466e-b574-c83f3617096c
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
[2K   ━━━━╺━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  3/28 [sqlalchemy]
[2K   ━━━━╺━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  3/28 [sqlalchemy]
[2K   ━━━━━━━━━━╺━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  7/28 [Mako]
[2K   ━━━━━━━━━━━━╸━━━━━━━━━━━━━━━━━━━━━━━━━━━  9/28 [gunicorn]
[2K   ━━━━━━━━━━━━━━╺━━━━━━━━━━━━━━━━━━━━━━━━━ 10/28 [graphql-core]
[2K  Attempting uninstall: blinker
   ━━━━━━━━━━━━━━╺━━━━━━━━━━━━━━━━━━━━━━━━━ 10/28 [graphql-core]
[2K    Found existing installation: blinker 1.7.0
   ━━━━━━━━━━━━━━╺━━━━━━━━━━━━━━━━━━━━━━━━━ 10/28 [graphql-core]
[2K    Not uninstalling blinker at /usr/lib/python3/dist-packages, outside environment /local_disk0/.ephemeral_nfs/envs/pythonEnv-f52a3e1f-d878-466e-b574-c83f3617096c
   ━━━━━━━━━━━━━━╺━━━━━━━━━━━━━━━━━━━━━━━━━ 10/28 [graphql-core]
[2K    Can't uninstall 'blinker'. No files were found to uninstall.
   ━━━━━━━━━━━━━━╺━━━━━━━━━━━━━━━━━━━━━━━━━ 10/28 [graphql-core]
[2K   ━━━━━━━━━━━━━━━━━━━━━━━━╺━━━━━━━━━━━━━━━ 17/28 [Flask]
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
[2K    Not uninstalling mlflow-skinny at /databricks/python3/lib/python3.12/site-packages, outside environment /local_disk0/.ephemeral_nfs/envs/pythonEnv-f52a3e1f-d878-466e-b574-c83f3617096c
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
import mlflow
dbutils.widgets.text("catalog", "main")
dbutils.widgets.text("schema", "order_intake")
dbutils.widgets.text("promote", "false")   # "true" = move @production to the version registered here
dbutils.widgets.text("promote_extract_schema", "false")   # same, for order_extract_schema (the ai_extract spec)
dbutils.widgets.text("lib_path", "")       # <bundle files>/src/lib (extract_spec.py)
catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
promote = dbutils.widgets.get("promote").strip().lower() == "true"
NAME = f"{catalog}.{schema}.order_extraction"

mlflow.set_registry_uri("databricks-uc")

line_item = {"type": "object", "properties": {
    "line_no": {"type": "integer"},
    "source_row": {"type": "string"},          # spreadsheets: row label as printed, e.g. "S1R35"
    "material_or_sku": {"type": "string"}, "description": {"type": "string"},
    "quantity": {"type": "number"}, "uom": {"type": "string"}, "unit_price": {"type": "number"},
    "line_confidence": {"type": "number"}},
    "required": ["material_or_sku", "quantity"]}
order = {"type": "object", "properties": {
    "po_number": {"type": "string"},
    "po_number_label": {"type": "string"},     # the label printed next to the PO number (grounding)
    "customer_name": {"type": "string"}, "customer_number": {"type": "string"},
    "order_date": {"type": "string"}, "currency": {"type": "string"}, "sales_org": {"type": "string"},
    "ship_to": {"type": "string"},
    "quantity_column": {"type": "string"},          # header text of the ORDERED-quantity column
    "quantity_column_letter": {"type": "string"},   # spreadsheets: its column letter, e.g. "E"
    "header_confidence": {"type": "number"},
    "line_items": {"type": "array", "items": line_item}},
    "required": ["line_items"]}
response_format = {"type": "json_schema", "json_schema": {"name": "po_batch", "strict": False,
    "schema": {"type": "object", "properties": {"orders": {"type": "array", "items": order}}, "required": ["orders"]}}}

# Supplier = Maison Solenne (fictional). NEVER the customer. (Extend this list as needed.)
SUPPLIER_ENTITIES = (
    "Maison Solenne (any country entity: S.A.S., GmbH, Ltd, Inc., FZE, Travel Retail), its customer-orders / "
    "field-sales teams, and the brands Solenne Paris, Kōri Botanicals / Kori Botanicals, Atelier Noor, Velour "
    "Cosmetics, Thornfield Grooming, Mistral Hair, Lune Rouge, Ember & Oak; and any address at maisonsolenne.*"
)

template = (
    "You extract retailer purchase orders sent TO Maison Solenne, for entry into SAP. "
    "Return JSON only, matching the schema.\n\n"
    "HOW THE DOCUMENT IS SHOWN\n"
    "- Spreadsheets are shown cell by cell: each line is one sheet row, e.g. "
    "\"S1R35: A=Shampoo | C=AX10010000 | E=3 | F=29.7\" means sheet 1, row 35, column A = Shampoo, etc. "
    "A column letter that is missing from a row means that cell is EMPTY. Use the header row's letters to know "
    "what each column is; never assume position.\n"
    "- PDFs are shown as text with HTML tables; an empty <td></td> is an empty cell.\n\n"
    "ORDERS\n"
    "1. Return one entry in `orders` per distinct PO number. If the document has no PO number, return exactly one order.\n\n"
    "PO NUMBER\n"
    "2. `po_number` is the BUYER'S order reference, copied exactly as printed. It is printed next to a label such as "
    "PO, P.O., Purchase Order No., Order No., Order number, Bestellnummer, Bestell-Nr., Auftragsnummer, "
    "Kunden-Auftragsnummer, Bestellreferenz, Referenz, N° de commande, Numéro de commande, Bon de commande N°, "
    "Commande n°, Pedido, Nº de pedido, Ordine n., Inkoopopdracht, Ordernummer, Bestelnummer, Sipariş No. "
    "Put that label text in `po_number_label`.\n"
    "3. A PO number is NEVER: a date; the document title, heading or file name (e.g. \"BON DE COMMANDE AOÛT 2026\", "
    "\"Order form\"); a product code, EAN or SKU; a customer, account or vendor number; an invoice, delivery-note, "
    "quote or page number; a phone number. If there is no PO number, OMIT `po_number` — never guess.\n\n"
    "CUSTOMER\n"
    "4. The customer is the retailer, store, salon or distributor that PLACES the order (look at sold-to / bill-to / "
    "ship-to / Rechnungs- or Lieferadresse / Kunde / Client / customer name and number fields, the sender and "
    "signature of an email, the fine print or footer of the page, and the letterhead of a document the buyer issued).\n"
    "5. The SUPPLIER is the recipient and must NEVER be returned as `customer_name`: " + SUPPLIER_ENTITIES + ". "
    "Order forms and price lists are often the supplier's own template, so their title and logo are the supplier, "
    "not the customer. A store or salon whose name merely CONTAINS a brand (e.g. \"Studio Mira Lune Rouge "
    "exclusive Salon\") IS a customer. If only the supplier can be identified, OMIT `customer_name`.\n\n"
    "LINE ITEMS AND QUANTITY\n"
    "6. First find the table's header row and the ONE column where the customer entered the ORDERED quantity "
    "(e.g. QTY, Qty, Quantity, Order quantity, Bestellmenge, Menge, Anzahl, Stück, Cantidad, Uds, Qté, Quantité, "
    "Aantal, Quantità, Adet; on periodic order forms \"Total periode\" / \"Total période\" / \"Total period\" is the "
    "quantity ordered for that period, not a grand total). Report its header text in `quantity_column` and, for spreadsheets, its letter in "
    "`quantity_column_letter`.\n"
    "7. These are NOT the ordered quantity: first-order / initial / launch quantities (\"First Order Qty\", "
    "Erstbestellung, Erstausstattung), minimum order quantity (MOQ, Mindestmenge), pack / case / inner / outer sizes "
    "(VE, PCB, colisage), stock or on-hand, tester or display quantities, prices (UVP, EK, EP, RRP, PVP, prix), "
    "totals and price×quantity columns, EAN/barcodes, and product sizes (ml, g). A non-zero line total or "
    "price×quantity cell confirms a row was ordered — use it as a cross-check, never as the quantity.\n"
    "8. Return ONLY rows whose ordered-quantity cell contains a number greater than 0. Order forms and price lists "
    "list the whole catalog and most rows are blank in that column — skip those. Do not skip a row because OTHER "
    "columns are blank, and never drop the LAST row of a table or a row that lacks a code or description.\n"
    "8a. Header labels can sit in a merged cell or one column off from their values. Confirm the column from the data: "
    "if the form has a line-total / price×quantity column, the ordered quantity is the value that multiplies the unit "
    "price to give that total, and a row whose total is exactly 0 is NOT ordered (an EMPTY total cell proves nothing). "
    "Report the letter of the column that actually contains the quantities.\n"

    "9. For each line: `material_or_sku` = the product/order code exactly as printed (keep leading zeros; prefer the "
    "order-code/material column, otherwise the EAN); `quantity` = the value from the ordered-quantity column, "
    "reading decimal and thousands separators in the document's locale (German \"1.000\" = 1000); `source_row` = the "
    "row label for spreadsheets (e.g. \"S1R35\"); `unit_price` = the net unit price if shown. Never use a "
    "recommended retail price (UVP, RRP, PVP, MSRP, prix conseillé) as `unit_price`; if only that is printed, omit "
    "`unit_price`. `description` is the product text of the row, never a column header (\"Originalware\", \"Artikel\", "
    "\"Article\", \"Bezeichnung\", \"Designation\" are headers).\n"
    "9a. In free-text emails a number after \"nr\", \"no.\", \"shade\", \"teinte\", \"kleur\", \"tint\" is a shade number "
    "of the product named before it, not a product code; the quantity is the number next to \"x\", \"maal\", \"fois\", "
    "\"stuks\", \"pcs\" (\"concealer nr 08, 2 maal\" = concealer, shade 08, quantity 2). Put the shade in the "
    "description and leave `material_or_sku` empty unless a real code is printed.\n\n"
    "GENERAL\n"
    "10. Copy codes and numbers verbatim. Do not invent placeholder values such as UNKNOWN or N/A — omit a field you "
    "cannot find. Set header_confidence and line_confidence in [0,1].\n\n"
    "Document:\n\n{{document}}"
)

# Idempotent (safe to run on every bootstrap): reuse the newest version if its template + schema are
# unchanged, otherwise register a new one. @production is set on first install, or when promote=true —
# so a re-run never silently moves a version someone promoted by hand.
latest = None
for v in range(200, 0, -1):
    try:
        latest = mlflow.genai.load_prompt(f"prompts:/{NAME}/{v}")
        break
    except Exception:
        continue
if latest is not None and latest.template == template and latest.response_format == response_format:
    pv = latest
    print(f"{NAME} v{pv.version} already has this template — not re-registered")
else:
    pv = mlflow.register_prompt(
        name=NAME, template=template,
        commit_message="v3 (customer feedback): Total periode = ordered quantity; keep last/sparse rows; no UVP as unit price; "
                       "no column headers as description; shade numbers in emails; ship-to/customer from fine print",
        tags={"parser": "ai_parse_document", "extractor": "ai_query", "schema": "orders_array_v2"},
        response_format=response_format,
    )
    print(f"Registered {NAME} v{pv.version}")

try:
    current = mlflow.genai.load_prompt(f"prompts:/{NAME}@production").version
except Exception:
    current = None
if current is None or promote:
    mlflow.set_prompt_alias(NAME, "production", pv.version)
    print(f"alias production -> v{pv.version}" + (f" (was v{current})" if current else " (first install)"))
else:
    print(f"alias production stays on v{current}" + ("" if current == pv.version else
          f"; to use v{pv.version} deploy with --var promote_prompt=true or set the alias by hand"))
```

**Output:**

```
evan_aws_01_catalog.fe_bar_fy27.order_extraction v1 already has this template — not re-registered
alias production stays on v1
```

### `order_extract_schema` — the ai_extract (v2.1, precision mode) spec of the hybrid extractor
Template = the ai_extract **instructions** (the business rules above, adapted: src/lib/extract_spec.py);
response_format = the ai_extract **schema** (orders[] with header fields + line_items[], every column named).
Gold (extraction_mode=hybrid) loads `prompts:/<catalog>.<schema>.order_extract_schema@production`.
Its own alias only: `order_extraction`'s aliases are never touched here. @production moves on first install or
with promote_extract_schema=true.

```python
import os
import sys
lib = dbutils.widgets.get("lib_path").strip() or os.path.abspath(os.path.join(os.getcwd(), "..", "lib"))
sys.path.insert(0, lib)
import extract_spec as _xs

SNAME = f"{catalog}.{schema}.order_extract_schema"
promote_x = dbutils.widgets.get("promote_extract_schema").strip().lower() == "true"
x_template = _xs.instructions_from_prompt(template)
x_schema = _xs.SCHEMA
latest_x = None
for v in range(200, 0, -1):
    try:
        latest_x = mlflow.genai.load_prompt(f"prompts:/{SNAME}/{v}")
        break
    except Exception:
        continue
if latest_x is not None and latest_x.template == x_template and latest_x.response_format == x_schema:
    xv = latest_x
    print(f"{SNAME} v{xv.version} already has this spec — not re-registered")
else:
    xv = mlflow.register_prompt(
        name=SNAME, template=x_template, response_format=x_schema,
        commit_message="ai_extract v2.1 precision spec: orders[] schema (every column named) + instructions derived "
                       "from order_extraction",
        tags={"extractor": "ai_extract", "ai_extract_version": _xs.AI_EXTRACT_VERSION, "mode": "precision",
              "schema": "orders_array_v2"})
    print(f"Registered {SNAME} v{xv.version}")
try:
    current_x = mlflow.genai.load_prompt(f"prompts:/{SNAME}@production").version
except Exception:
    current_x = None
if current_x is None or promote_x:
    mlflow.set_prompt_alias(SNAME, "production", xv.version)
    print(f"{SNAME}: alias production -> v{xv.version}" + (f" (was v{current_x})" if current_x else " (first install)"))
else:
    print(f"{SNAME}: alias production stays on v{current_x}")
```

**Output:**

```
evan_aws_01_catalog.fe_bar_fy27.order_extract_schema v1 already has this spec — not re-registered
evan_aws_01_catalog.fe_bar_fy27.order_extract_schema: alias production stays on v1
```

