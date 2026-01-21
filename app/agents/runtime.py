"""Agent runtime for executing prompts with LLM."""
from __future__ import annotations

import logging
import json
import base64
import os
from pathlib import Path
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
		# Default client for backward compatibility
		if not settings.openai_api_key:
			logger.warning("OpenAI API key is not configured")
		self.default_client = AsyncOpenAI(api_key=settings.openai_api_key)
		self.default_model = settings.openai_model
		self.default_temperature = settings.openai_temperature
		self.default_max_tokens = settings.openai_max_tokens
	
	def _get_client_for_agent(self, agent: Agent) -> AsyncOpenAI:
		"""Get OpenAI-compatible client configured for the agent's LLM model."""
		if not agent.llm_model:
			logger.warning(f"Agent {agent.id} has no LLM model, using default client")
			return self.default_client
		
		llm_model = agent.llm_model
		
		if not llm_model.is_active:
			raise ValueError(f"LLM model '{llm_model.name}' is not active")
		
		# Support multiple providers
		if llm_model.provider == "openai":
			return AsyncOpenAI(
				api_key=llm_model.api_key,
				base_url=llm_model.api_base_url if llm_model.api_base_url else None
			)
		elif llm_model.provider == "google":
			# Google Gemini uses OpenAI-compatible API
			return AsyncOpenAI(
				api_key=llm_model.api_key,
				base_url=llm_model.api_base_url or "https://generativelanguage.googleapis.com/v1beta/openai/"
			)
		else:
			raise ValueError(f"Provider '{llm_model.provider}' is not supported yet. Supported: openai, google")

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
	
	def _load_image_as_base64(self, image_path: str) -> Optional[str]:
		"""
		Load image from file system and convert to base64 data URL.
		
		Args:
			image_path: Path to image file relative to media directory
			
		Returns:
			Base64 data URL or None if file doesn't exist
		"""
		try:
			# Construct full path
			media_dir = Path(settings.base_dir) / "media"
			full_path = media_dir / image_path
			
			if not full_path.exists():
				logger.warning(f"Image file not found: {full_path}")
				return None
			
			# Read file and encode to base64
			with open(full_path, "rb") as image_file:
				image_data = image_file.read()
				base64_image = base64.b64encode(image_data).decode('utf-8')
			
			# Determine MIME type from extension
			extension = full_path.suffix.lower()
			mime_types = {
				'.jpg': 'image/jpeg',
				'.jpeg': 'image/jpeg',
				'.png': 'image/png',
				'.gif': 'image/gif',
				'.webp': 'image/webp'
			}
			mime_type = mime_types.get(extension, 'image/jpeg')
			
			return f"data:{mime_type};base64,{base64_image}"
		except Exception as e:
			logger.error(f"Error loading image {image_path}: {e}")
			return None
	
	def _build_messages_with_image(
		self, 
		prompt: RenderedPrompt, 
		image_data_url: str
	) -> List[Dict[str, Any]]:
		"""
		Build messages array with image support for vision models.
		
		Args:
			prompt: Rendered prompt
			image_data_url: Base64 data URL of the image
			
		Returns:
			Messages array with image content
		"""
		messages = []
		
		# Add system message if present
		for msg in prompt.to_messages():
			if msg["role"] == "system":
				messages.append(msg)
			elif msg["role"] == "user":
				# Transform user message to include image
				messages.append({
					"role": "user",
					"content": [
						{
							"type": "text",
							"text": msg["content"]
						},
						{
							"type": "image_url",
							"image_url": {
								"url": image_data_url
							}
						}
					]
				})
			else:
				messages.append(msg)
		
		return messages

	async def run(
		self,
		agent: Agent,
		variables: Dict[str, Any],
		prompt_version: Optional[PromptVersion] = None,
		stream: bool = False,
	) -> Any:
		"""Run agent and return completion or async generator when streaming."""
		prompt = await self._build_prompt(agent, variables, prompt_version)
		
		# Get client and model config from agent's LLM model
		client = self._get_client_for_agent(agent)
		model_name = agent.llm_model.name if agent.llm_model else self.default_model
		temperature = agent.temperature
		max_tokens = min(
			agent.max_tokens,
			agent.llm_model.max_tokens_limit if agent.llm_model else self.default_max_tokens
		)
		
		# Check if image is provided
		image_path = variables.get("image_path")
		image_data_url = None
		if image_path:
			image_data_url = self._load_image_as_base64(image_path)
			if not image_data_url:
				logger.warning(f"Failed to load image: {image_path}, continuing without image")

		if stream:
			return self._stream_completion(
				prompt, client, model_name, temperature, max_tokens, image_data_url
			)
		return await self._completion(
			prompt, client, model_name, temperature, max_tokens, image_data_url
		)

	async def _completion(
		self, 
		prompt: RenderedPrompt,
		client: AsyncOpenAI,
		model: str,
		temperature: float,
		max_tokens: int,
		image_data_url: Optional[str] = None
	) -> tuple[str, dict]:
		"""Non-streaming completion with usage metadata."""
		logger.debug(f"Sending completion request to {model}")
		
		# Build messages with or without image
		if image_data_url:
			messages = self._build_messages_with_image(prompt, image_data_url)
		else:
			messages = prompt.to_messages()
		
		response = await client.chat.completions.create(
			model=model,
			temperature=temperature,
			max_tokens=max_tokens,
			messages=messages,
		)
		usage = response.usage or None
		usage_info = {
			"prompt_tokens": usage.prompt_tokens if usage else 0,
			"completion_tokens": usage.completion_tokens if usage else 0,
			"total_tokens": usage.total_tokens if usage else 0,
		}
		return (response.choices[0].message.content or "", usage_info)

	async def _stream_completion(
		self, 
		prompt: RenderedPrompt,
		client: AsyncOpenAI,
		model: str,
		temperature: float,
		max_tokens: int,
		image_data_url: Optional[str] = None
	) -> AsyncGenerator[str, None]:
		"""Streaming completion generator."""
		logger.debug(f"Sending streaming completion request to {model}")
		
		# Build messages with or without image
		if image_data_url:
			messages = self._build_messages_with_image(prompt, image_data_url)
		else:
			messages = prompt.to_messages()
		
		stream = await client.chat.completions.create(
			model=model,
			temperature=temperature,
			max_tokens=max_tokens,
			messages=messages,
			stream=True,
		)
		async for chunk in stream:
			delta = chunk.choices[0].delta.content or ""
			if delta:
				yield delta


# Global runtime instance
agent_runtime = AgentRuntime()
