"""Prompt data models and rendering utilities."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, root_validator, validator


class PromptVariable(BaseModel):
	"""Single variable required to render a prompt."""

	name: str = Field(..., description="Variable name (used in template)")
	description: Optional[str] = Field(
		None, description="Human-friendly description for UI/help"
	)
	required: bool = Field(True, description="Whether the variable is required")


class PromptTemplate(BaseModel):
	"""Prompt template with system and user parts."""

	name: str
	version: str = "1.0.0"
	system: str = Field(..., description="System prompt (role/instructions)")
	user: str = Field(..., description="User-facing prompt template")
	variables: List[PromptVariable] = Field(
		default_factory=list, description="Variables used in user template"
	)
	metadata: Dict[str, Any] = Field(default_factory=dict)

	@validator("variables", each_item=True)
	def ensure_unique_vars(cls, v, values):
		"""Ensure variable names are unique."""
		names = [var.name for var in values.get("variables", [])]
		if v.name in names:
			raise ValueError(f"Duplicate variable name: {v.name}")
		return v

	def render(self, data: Dict[str, Any]) -> "RenderedPrompt":
		"""Render the prompt using provided data.

		Args:
			data: Mapping of variable name -> value

		Returns:
			RenderedPrompt with filled text
		"""

		# Validate required variables
		missing = [var.name for var in self.variables if var.required and var.name not in data]
		if missing:
			raise ValueError(f"Missing variables: {', '.join(missing)}")

		# Simple str.format rendering; could be swapped to jinja if needed
		try:
			rendered_user = self.user.format(**data)
		except KeyError as exc:
			raise ValueError(f"Missing variable in data: {exc}") from exc

		return RenderedPrompt(
			system=self.system,
			user=rendered_user,
			variables=data,
			template_version=self.version,
			template_name=self.name,
		)


class RenderedPrompt(BaseModel):
	"""Rendered prompt ready for LLM invocation."""

	system: str
	user: str
	variables: Dict[str, Any]
	template_version: str
	template_name: str

	def to_messages(self) -> List[Dict[str, str]]:
		"""Return list of messages for chat completion API."""
		return [
			{"role": "system", "content": self.system},
			{"role": "user", "content": self.user},
		]
