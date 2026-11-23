import mimetypes
import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from server.routes import orders, whoami

app = FastAPI(title="Order Intake Review")

app.include_router(orders.router, prefix="/api")
app.include_router(whoami.router, prefix="/api")


@app.get("/api/health")
def health():
    return {"status": "ok"}


# pdf.js runs its (bundled) worker as an ES module: browsers require a JavaScript MIME type for it, and older
# Python mimetypes tables don't know .mjs.
mimetypes.add_type("text/javascript", ".mjs")

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "frontend", "dist")

if os.path.exists(FRONTEND_DIR):
    app.mount(
        "/assets",
        StaticFiles(directory=os.path.join(FRONTEND_DIR, "assets")),
        name="assets",
    )

    @app.get("/{full_path:path}")
    def serve_spa(full_path: str):
        if full_path.startswith("api/"):
            return {"error": "not found"}
        candidate = os.path.join(FRONTEND_DIR, full_path)
        if full_path and os.path.isfile(candidate):
            return FileResponse(candidate)
        return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))
