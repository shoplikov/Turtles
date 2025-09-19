from fastapi import FastAPI

from app.api.routers.tasks import router as tasks_router


def create_app() -> FastAPI:
    app = FastAPI(title="Jira Task Creator API")

    app.include_router(tasks_router)

    @app.get("/")
    async def root():
        return {
            "message": "Jira Task Creator API",
            "endpoints": {
                "/create-jira-task": "POST - Create a Jira task from natural language instruction",
                "/docs": "GET - API documentation",
            },
        }

    @app.get("/health")
    async def health_check():
        return {"status": "healthy"}

    return app


app = create_app()


