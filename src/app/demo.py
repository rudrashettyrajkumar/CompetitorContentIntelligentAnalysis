"""End-to-end demo entrypoint (`make demo`).

EPIC-01 ships the skeleton only; EPIC-02+ extend this to run the full pipeline on the
sample Excel with mock data.
"""

from app.config.settings import PROMPTS_DIR, get_models_config, get_settings
from app.core.logging import configure_logging, get_logger
from app.core.model_router import ModelRouter
from app.core.prompt_registry import PromptRegistry
from app.db.engine import build_engine, init_db
from app.schemas import EchoResult


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, json_output=False)
    log = get_logger("demo")

    engine = build_engine(settings.database_url)
    init_db(engine)
    log.info("db_ready", url=settings.database_url)

    registry = PromptRegistry(PROMPTS_DIR)
    log.info("prompts_loaded", prompts=registry.names())

    router = ModelRouter(settings, get_models_config())
    if router.use_fake:
        router.fake_llm.register(EchoResult, {"message": "pipeline wiring works", "language": "en"})
    rendered = registry.render("echo", message="pipeline wiring works", language="English")
    result = router.invoke(
        tier=rendered.meta.model_tier,
        system=rendered.system,
        user=rendered.user,
        schema=rendered.schema,
        temperature=rendered.meta.temperature,
        prompt_name=rendered.meta.name,
        prompt_version=rendered.meta.version,
    )
    log.info("demo_complete", echo=result.model_dump())
    print("EPIC-01 foundation demo OK:", result.model_dump())


if __name__ == "__main__":
    main()
