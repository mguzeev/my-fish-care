# Admin Panel Vision/Text Configuration

## Overview
This feature adds the ability to configure which LLM models support text-only processing and which support vision (image processing) through the admin panel.

## Changes Made

### Backend (API)

#### 1. Admin Router Schemas (`app/admin/router.py`)
- **LLMModelResponse**: Added `supports_text` and `supports_vision` boolean fields
- **CreateLLMModelRequest**: Added `supports_text` (default: True) and `supports_vision` (default: False) fields
- **UpdateLLMModelRequest**: Added optional `supports_text` and `supports_vision` fields

#### 2. Admin Endpoints Updated
All LLM model management endpoints now handle the new fields:
- `GET /admin/llm-models` - List models with capabilities
- `GET /admin/llm-models/{model_id}` - Get model details including capabilities
- `POST /admin/llm-models` - Create model with capability flags
- `PUT /admin/llm-models/{model_id}` - Update model capabilities
- `DELETE /admin/llm-models/{model_id}` - Delete model (unchanged)

### Frontend (UI)

#### 1. Admin HTML Template (`app/templates/admin.html`)

**Create Modal:**
- Added "Supports Text" checkbox (ID: `llmModelSupportsText`, default: checked)
- Added "Supports Vision (Images)" checkbox (ID: `llmModelSupportsVision`, default: unchecked)

**Edit Modal:**
- Added "Supports Text" checkbox (ID: `editLLMModelSupportsText`)
- Added "Supports Vision (Images)" checkbox (ID: `editLLMModelSupportsVision`)

**LLM Models Table:**
- Added "Capabilities" column showing:
  - 📝 Text badge when `supports_text` is true
  - 🖼️ Vision badge when `supports_vision` is true
  - "None" badge when both are false

#### 2. JavaScript Functions Updated
- `createLLMModel()`: Now sends `supports_text` and `supports_vision` in request
- `editLLMModel()`: Loads and sets checkbox states from model data
- `saveLLMModelChanges()`: Includes capability fields in update request
- `loadLLMModels()`: Renders capability badges in table

### Testing

Created comprehensive test suite (`tests/test_admin_vision_config.py`):
1. ✅ `test_llm_model_has_vision_text_fields` - Verifies model has new fields
2. ✅ `test_llm_model_defaults` - Checks field values are set correctly
3. ✅ `test_admin_api_schema_structure` - Validates API schemas include fields
4. ✅ `test_create_request_defaults` - Confirms default values in create request
5. ✅ `test_html_template_fields` - Checks UI includes all necessary elements

**All 5 tests passing ✅**

## Usage

### Admin Panel Access
1. Navigate to Admin Panel → LLM Models tab
2. Click "+ Add Model" to create a new model
3. Configure model settings:
   - Check "Supports Text" if model can process text-only queries
   - Check "Supports Vision (Images)" if model can process images
4. Save the model

### Editing Existing Models
1. Click "Edit" on any LLM model in the table
2. Toggle the capability checkboxes as needed
3. Click "Save" to update

### Viewing Capabilities
The LLM Models table displays capabilities for each model:
- Models supporting text show 📝 Text badge
- Models supporting vision show 🖼️ Vision badge
- Models with no capabilities show "None"

## API Examples

### Create Model with Vision Support
```bash
POST /admin/llm-models
{
  "name": "gpt-4-vision",
  "display_name": "GPT-4 Vision",
  "provider": "openai",
  "api_key": "sk-...",
  "supports_text": true,
  "supports_vision": true
}
```

### Update Model Capabilities
```bash
PUT /admin/llm-models/1
{
  "supports_text": true,
  "supports_vision": false
}
```

### List Models (Response)
```json
[
  {
    "id": 1,
    "name": "gpt-4",
    "supports_text": true,
    "supports_vision": false,
    ...
  },
  {
    "id": 2,
    "name": "gpt-4-vision",
    "supports_text": true,
    "supports_vision": true,
    ...
  }
]
```

## Integration with Agent System

These capability flags are used by:
1. **Auto-agent selection** (`app/agents/router.py`): 
   - `_get_first_available_agent()` filters agents by model capabilities
   - When `image_path` is provided, only models with `supports_vision=True` are selected
   
2. **Agent Runtime** (`app/agents/runtime.py`):
   - Vision-enabled models receive multimodal messages with base64-encoded images
   - Text-only models receive standard text messages

## Database Schema

Fields added via migration `786fab8c175e_add_vision_support_fields`:
```python
supports_text: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
supports_vision: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
```

## Git Commits

This feature spans multiple commits:
1. Initial migration and database schema
2. Agent runtime and API updates
3. Web channel UI implementation
4. **Current**: Admin panel configuration (commit 9da8b4c)

## Future Enhancements

- [ ] Add bulk update for model capabilities
- [ ] Show capability requirements in agent creation UI
- [ ] Add filtering by capabilities in model list
- [ ] Display model compatibility warnings when assigning to agents
- [ ] Add API endpoint to test model capabilities

## Notes

- Default values: `supports_text=True`, `supports_vision=False`
- Both flags can be enabled simultaneously (multimodal models)
- Both flags can be disabled (though not recommended)
- Changes take effect immediately for new agent invocations
- Existing agents using the model will use new capabilities
