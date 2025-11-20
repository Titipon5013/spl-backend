import os
from dotenv import load_dotenv
import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion
from . import handler

load_dotenv()

MQTT_USER = os.getenv("MQTT_USER")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD")
MQTT_HOST = os.getenv("MQTT_BROKER_HOST", "localhost")
client_id = os.getenv("MQTT_CLIENT")

class mqttClient:
    def __init__(self):
        self.mqtt_client = mqtt.Client(
            callback_api_version=CallbackAPIVersion.VERSION2,
            client_id=client_id,
            clean_session=True
        )
        self.mqtt_client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
        self.mqtt_client.tls_set()
        self.mqtt_client.on_connect = handler.on_connect
        self.mqtt_client.on_message = handler.on_message
    
    def start_mqtt(self):
        try:
            print("Starting mqtt...")
            self.mqtt_client.connect(
                host=MQTT_HOST,
                port=8883,
            )
            self.mqtt_client.loop_start()
        except Exception as e:
            print(f"Unexpected Error occured: {e}")


    def stop_mqtt(self):
        print("Stopping mqtt")
        self.mqtt_client.loop_stop()
        self.mqtt_client.disconnect()
