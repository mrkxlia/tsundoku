---
url: https://github.com/microsoft/data-formulator
created: '2026-08-11T21:35:08'
type: article
tags:
- ai
- データ分析
- データ可視化
- オープンソース
- microsoft
summary: 'Data Formulatorは、AIエージェントを活用して多様なデータソースに接続し、対話的に探索や可視化を行えるオープンソースツールです。

  会話を通じたデータベースの読み込みや、編集・分岐が可能な高度なチャートギャラリーを備え、データ分析の効率を大幅に向上させます。

  最新のv0.8アルファ版では、Databricks連携や企業向け認証機能、永続的なアナリスト添付ファイルなどの新機能が追加されています。'
---

# microsoft/data-formulator: 🪄 Data Formulator is an interactive AI-powered data analysis system makes it easy to connect, explore and visualize data.
2026-08-11
## Data Formulator: AI-powered Data Visualization

🪄 Explore data with visualizations, powered by AI agents.

[![Try Online Demo](https://camo.githubusercontent.com/7e10e55d2ec1d8bbd43e1edf0a5ce80a77e64a27ac4a6dd7b200459e20a70e2d/68747470733a2f2f696d672e736869656c64732e696f2f62616467652ff09f9a805f5472795f4f6e6c696e655f44656d6f2d646174612d2d666f726d756c61746f722e61692d4635394530423f7374796c653d666f722d7468652d6261646765)](https://data-formulator.ai/) [![Install Locally](https://camo.githubusercontent.com/be503d5a15e8a5737e39b1826c8c05ef498a34c4780ce425fae00ae61a83bb2b/68747470733a2f2f696d672e736869656c64732e696f2f62616467652ff09f92bb5f496e7374616c6c5f4c6f63616c6c792d7576785f7c5f7069702d3337373641423f7374796c653d666f722d7468652d6261646765)](#get-started)

[![PyPI](https://camo.githubusercontent.com/8ff1ad9d10088160bf99fa6af41e0c5680f0ec5c9c37aeba19e545f57b7cd7c5/68747470733a2f2f696d672e736869656c64732e696f2f707970692f762f646174615f666f726d756c61746f722e7376673f6c6162656c3d70797069253341253230646174615f666f726d756c61746f72)](https://pypi.org/project/data_formulator/)   [![License: MIT](https://camo.githubusercontent.com/fdf2982b9f5d7489dcf44570e714e3a15fce6253e0cc6b5aa61a075aac2ff71b/68747470733a2f2f696d672e736869656c64732e696f2f62616467652f4c6963656e73652d4d49542d79656c6c6f772e737667)](https://opensource.org/licenses/MIT)   [![YouTube](https://camo.githubusercontent.com/e52cacb5d03317dfdea99cd5b41840681ede73d0b791c56111acf935e7b77859/68747470733a2f2f696d672e736869656c64732e696f2f62616467652f596f75547562652d77686974653f6c6f676f3d796f7574756265266c6f676f436f6c6f723d253233464630303030)](https://www.youtube.com/watch?v=GfTE2FLyMrs)   [![build](https://github.com/microsoft/data-formulator/actions/workflows/python-build.yml/badge.svg)](https://github.com/microsoft/data-formulator/actions/workflows/python-build.yml)   [![Discord](https://camo.githubusercontent.com/70cc9e7fb6549b8fb6ce0a0c480bbbd279fce5f4ef39bf21d891fbd9e697efe3/68747470733a2f2f696d672e736869656c64732e696f2f62616467652f646973636f72642d636861742d677265656e3f6c6f676f3d646973636f7264)](https://discord.gg/mYCZMQKYZb)

## Why Data Formulator?

Your data lives everywhere — databases, warehouses, BI tools, files. Coding agents can help, but only after someone wires them up, and answers come back as walls of code or text that are hard to follow, refine, or share.

Data Formulator makes it simple: **connect any data, ask anything, get charts you can edit, branch, and share** — all on one interactive, visual canvas.

- **Data & platform teams**: wire up your databases, warehouses, and BI sources once, and give the whole org an AI-powered data exploration layer.
- **Analysts & users**: ask, edit, branch, share. It's so easy to get insights from good-looking charts.
Data.Formulator-0.7-1080p.mp4<video src="https://private-user-images.githubusercontent.com/93549116/599350667-8e4f8a08-6423-4227-a1f7-559e0126ce31.mp4?jwt=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJnaXRodWIuY29tIiwiYXVkIjoicmF3LmdpdGh1YnVzZXJjb250ZW50LmNvbSIsImtleSI6ImtleTUiLCJleHAiOjE3ODY0NTEyMjEsIm5iZiI6MTc4NjQ1MDkyMSwicGF0aCI6Ii85MzU0OTExNi81OTkzNTA2NjctOGU0ZjhhMDgtNjQyMy00MjI3LWExZjctNTU5ZTAxMjZjZTMxLm1wND9YLUFtei1BbGdvcml0aG09QVdTNC1ITUFDLVNIQTI1NiZYLUFtei1DcmVkZW50aWFsPUFLSUFWQ09EWUxTQTUzUFFLNFpBJTJGMjAyNjA4MTElMkZ1cy1lYXN0LTElMkZzMyUyRmF3czRfcmVxdWVzdCZYLUFtei1EYXRlPTIwMjYwODExVDEyMjIwMVomWC1BbXotRXhwaXJlcz0zMDAmWC1BbXotU2lnbmF0dXJlPTE3MzM5MmU4MzUyZjg2ZGVkYzQyNTdiMzIzZTk5ZjRlNjljNDQwNDM1NjkxODA2ZDFhMTRlZDhkNDM4M2NlY2UmWC1BbXotU2lnbmVkSGVhZGVycz1ob3N0JnJlc3BvbnNlLWNvbnRlbnQtdHlwZT12aWRlbyUyRm1wNCJ9.haYDsbN50hcXz2xvr__QVH72b5uWYh5DcJgA_X0WuPI" controls="controls"></video>

> [!tip] Tip
> **Love the charts?** They're built on [**Flint**](https://github.com/microsoft/flint-chart) — our open-source visualization language that compiles compact, semantic chart specs into polished Vega-Lite, ECharts, and Chart.js. Explore the [project site](https://microsoft.github.io/flint-chart/) or drop it into your own app.

## News 🔥🔥🔥

\[07-23-2026\] **Data Formulator 0.8 alpha** (a1–a4, latest: 0.8.0a4) includes:

- **Conversational database loading.** Agents can discover relevant tables, propose filters, preview results, and revise a loading plan through conversation before importing data.
- **Unified Data Thread.** Questions, clarifications, explanations, tables, and charts share one conversation history, with branching from earlier steps into new questions, calculated columns, or visualizations.
- **Expanded chart gallery, powered by Flint.** New bullet, connected scatter, ECDF, Gantt, range area, slope, sparkline, and violin charts, along with improved chart recommendations. Try the open-source [Flint chart language](https://microsoft.github.io/flint-chart/) in your own applications.
- **Persistent analyst attachments.** CSV, JSON, Excel, and other attached files remain available to the analyst throughout an exploration instead of being embedded once in a prompt.
- **Databricks connector.** Browse Unity Catalog catalogs, schemas, and tables, then load Databricks data into the exploration workflow.
- **Microsoft authentication for enterprise connectors.** SQL Server supports passwordless Microsoft Entra ID authentication through `az login`, including an in-app flow for local deployments. Kusto supports delegated Microsoft sign-in alongside Azure default identity and service principal authentication.
- **Connector setup and diagnostics.** Connection forms separate connection, scope, and source-specific authentication options. Persistent server logs and an in-app log viewer help diagnose failures.

> Preview with `pip install --pre data_formulator==0.8.0a4` or `uvx data_formulator@0.8.0a4`.

> Install the latest stable release (0.7) with `pip install data_formulator` or run instantly with `uvx data_formulator`.

## Previous Updates

Here are milestones that lead to the current design:

- **v0.7** (05-28-2026): Turn ANY data into insights in five steps — connect governed data sources, load via agents, explore with the unified `DataAgent` + Data Thread, refine 30+ chart types (semantic chart engine powered by [Flint](https://github.com/microsoft/flint-chart)) with a style-refinement agent, and share as reports. Plus persistent sessions & workspaces and a multilingual (English/Chinese) UI.
- **v0.7 alpha 2** (05-11-2026): Early preview of data connectors, the unified `DataAgent` with thread memory, persistent workspaces, the semantic chart engine, and experimental knowledge distillation.
- **v0.6** ([Demo](https://github.com/microsoft/data-formulator/releases/tag/0.6)): Real-time insights from live data — connect to URLs and databases with automatic refresh
- **uv support**: Faster installation with [uv](https://docs.astral.sh/uv/) — `uvx data_formulator` or `uv pip install data_formulator`
- **v0.5.1** ([Demo](https://github.com/microsoft/data-formulator/pull/200#issue-3635408217)): Community data loaders, US Map & Pie Chart, editable reports, snappier UI
- **v0.5**: Vibe with your data, in control — agent mode, data extraction, reports
- **v0.2.2** ([Demo](https://github.com/microsoft/data-formulator/pull/176)): Goal-driven exploration with agent recommendations and performance improvements
- **v0.2.1.3/4** ([Readme](https://github.com/microsoft/data-formulator/tree/main/py-src/data_formulator/data_loader) | [Demo](https://github.com/microsoft/data-formulator/pull/155)): External data loaders (MySQL, PostgreSQL, MSSQL, Azure Data Explorer, S3, Azure Blob)
- **v0.2** ([Demos](https://github.com/microsoft/data-formulator/releases/tag/0.2)): Large data support with DuckDB integration
- **v0.1.7** ([Demos](https://github.com/microsoft/data-formulator/releases/tag/0.1.7)): Dataset anchoring for cleaner workflows
- **v0.1.6** ([Demo](https://github.com/microsoft/data-formulator/releases/tag/0.1.6)): Multi-table support with automatic joins
- **Model Support**: OpenAI, Azure, Ollama, Anthropic via [LiteLLM](https://github.com/BerriAI/litellm) ([feedback](https://github.com/microsoft/data-formulator/issues/49))
- **Python Package**: Easy local installation ([try it](#get-started))
- **Visualization Challenges**: Test your skills ([challenges](https://github.com/microsoft/data-formulator/issues/53))
- **Data Extraction**: Parse data from images and text ([demo](https://github.com/microsoft/data-formulator/pull/31#issuecomment-2403652717))
- **Initial Release**: [Blog](https://www.microsoft.com/en-us/research/blog/data-formulator-exploring-how-ai-can-help-analysts-create-rich-data-visualizations/) | [Video](https://youtu.be/3ndlwt0Wi3c)

## Overview

**Data Formulator** is a Microsoft Research project for data exploration with visualizations powered by AI agents. It combines *UI interactions* with *natural language* so analysts can communicate intent, branch into alternative analyses, and share results — starting from any data format (screenshot, text, CSV, or database).

## Get Started

Play with Data Formulator with one of the following options.

- **Option 1: Install via uv (recommended)**
	[uv](https://docs.astral.sh/uv/) is an extremely fast Python package manager. If you have uv installed, you can run Data Formulator directly without any setup:
	```
	uvx data_formulator
	```
	Run `uvx data_formulator --help` to see all available options, such as custom port, sandboxing mode, and data storage location.
- **Option 2: Install via pip**
	Use pip for installation (recommend: install it in a virtual environment).
	```
	pip install data_formulator # install
	python -m data_formulator # run
	```
	Data Formulator will be automatically opened in the browser at [http://localhost:5567](http://localhost:5567/).
- **Option 3: Run with Docker**
	```
	docker compose up --build
	```
	Open [http://localhost:5567](http://localhost:5567/) in your browser. To stop, press `Ctrl+C` or run `docker compose down`.
- **Option 4: Codespaces**
	You can run Data Formulator in Codespaces; we have everything pre-configured. For more details, see [CODESPACES.md](https://github.com/microsoft/data-formulator/blob/main/CODESPACES.md).
	[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/microsoft/data-formulator?quickstart=1)
- **Option 5: Working as developer**
	You can build Data Formulator locally and develop your own version. Check out details in [DEVELOPMENT.md](https://github.com/microsoft/data-formulator/blob/main/DEVELOPMENT.md).

## Using Data Formulator

Besides uploading csv, tsv or xlsx files that contain structured data, you can ask Data Formulator to extract data from screenshots, text blocks or websites, or load data from databases use connectors. Then you are ready to explore. Ask visualizaiton questions, edit charts, or delegate some exploration tasks to agents. Then, create reports to share your insights.

data-formulator-tutorial.mp4<video src="https://private-user-images.githubusercontent.com/93549116/507946971-164aff58-9f93-4792-b8ed-9944578fbb72.mp4?jwt=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJnaXRodWIuY29tIiwiYXVkIjoicmF3LmdpdGh1YnVzZXJjb250ZW50LmNvbSIsImtleSI6ImtleTUiLCJleHAiOjE3ODY0NTEyMjEsIm5iZiI6MTc4NjQ1MDkyMSwicGF0aCI6Ii85MzU0OTExNi81MDc5NDY5NzEtMTY0YWZmNTgtOWY5My00NzkyLWI4ZWQtOTk0NDU3OGZiYjcyLm1wND9YLUFtei1BbGdvcml0aG09QVdTNC1ITUFDLVNIQTI1NiZYLUFtei1DcmVkZW50aWFsPUFLSUFWQ09EWUxTQTUzUFFLNFpBJTJGMjAyNjA4MTElMkZ1cy1lYXN0LTElMkZzMyUyRmF3czRfcmVxdWVzdCZYLUFtei1EYXRlPTIwMjYwODExVDEyMjIwMVomWC1BbXotRXhwaXJlcz0zMDAmWC1BbXotU2lnbmF0dXJlPWUyYzc4OTUyYmJjY2ZhYzg1OWJlMWVlOTIwZGIwN2Q3YWU2ZDQzZTczNjY1OTExMDZjMDkyNDRjNzljNGFkYTYmWC1BbXotU2lnbmVkSGVhZGVycz1ob3N0JnJlc3BvbnNlLWNvbnRlbnQtdHlwZT12aWRlbyUyRm1wNCJ9.97tDpXYsfYuTlB_xowi3a9aGZ0_ivqhsxcXRUz8t9Rs" controls="controls"></video>

## Contributing

This project welcomes contributions and suggestions. Most contributions require you to agree to a Contributor License Agreement (CLA) declaring that you have the right to, and actually do, grant us the rights to use your contribution. For details, visit [https://cla.microsoft.com](https://cla.microsoft.com/).

When you submit a pull request, a CLA-bot will automatically determine whether you need to provide a CLA and decorate the PR appropriately (e.g., label, comment). Simply follow the instructions provided by the bot. You will only need to do this once across all repositories using our CLA.

This project has adopted the [Microsoft Open Source Code of Conduct](https://opensource.microsoft.com/codeofconduct/). For more information see the [Code of Conduct FAQ](https://opensource.microsoft.com/codeofconduct/faq/) or contact [opencode@microsoft.com](mailto:opencode@microsoft.com) with any additional questions or comments.

## Trademarks

This project may contain trademarks or logos for projects, products, or services. Authorized use of Microsoft trademarks or logos is subject to and must follow [Microsoft's Trademark & Brand Guidelines](https://www.microsoft.com/en-us/legal/intellectualproperty/trademarks/usage/general). Use of Microsoft trademarks or logos in modified versions of this project must not cause confusion or imply Microsoft sponsorship. Any use of third-party trademarks or logos are subject to those third-party's policies.
