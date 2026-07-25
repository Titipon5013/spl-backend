from dotenv import load_dotenv
load_dotenv()
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from routes.login_controller import login_router
from routes.parking_controller import router as parking_router
from routes.register_controller import register_router
from routes.request_controller import request_router
from routes.plate_controller import router as plate_router
from routes.admin_controller import router as user_router
from routes.entry_record_controller import router as entry_record_router
from routes.analytics_controller import router as analytics_router
from routes.webhook_controller import router as webhook_router
from routes.oauth_controller import router as oauth_router
from routes.admin_access_controller import router as admin_access_router
from routes.report_controller import router as report_router

# 👇 1. เพิ่มการ Import camera_event_controller จากโฟลเดอร์ routes
from routes.camera_event_controller import router as camera_event_router

from services.report_scheduler import start_report_scheduler, stop_report_scheduler

# 👇 Feature 2: MCP Server สำหรับให้ AI agent เรียกใช้ข้อมูลลานจอด
from mcp_server.server import create_http_app, http_transport_enabled, mcp_lifespan

from mqtt.client import mqttClient
import os


BROKER_HOST = os.getenv("MQTT_BROKER_HOST", default="localhost")
MQTT_USER = os.getenv("MQTT_USER")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD")
mqtt_client = mqttClient()

@asynccontextmanager
async def lifespan(app: FastAPI):
    mqtt_client.start_mqtt()
    start_report_scheduler()

    if http_transport_enabled():
        # แอปที่ mount ไว้ไม่ได้รับ lifespan ของตัวเอง ต้องรัน session manager ที่นี่
        async with mcp_lifespan():
            yield
    else:
        yield

    stop_report_scheduler()
    mqtt_client.stop_mqtt()


app = FastAPI(lifespan=lifespan)

origins =[
    "http://localhost:8080",
    "http://localhost:5173",
    "http://10.41.11.21:9696"
    # "http://192.168.0.101:5173"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(login_router)
app.include_router(user_router)
app.include_router(parking_router)
app.include_router(register_router)
app.include_router(request_router)
app.include_router(plate_router)
app.include_router(entry_record_router)
app.include_router(analytics_router, prefix="/api/analytics", tags=["Analytics Dashboard"])
app.include_router(webhook_router, prefix="/webhook", tags=["LINE Chatbot"])
app.include_router(oauth_router)
app.include_router(admin_access_router)
app.include_router(report_router)

# 👇 2. ลงทะเบียน Router ใหม่เข้าสู่แอปพลิเคชัน
app.include_router(camera_event_router)

# 👇 3. Feature 2: เปิด MCP server ผ่าน HTTP ที่ /mcp (ต้องมี bearer token)
#    ส่วน Claude Desktop ให้ใช้ stdio ผ่าน `python -m mcp_server` แทน
if http_transport_enabled():
    app.mount("/mcp", create_http_app())