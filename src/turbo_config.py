"""
Writes MoneyPrinterTurbo's config.toml for one CI run, from environment
variables (GitHub secrets). Runs under MoneyPrinterTurbo's own virtualenv
python -- that env has the `toml` package MoneyPrinterTurbo itself reads its
config with, so what gets written here is exactly what it can parse.

Starts from the project's own config.example.toml (so every setting it
expects is present with its default) and only overrides what GRACE needs.

Usage: <mpt-venv>/bin/python turbo_config.py <path-to-MoneyPrinterTurbo>
"""
import os
import sys

import toml


def main():
    mpt_dir = sys.argv[1]
    with open(os.path.join(mpt_dir, "config.example.toml"), encoding="utf-8") as f:
        cfg = toml.load(f)

    cfg["log_level"] = "INFO"
    app = cfg.setdefault("app", {})

    def keys(env_name):
        return [k.strip() for k in os.environ.get(env_name, "").split(",") if k.strip()]

    app["pexels_api_keys"] = keys("PEXELS_API_KEY")
    app["pixabay_api_keys"] = keys("PIXABAY_API_KEY")
    app["video_source"] = os.environ.get("TURBO_VIDEO_SOURCE", "pexels")
    app["subtitle_provider"] = "edge"
    app["hide_config"] = True

    provider = os.environ.get("TURBO_LLM_PROVIDER", "")
    if provider:
        app["llm_provider"] = provider
        app[f"{provider}_api_key"] = os.environ.get("TURBO_LLM_KEY", "")
        model = os.environ.get("TURBO_LLM_MODEL", "")
        if model:
            app[f"{provider}_model_name"] = model

    out = os.path.join(mpt_dir, "config.toml")
    with open(out, "w", encoding="utf-8") as f:
        toml.dump(cfg, f)
    os.chmod(out, 0o600)
    print(f"wrote {out} (source={app['video_source']}, llm={provider or 'none'})")


if __name__ == "__main__":
    main()
