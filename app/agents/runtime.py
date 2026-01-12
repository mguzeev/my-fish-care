"""Agent runtime for executing prompts with LLM."""
from __future__ import annotations

import logging
import json
from typing import Any, AsyncGenerator, Dict, List, Optional
from openai import AsyncOpenAI
from app.core.config import settings
from app.prompts.models import PromptTemplate, PromptVariable, RenderedPrompt
from app.models.agent import Agent
from app.models.prompt import PromptVersion


logger = logging.getLogger(__name__)


class AgentRuntime:
	"""Runtime to execute agents using LLM provider."""

	def __init__(self):
		if not settings.openai_api_key:
			logger.warning("OpenAI API key is not configured")
		self.client = AsyncOpenAI(api_key=settings.openai_api_key)
		self.model = settings.openai_model
		self.temperature = settings.openai_temperature
		self.max_tokens = settings.openai_max_tokens

	async def _build_prompt(
		self,
		agent: Agent,
		variables: Dict[str, Any],
		prompt_version: Optional[PromptVersion] = None,
	) -> RenderedPrompt:
		"""Render prompt for the given agent using DB-stored version if provided."""

		if prompt_version:
			template = PromptTemplate(
				name=prompt_version.name,
				version=prompt_version.version,
				system=prompt_version.system_prompt,
				user=prompt_version.user_template,
				variables=self._load_variables(prompt_version),
			)
		else:
			template = PromptTemplate(
				name=agent.name,
				version=agent.version or "1.0.0",
				system=agent.system_prompt,
				user=agent.prompt_template or "{input}",
				variables=[
					PromptVariable(name="input", required=True, description="User message"),
				],
			)

		return template.render(variables)

	def _load_variables(self, prompt_version: PromptVersion) -> List[PromptVariable]:
		"""Deserialize variables JSON into PromptVariable list with fallback."""
		try:
			variables_data = json.loads(prompt_version.variables_json or "[]")
		except json.JSONDecodeError:
			variables_data = []

		variables: List[PromptVariable] = []
		for item in variables_data:
			if not isinstance(item, dict) or "name" not in item:
				continue
			variables.append(
				PromptVariable(
					name=item.get("name"),
					description=item.get("description"),
					required=bool(item.get("required", True)),
				)
			)

		if not any(var.name == "input" for var in variables):
			variables.append(PromptVariable(name="input", required=True, description="User message"))

		return variables

	async def run(
		self,
		agent: Agent,
		variables: Dict[str, Any],
		prompt_version: Optional[PromptVersion] = None,
		stream: bool = False,
	) -> Any:
		"""Run agent and return completion or async generator when streaming."""
		prompt = await self._build_prompt(agent, variables, prompt_version)

		if stream:
			return self._stream_completion(prompt)
		return await self._completion(prompt)

	async def _completion(self, prompt: RenderedPrompt) -> str:
		"""Non-streaming completion."""
		logger.debug("Sending completion request to OpenAI")
		response = await self.client.chat.completions.create(
			model=self.model,
			temperature=self.temperature,
			max_tokens=self.max_tokens,
			messages=prompt.to_messages(),
		)
		return response.choices[0].message.content or ""

	async def _stream_completion(
		self, prompt: RenderedPrompt
	) -> AsyncGenerator[str, None]:
		"""Streaming completion generator."""
		logger.debug("Sending streaming completion request to OpenAI")
		stream = await self.client.chat.completions.create(
			model=self.model,
			temperature=self.temperature,
			max_tokens=self.max_tokens,
			messages=prompt.to_messages(),
			stream=True,
		)
		async for chunk in stream:
			delta = chunk.choices[0].delta.content or ""
			if delta:
				yield delta


# Global runtime instance
agent_runtime = AgentRuntime()
