from app.api.routes.anomalies_route import router as anomaly_router
from app.api.routes.health_route import router as health_router
from app.api.routes.query_route import router as query_router
from fastapi import FastAPI

app = FastAPI(title="Support Ticket Analytics API", version="1.0.0")

app.include_router(anomaly_router)
app.include_router(health_router)
app.include_router(query_router)


@app.get("/")
def home():
    return {"message":"Backend Running successfully !"}



















