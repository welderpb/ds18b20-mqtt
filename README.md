# ds18b20-mqtt

Reads the temperature from a DS18B20 (1-Wire) sensor and publishes it to
MQTT, with automatic Home Assistant MQTT Discovery.

## Host requirements

The DS18B20 sensor connects via 1-Wire and must be visible under
`/sys/bus/w1/devices` **before** starting the container:

```bash
sudo modprobe w1-gpio
sudo modprobe w1-therm
ls /sys/bus/w1/devices   # should show a folder like 28-xxxxxxxxxxxx
```

On Raspberry Pi OS, 1-Wire is usually enabled via `raspi-config`
(Interface Options → 1-Wire) or by adding `dtoverlay=w1-gpio` to
`/boot/config.txt`.

## Run with Docker Compose (recommended)

1. Edit `docker-compose.yml` — at minimum set `MQTT_HOST` and, if
   needed, `MQTT_USERNAME`/`MQTT_PASSWORD`.
2. Build and start:

```bash
docker compose up -d --build
```

3. Logs:

```bash
docker compose logs -f
```

## Run with Docker (without Compose)

```bash
docker build -t ds18b20-mqtt .

docker run -d \
  --name ds18b20-mqtt \
  --restart unless-stopped \
  --privileged \
  -v /sys/bus/w1/devices:/sys/bus/w1/devices:ro \
  -e MQTT_HOST=192.168.1.10 \
  -e MQTT_USERNAME=myuser \
  -e MQTT_PASSWORD=mypassword \
  -e SENSOR_NAME=external \
  ds18b20-mqtt
```

`--privileged` is used to reliably guarantee the container can read
`/sys/bus/w1/devices` on the host.

## Run with Podman (`podman play kube`)

`ds18b20-mqtt-pod.yaml` is a Kubernetes-style Pod manifest that can be
run directly with Podman, without Compose:

```bash
podman build -t localhost/ds18b20-mqtt:latest .

# edit ds18b20-mqtt-pod.yaml first (MQTT_HOST, credentials, etc.)
podman play kube ds18b20-mqtt-pod.yaml
```

Logs:

```bash
podman pod logs -f ds18b20-mqtt
```

Stop and remove the pod:

```bash
podman play kube --down ds18b20-mqtt-pod.yaml
```

## Run locally without Docker

```bash
pip install -r requirements.txt
export MQTT_HOST=192.168.1.10
python3 ds18b20_mqtt.py
```

## Environment variables

| Variable                 | Default                     | Description                                                              |
|---------------------------|------------------------------|----------------------------------------------------------------------------|
| `MQTT_HOST`               | `127.0.0.1`                 | MQTT broker address                                                       |
| `MQTT_PORT`               | `1883`                      | MQTT broker port                                                          |
| `MQTT_USERNAME`           | —                            | Username for broker authentication (optional)                            |
| `MQTT_PASSWORD`           | —                            | Password for broker authentication (optional)                            |
| `MQTT_CLIENT_ID`          | `ds18b20-mqtt`              | MQTT client id                                                            |
| `MQTT_TLS`                | `false`                     | Enable TLS for the broker connection (`true`/`false`)                    |
| `MQTT_QOS`                | `1`                         | QoS used when publishing temperature readings                            |
| `MQTT_KEEPALIVE`          | `60`                        | MQTT connection keepalive interval, seconds                              |
| `SENSOR_ID`               | —                            | ID of a specific sensor (if several are on the bus); otherwise the first one found is used |
| `SENSOR_NAME`             | `external`                 | Sensor name — used in topics and in Home Assistant                       |
| `SENSOR_UNIT`             | `C`                         | Measurement unit: `C` or `F`                                             |
| `INTERVAL`                | `30`                        | Publishing interval, seconds                                             |
| `STATE_TOPIC`             | `DS18B20/<SENSOR_NAME>/temp` | Topic the temperature readings are published to                         |
| `HASS_DISCOVERY`          | `true`                      | Publish the Home Assistant discovery config (`true`/`false`)             |
| `HASS_DISCOVERY_PREFIX`   | `homeassistant`             | Home Assistant discovery topic prefix                                    |
| `LOG_LEVEL`               | `INFO`                      | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`)                      |

## Shutdown

The process shuts down gracefully on `SIGTERM`/`SIGINT` (including on
`docker stop` / `docker compose down`) — it disconnects from the broker
before exiting.
