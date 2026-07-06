#!/usr/bin/env python3
"""Read a DS18B20 temperature sensor and publish readings to MQTT.

All configuration is provided via environment variables (see README/Dockerfile).
"""

import json
import logging
import os
import signal
import sys
import threading

import paho.mqtt.client as mqtt
from w1thermsensor import NoSensorFoundError, SensorNotReadyError, Unit, W1ThermSensor

LOGGER = logging.getLogger("ds18b20-mqtt")

UNITS = {"C": Unit.DEGREES_C, "F": Unit.DEGREES_F}


def _env(name, default=None):
    return os.environ.get(name, default)


def _env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _env_int(name, default):
    value = os.environ.get(name)
    return int(value) if value else default


def _env_float(name, default):
    value = os.environ.get(name)
    return float(value) if value else default


class Config:
    def __init__(self):
        self.mqtt_host = _env("MQTT_HOST", "127.0.0.1")
        self.mqtt_port = _env_int("MQTT_PORT", 1883)
        self.mqtt_username = _env("MQTT_USERNAME")
        self.mqtt_password = _env("MQTT_PASSWORD")
        self.mqtt_client_id = _env("MQTT_CLIENT_ID", "ds18b20-mqtt")
        self.mqtt_tls = _env_bool("MQTT_TLS", False)
        self.mqtt_qos = _env_int("MQTT_QOS", 1)
        self.mqtt_keepalive = _env_int("MQTT_KEEPALIVE", 60)

        self.sensor_id = _env("SENSOR_ID")  # optional; auto-detected if unset
        self.sensor_name = _env("SENSOR_NAME", "external")

        unit = _env("SENSOR_UNIT", "C").upper()
        if unit not in UNITS:
            raise ValueError(f"SENSOR_UNIT must be 'C' or 'F', got {unit!r}")
        self.unit_code = unit
        self.unit = UNITS[unit]

        self.interval = _env_float("INTERVAL", 30)

        self.state_topic = _env("STATE_TOPIC", f"DS18B20/{self.sensor_name}/temp")
        self.discovery_prefix = _env("HASS_DISCOVERY_PREFIX", "homeassistant")
        self.discovery_enabled = _env_bool("HASS_DISCOVERY", True)

        self.log_level = _env("LOG_LEVEL", "INFO").upper()


def build_discovery_payload(config, sensor_id):
    unit_symbol = "°C" if config.unit_code == "C" else "°F"
    return {
        "state_topic": config.state_topic,
        "icon": "hass:thermometer",
        "name": f"{config.sensor_name} Temperature",
        "unique_id": f"{sensor_id}_ds18b20_{config.sensor_name}_temp",
        "unit_of_measurement": unit_symbol,
        "state_class": "measurement",
        "device_class": "temperature",
        "device": {
            "identifiers": [config.sensor_name, sensor_id],
            "manufacturer": "Maxim Integrated",
            "model": "DS18B20",
            "name": config.sensor_name,
        },
    }


def create_sensor(config):
    try:
        if config.sensor_id:
            return W1ThermSensor(sensor_id=config.sensor_id)
        return W1ThermSensor()
    except NoSensorFoundError as exc:
        raise RuntimeError("No DS18B20 sensor found on the 1-Wire bus") from exc


class Publisher:
    def __init__(self, config, sensor_id):
        self.config = config
        self.sensor_id = sensor_id
        self.discovery_topic = f"{config.discovery_prefix}/sensor/DS18B20/{config.sensor_name}_temp/config"

        self.client = mqtt.Client(client_id=config.mqtt_client_id)
        if config.mqtt_username:
            self.client.username_pw_set(config.mqtt_username, config.mqtt_password)
        if config.mqtt_tls:
            self.client.tls_set()
        self.client.reconnect_delay_set(min_delay=1, max_delay=60)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect

    def _on_connect(self, client, userdata, flags, rc):
        if rc != 0:
            LOGGER.error("Failed to connect to MQTT broker: %s", mqtt.connack_string(rc))
            return
        LOGGER.info("Connected to MQTT broker %s:%s", self.config.mqtt_host, self.config.mqtt_port)
        self._publish_discovery()

    def _on_disconnect(self, client, userdata, rc):
        if rc != 0:
            LOGGER.warning("Unexpectedly disconnected from MQTT broker (rc=%s); will reconnect", rc)
        else:
            LOGGER.info("Disconnected from MQTT broker")

    def _publish_discovery(self):
        if not self.config.discovery_enabled:
            return
        payload = build_discovery_payload(self.config, self.sensor_id)
        self.client.publish(self.discovery_topic, json.dumps(payload), qos=0, retain=True)
        LOGGER.debug("Published discovery config to %s", self.discovery_topic)

    def start(self):
        LOGGER.info("Connecting to MQTT broker %s:%s", self.config.mqtt_host, self.config.mqtt_port)
        self.client.connect(self.config.mqtt_host, self.config.mqtt_port, self.config.mqtt_keepalive)
        self.client.loop_start()

    def stop(self):
        self.client.loop_stop()
        self.client.disconnect()

    def publish_temperature(self, temperature):
        result = self.client.publish(self.config.state_topic, f"{temperature:.1f}", qos=self.config.mqtt_qos)
        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            LOGGER.warning("Failed to publish temperature (rc=%s)", result.rc)


def main():
    config = Config()
    logging.basicConfig(
        level=getattr(logging, config.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    stop_event = threading.Event()

    def handle_signal(signum, frame):
        LOGGER.info("Received signal %s, shutting down", signal.Signals(signum).name)
        stop_event.set()

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    sensor = create_sensor(config)
    LOGGER.info("Using sensor %s", sensor.id)

    publisher = Publisher(config, sensor.id)
    publisher.start()

    LOGGER.info("Publishing every %.1fs to %s", config.interval, config.state_topic)

    while not stop_event.is_set():
        try:
            temperature = sensor.get_temperature(config.unit)
            LOGGER.info("Sensor %s temperature: %.2f%s", sensor.id, temperature, config.unit_code)
            publisher.publish_temperature(temperature)
        except SensorNotReadyError:
            LOGGER.warning("Sensor not ready, skipping this reading")
        except Exception:
            LOGGER.exception("Error while reading/publishing temperature")

        stop_event.wait(config.interval)

    publisher.stop()
    LOGGER.info("Shutdown complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
