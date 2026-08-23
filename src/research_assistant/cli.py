from pathlib import Path

import typer

from research_assistant.tracing.recorder import RunRecorder
from research_assistant.variants import VARIANT_REGISTRY, Variant

app = typer.Typer()


@app.command()
def run(
    topic: str,
    variant: Variant = Variant.pipeline,
    output: Path | None = None,
) -> None:
    """Run one research variant on a topic and print/save the brief."""
    recorder = RunRecorder(variant=variant.value, topic=topic)
    run_fn = VARIANT_REGISTRY[variant]
    brief = run_fn(topic, recorder)

    if output:
        output.write_text(brief.markdown, encoding="utf-8")
        typer.echo(f"Brief written to {output}")
    else:
        typer.echo(brief.markdown)


@app.command()
def serve(port: int = 8000) -> None:
    """Run the web backend locally (binds to 127.0.0.1 only)."""
    import uvicorn

    uvicorn.run("research_assistant.web.app:app", host="127.0.0.1", port=port)


if __name__ == "__main__":
    app()
