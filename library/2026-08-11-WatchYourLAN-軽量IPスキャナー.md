---
url: https://github.com/aceberg/WatchYourLAN
created: '2026-08-11T21:35:08'
type: article
tags:
- ネットワーク
- go
- docker
- 監視
summary: 'WatchYourLANはGo言語で書かれた軽量なネットワークIPスキャナーです。

  Web GUIを備え、新規ホストの検知通知やオンライン履歴のモニタリングが可能です。

  InfluxDBやPrometheusと連携し、Grafanaでのダッシュボード構築にも対応しています。'
title: 'aceberg/WatchYourLAN: Lightweight network IP scanner written in Go. With notifications, history, export to Grafana'
read: false
---

# aceberg/WatchYourLAN: Lightweight network IP scanner written in Go. With notifications, history, export to Grafana
2026-08-11
## WatchYourLAN

[![Docker](https://github.com/aceberg/WatchYourLAN/actions/workflows/main-docker-all.yml/badge.svg)](https://github.com/aceberg/WatchYourLAN/actions/workflows/main-docker-all.yml) [![Go Report Card](https://camo.githubusercontent.com/0a7df4c938d66f012843f6868453434ae4ab5fec2c682c2163b24faec5e09d4d/68747470733a2f2f676f7265706f7274636172642e636f6d2f62616467652f6769746875622e636f6d2f616365626572672f5761746368596f75724c414e)](https://goreportcard.com/report/github.com/aceberg/WatchYourLAN) [![Docker Image Size (latest semver)](https://camo.githubusercontent.com/ad8e4802521229fcc890bd086820c0bf031ef428caf4b83b62e59c9561a8e4dd/68747470733a2f2f696d672e736869656c64732e696f2f646f636b65722f696d6167652d73697a652f616365626572672f7761746368796f75726c616e)](https://hub.docker.com/r/aceberg/watchyourlan) [![GitHub Discussions](https://camo.githubusercontent.com/75bfc26845f641ed00b27834c29f6ed26391159191abaed7db9b561024a5e4cd/68747470733a2f2f696d672e736869656c64732e696f2f6769746875622f64697363757373696f6e732f616365626572672f5761746368596f75724c414e)](https://github.com/aceberg/WatchYourLAN/discussions)

[![aceberg%2FWatchYourLAN | Trendshift](https://camo.githubusercontent.com/de0005371021e45b5401ced2bacd7eb7c73b8d7231c7154ec1d48752662b0d3d/68747470733a2f2f7472656e6473686966742e696f2f6170692f62616467652f7265706f7369746f726965732f3131363432)](https://trendshift.io/repositories/11642)

Lightweight network IP scanner with web GUI. Features:

- Send notification when new host is found
- Monitor hosts online/offline history
- Keep a list of all hosts in the network
- Send data to `InfluxDB2` or `Prometheus` to make a `Grafana` dashboard

> [!important] Important
> Please, consider making a [donation](https://github.com/aceberg#donate). Even $10 will make a difference to me.

[![Screenshot_1](https://raw.githubusercontent.com/aceberg/WatchYourLAN/main/assets/Screenshot_1.png)](https://raw.githubusercontent.com/aceberg/WatchYourLAN/main/assets/Screenshot_1.png)

## More screenshots

Expand

[![Screenshot_5](https://raw.githubusercontent.com/aceberg/WatchYourLAN/main/assets/Screenshot_5.png)](https://raw.githubusercontent.com/aceberg/WatchYourLAN/main/assets/Screenshot_5.png)  
[![Screenshot_2](https://raw.githubusercontent.com/aceberg/WatchYourLAN/main/assets/Screenshot_2.png)](https://raw.githubusercontent.com/aceberg/WatchYourLAN/main/assets/Screenshot_2.png)  
[![Screenshot_3](https://raw.githubusercontent.com/aceberg/WatchYourLAN/main/assets/Screenshot_3.png)](https://raw.githubusercontent.com/aceberg/WatchYourLAN/main/assets/Screenshot_3.png)  
[![Screenshot_4](https://raw.githubusercontent.com/aceberg/WatchYourLAN/main/assets/Screenshot_4.png)](https://raw.githubusercontent.com/aceberg/WatchYourLAN/main/assets/Screenshot_4.png)

## Quick start

Expand

Replace `$YOURTIMEZONE` with correct time zone and `$YOURIFACE` with network interface you want to scan. Network mode must be `host`. Set `$DOCKERDATAPATH` for container to save data:

```
docker run --name wyl \
    -e "IFACES=$YOURIFACE" \
    -e "TZ=$YOURTIMEZONE" \
    --network="host" \
    -v $DOCKERDATAPATH/wyl:/data/WatchYourLAN \
    aceberg/watchyourlan
```

Web GUI should be at [http://localhost:8840](http://localhost:8840/)

## Auth

Expand

**WatchYourLAN** does not have built-in auth option. But you can use it with SSO tools like Authelia, or my simple auth app [ForAuth](https://github.com/aceberg/ForAuth).  
Here is an example [docker-compose-auth.yml](https://github.com/aceberg/WatchYourLAN/blob/main/docker-compose-auth.yml).

> ⚠️
> 
> **WARNING!**  
> Please, don't forget that WYL needs `host` network mode to work. So, WYL port will be exposed in this setup. You need to limit access to it with firewall or other measures.

## Install on Linux

Expand

All binary packages can be found in [latest](https://github.com/aceberg/WatchYourLAN/releases/latest) release. There are `.deb`, `.rpm`, `.apk` (Alpine Linux) and `.tar.gz` files.

Supported architectures: `amd64`, `i386`, `arm_v5`, `arm_v6`, `arm_v7`, `arm64`.  
Dependencies: `arp-scan`, `tzdata`.

For `amd64` there is a `deb` repo [available](https://github.com/aceberg/ppa)

## Config

Expand

Configuration can be done through config file, GUI or environment variables. Variable names is `config_v2.yaml` file are the same, but in lowcase.

### Basic config

| Variable | Description | Default |
| --- | --- | --- |
| TZ | Set your timezone for correct time |  |
| HOST | Listen address | 0.0.0.0 |
| PORT | Port for web GUI | 8840 |
| THEME | Any theme name from [https://bootswatch.com](https://bootswatch.com/) in lowcase or [additional](https://github.com/aceberg/aceberg-bootswatch-fork) | sand |
| COLOR | Background color: light or dark | dark |
| NODEPATH | Path to local node modules |  |
| SHOUTRRR\_URL | WatchYourLAN uses [Shoutrrr](https://github.com/nicholas-fedor/shoutrrr) to send notifications. It is already integrated, just needs a correct URL. Examples for Discord, Email, Gotify, Matrix, Ntfy, Pushover, Slack, Telegram, Generic Webhook and etc are [here](https://nicholas-fedor.github.io/shoutrrr/) |  |

### Scan settings

| Variable | Description | Default |
| --- | --- | --- |
| IFACES | Interfaces to scan. Could be one or more, separated by space. See [docs/VLAN\_ARP\_SCAN.md](https://github.com/aceberg/WatchYourLAN/blob/main/docs/VLAN_ARP_SCAN.md). |  |
| TIMEOUT | Time between scans (seconds) | 120 |
| ARP\_ARGS | Arguments for `arp-scan`. Enable `debug` log level to see resulting command. (Example: `-r 1`). See [docs/VLAN\_ARP\_SCAN.md](https://github.com/aceberg/WatchYourLAN/blob/main/docs/VLAN_ARP_SCAN.md). |  |
| ARP\_STRS ARP\_STRS\_JOINED | See [docs/VLAN\_ARP\_SCAN.md](https://github.com/aceberg/WatchYourLAN/blob/main/docs/VLAN_ARP_SCAN.md). |  |
| LOG\_LEVEL | Log level: `debug`, `info`, `warn` or `error` | info |
| TRIM\_HIST | Remove history after (hours) | 48 |
| HIST\_IN\_DB | DEPRECATED since 2.1.3. Now History is always stored in DB. Use TRIM\_HIST to reduce DB size |  |
| USE\_DB | Either `sqlite` or `postgres` | sqlite |
| PG\_CONNECT | Address to connect to PostgreSQL. (Example: `postgres://username:password@192.168.0.1:5432/dbname?sslmode=disable`). Full list of URL parameters [here](https://pkg.go.dev/github.com/lib/pq#hdr-Connection_String_Parameters) |  |

### InfluxDB2 config

This config matches Grafana's config for InfluxDB data source

| Variable | Description | Default | Example |
| --- | --- | --- | --- |
| INFLUX\_ENABLE | Enable export to InfluxDB2 | false | true |
| INFLUX\_SKIP\_TLS | Skip TLS Verify | false | true |
| INFLUX\_ADDR | Address:port of InfluxDB2 server |  | [https://192.168.2.3:8086/](https://192.168.2.3:8086/) |
| INFLUX\_BUCKET | InfluxDB2 bucket |  | test |
| INFLUX\_ORG | InfluxDB2 org |  | home |
| INFLUX\_TOKEN | Secret token, generated by InfluxDB2 |  |  |

### Prometheus config

This config configures the Prometheus data source

| Variable | Description | Default | Example |
| --- | --- | --- | --- |
| PROMETHEUS\_ENABLE | Enable the Prometheus `/metrics` endpoint | false | true |

## Config file

Expand

Config file name is `config_v2.yaml`. Example:

```
arp_args: ""
color: dark
host: 0.0.0.0
ifaces: enp4s0
influx_addr: ""
influx_bucket: ""
influx_enable: false
influx_org: ""
influx_skip_tls: false
influx_token: ""
log_level: info
nodepath: ""
pg_connect: ""
port: "8840"
prometheus_enable: false
shoutrrr_url: "gotify://192.168.0.1:8083/AwQqpAae.rrl5Ob/?title=Unknown host detected&DisableTLS=yes"
theme: sand
timeout: 60
trim_hist: 48
use_db: sqlite
```

## Options

Expand

| Key | Description | Default |
| --- | --- | --- |
| \-d | Path to config dir | /data/WatchYourLAN |
| \-n | Path to node modules (see below) |  |

## Local network only

Expand

By default, this app pulls themes, icons and fonts from the internet. But, in some cases, it may be useful to have an independent from global network setup. I created a separate [image](https://github.com/aceberg/my-dockerfiles/tree/main/node-bootstrap) with all necessary modules and fonts. Run with Docker:

```
docker run --name node-bootstrap          \
    -p 8850:8850                          \
    aceberg/node-bootstrap
```
```
docker run --name wyl \
    -e "IFACES=$YOURIFACE" \
    -e "TZ=$YOURTIMEZONE" \
    --network="host" \
    -v $DOCKERDATAPATH/wyl:/data/WatchYourLAN \
    aceberg/watchyourlan -n "http://$YOUR_IP:8850"
```

Or use [docker-compose](https://github.com/aceberg/WatchYourLAN/blob/main/docker-compose.yml)

## API & Integrations

Expand

### API

Moved to [docs/API.md](https://github.com/aceberg/WatchYourLAN/blob/main/docs/API.md)

### Integrations

- [ArchLinux (AUR)](https://aur.archlinux.org/packages/watch-your-lan) by `gilcu3`
- [Python API client](https://github.com/drwahl/py-watchyourlanclient) by [drwahl](https://github.com/drwahl)
- [Umbrel](https://apps.umbrel.com/app/watch-your-lan) by [Jasper](https://github.com/ceramicwhite)
- [YunoHost](https://apps.yunohost.org/app/watchyourlan)

## Thanks

Expand
- All go packages listed in [dependencies](https://github.com/aceberg/WatchYourLAN/network/dependencies)
- Favicon and logo: [Access point icons created by Freepik - Flaticon](https://www.flaticon.com/free-icons/access-point)
- [Bootstrap](https://getbootstrap.com/)
- Themes: [Free themes for Bootstrap](https://bootswatch.com/)
