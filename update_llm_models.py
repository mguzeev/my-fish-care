"""
Update LLM models with correct pricing and vision support.

This script:
1. Updates Gemini pricing
2. Adds vision models (GPT-4 Vision, Gemini Vision)
3. Sets correct supports_text and supports_vision flags
"""
import asyncio
import sys
from decimal import Decimal

sys.path.insert(0, ".")

from app.core.database import AsyncSessionLocal
from app.models.llm_model import LLMModel
from sqlalchemy import select


async def update_models():
    """Update LLM models with pricing and vision support."""
    print("=" * 70)
    print("UPDATING LLM MODELS")
    print("=" * 70)
    
    async with AsyncSessionLocal() as db:
        # Get all existing models
        result = await db.execute(select(LLMModel))
        existing_models = {model.name: model for model in result.scalars().all()}
        
        print(f"\nFound {len(existing_models)} existing models")
        
        # Define model configurations
        model_configs = [
            # Text-only models
            {
                "name": "gpt-4",
                "provider": "openai",
                "cost_per_1k_input_tokens": Decimal("0.03"),
                "cost_per_1k_output_tokens": Decimal("0.06"),
                "supports_text": True,
                "supports_vision": False,
            },
            {
                "name": "gemini-2.0-flash-exp",
                "provider": "google",
                "cost_per_1k_input_tokens": Decimal("0.0"),  # Free tier
                "cost_per_1k_output_tokens": Decimal("0.0"),
                "supports_text": True,
                "supports_vision": False,
            },
            {
                "name": "gemini-2.5-flash",
                "provider": "google",
                "cost_per_1k_input_tokens": Decimal("0.00001875"),  # $0.0075 / 1M input = $0.00001875 / 1k
                "cost_per_1k_output_tokens": Decimal("0.00003"),     # $0.03 / 1M output = $0.00003 / 1k
                "supports_text": True,
                "supports_vision": False,
            },
            # Vision models
            {
                "name": "gpt-4-vision-preview",
                "provider": "openai",
                "cost_per_1k_input_tokens": Decimal("0.01"),
                "cost_per_1k_output_tokens": Decimal("0.03"),
                "supports_text": True,
                "supports_vision": True,
                "max_tokens_limit": 4096,
            },
            {
                "name": "gpt-4o",
                "provider": "openai",
                "cost_per_1k_input_tokens": Decimal("0.0025"),
                "cost_per_1k_output_tokens": Decimal("0.01"),
                "supports_text": True,
                "supports_vision": True,
                "max_tokens_limit": 16384,
            },
            {
                "name": "gemini-2.0-flash-thinking-exp",
                "provider": "google",
                "cost_per_1k_input_tokens": Decimal("0.0"),  # Free tier
                "cost_per_1k_output_tokens": Decimal("0.0"),
                "supports_text": True,
                "supports_vision": True,
            },
            {
                "name": "gemini-1.5-flash",
                "provider": "google",
                "cost_per_1k_input_tokens": Decimal("0.000075"),  # $0.075 / 1M
                "cost_per_1k_output_tokens": Decimal("0.0003"),   # $0.30 / 1M
                "supports_text": True,
                "supports_vision": True,
            },
            {
                "name": "gemini-1.5-pro",
                "provider": "google",
                "cost_per_1k_input_tokens": Decimal("0.00125"),   # $1.25 / 1M
                "cost_per_1k_output_tokens": Decimal("0.005"),    # $5.00 / 1M
                "supports_text": True,
                "supports_vision": True,
            },
        ]
        
        # Update or create models
        for config in model_configs:
            name = config["name"]
            if name in existing_models:
                # Update existing model
                model = existing_models[name]
                print(f"\n📝 Updating: {name}")
                for key, value in config.items():
                    if key != "name":
                        old_value = getattr(model, key, None)
                        if old_value != value:
                            setattr(model, key, value)
                            print(f"   {key}: {old_value} → {value}")
            else:
                # Create new model
                print(f"\n✨ Creating: {name}")
                model = LLMModel(
                    name=config["name"],
                    provider=config["provider"],
                    api_key_env_var=f"{config['provider'].upper()}_API_KEY",
                    model_name=config["name"],
                    cost_per_1k_input_tokens=config["cost_per_1k_input_tokens"],
                    cost_per_1k_output_tokens=config["cost_per_1k_output_tokens"],
                    supports_text=config.get("supports_text", True),
                    supports_vision=config.get("supports_vision", False),
                    max_tokens_limit=config.get("max_tokens_limit", 2048),
                )
                db.add(model)
                for key, value in config.items():
                    print(f"   {key}: {value}")
        
        # Commit changes
        await db.commit()
        
        print("\n" + "=" * 70)
        print("✅ MODELS UPDATED SUCCESSFULLY")
        print("=" * 70)
        
        # Show final state
        result = await db.execute(select(LLMModel).order_by(LLMModel.provider, LLMModel.name))
        all_models = result.scalars().all()
        
        print(f"\nTotal models: {len(all_models)}")
        print("\nText-only models:")
        for model in all_models:
            if model.supports_text and not model.supports_vision:
                print(f"  - {model.name} ({model.provider})")
        
        print("\nVision-capable models:")
        for model in all_models:
            if model.supports_vision:
                print(f"  - {model.name} ({model.provider})")


if __name__ == "__main__":
    asyncio.run(update_models())
