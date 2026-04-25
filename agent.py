import os
from dotenv import load_dotenv
from strands import Agent, tool
from strands.models.litellm import LiteLLMModel

load_dotenv()

model = LiteLLMModel(
    model_id="openrouter/tencent/hy3-preview:free",
    api_base="https://openrouter.ai/api/v1",
    api_key=os.environ["OPENROUTER_API_KEY"],
)


@tool
def get_weather(city: str) -> str:
    """Return the current weather for a given city.

    Args:
        city: The name of the city to look up weather for.

    Returns:
        A string describing the current weather conditions.
    """
    return f"The weather in {city} is 72°F and sunny."


agent = Agent(
    model=model,
    system_prompt="You are a helpful assistant. Use your tools to answer questions about the world.",
    tools=[get_weather],
)

if __name__ == "__main__":
    response = agent("What's the weather like in New York?")
    print(response)
