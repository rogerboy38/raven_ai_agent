"""
AI Agent Settings DocType Fields Update

Add these fields to your AI Agent Settings DocType in ERPNext:
1. Go to DocType List > AI Agent Settings
2. Add these fields in the Fields section
"""

NEW_FIELDS = [
    # Provider Selection
    {
        "fieldname": "ai_provider_section",
        "fieldtype": "Section Break",
        "label": "AI Provider Configuration"
    },
    {
        "fieldname": "default_provider",
        "fieldtype": "Select",
        "label": "Default AI Provider",
        "options": "OpenAI\nDeepSeek\nClaude\nMiniMax\nOllama",
        "default": "OpenAI",
        "reqd": 1
    },
    {
        "fieldname": "column_break_provider",
        "fieldtype": "Column Break"
    },
    {
        "fieldname": "fallback_provider",
        "fieldtype": "Select",
        "label": "Fallback Provider",
        "options": "\nOpenAI\nDeepSeek\nClaude\nMiniMax\nOllama",
        "description": "Used when primary provider fails"
    },
    
    # OpenAI Section (existing, keep)
    {
        "fieldname": "openai_section",
        "fieldtype": "Section Break",
        "label": "OpenAI Settings",
        "depends_on": "eval:doc.default_provider=='OpenAI' || doc.fallback_provider=='OpenAI'"
    },
    {
        "fieldname": "openai_api_key",
        "fieldtype": "Password",
        "label": "OpenAI API Key"
    },
    {
        "fieldname": "model",
        "fieldtype": "Select",
        "label": "OpenAI Model",
        "options": "gpt-4o\ngpt-4o-mini\ngpt-4-turbo\ngpt-3.5-turbo",
        "default": "gpt-4o-mini"
    },
    
    # DeepSeek Section (NEW)
    {
        "fieldname": "deepseek_section",
        "fieldtype": "Section Break",
        "label": "DeepSeek Settings",
        "depends_on": "eval:doc.default_provider=='DeepSeek' || doc.fallback_provider=='DeepSeek'"
    },
    {
        "fieldname": "deepseek_api_key",
        "fieldtype": "Password",
        "label": "DeepSeek API Key",
        "description": "Get from https://platform.deepseek.com/"
    },
    {
        "fieldname": "deepseek_model",
        "fieldtype": "Select",
        "label": "DeepSeek Model",
        "options": "deepseek-chat\ndeepseek-reasoner",
        "default": "deepseek-chat",
        "description": "deepseek-chat (V3) for general use, deepseek-reasoner (R1) for complex reasoning"
    },
    {
        "fieldname": "column_break_deepseek",
        "fieldtype": "Column Break"
    },
    {
        "fieldname": "deepseek_use_reasoning",
        "fieldtype": "Check",
        "label": "Use Reasoning Mode",
        "description": "Enable chain-of-thought reasoning for complex queries (slower but more accurate)"
    },
    
    # Claude Section (for future)
    {
        "fieldname": "claude_section",
        "fieldtype": "Section Break",
        "label": "Claude Settings",
        "depends_on": "eval:doc.default_provider=='Claude' || doc.fallback_provider=='Claude'"
    },
    {
        "fieldname": "claude_api_key",
        "fieldtype": "Password",
        "label": "Anthropic API Key"
    },
    {
        "fieldname": "claude_model",
        "fieldtype": "Select",
        "label": "Claude Model",
        "options": "claude-3-5-sonnet-20241022\nclaude-3-opus-20240229\nclaude-3-haiku-20240307",
        "default": "claude-3-5-sonnet-20241022"
    },
    
    # MiniMax Section (for future)
    {
        "fieldname": "minimax_section",
        "fieldtype": "Section Break",
        "label": "MiniMax Settings",
        "depends_on": "eval:doc.default_provider=='MiniMax' || doc.fallback_provider=='MiniMax'"
    },
    {
        "fieldname": "minimax_api_key",
        "fieldtype": "Password",
        "label": "MiniMax API Key"
    },
    {
        "fieldname": "minimax_group_id",
        "fieldtype": "Data",
        "label": "MiniMax Group ID"
    },
    
    # Ollama Section (for future - local models)
    {
        "fieldname": "ollama_section",
        "fieldtype": "Section Break",
        "label": "Ollama Settings (Local)",
        "depends_on": "eval:doc.default_provider=='Ollama' || doc.fallback_provider=='Ollama'"
    },
    {
        "fieldname": "ollama_base_url",
        "fieldtype": "Data",
        "label": "Ollama Base URL",
        "default": "http://localhost:11434"
    },
    {
        "fieldname": "ollama_model",
        "fieldtype": "Data",
        "label": "Ollama Model",
        "default": "llama3.1:8b",
        "description": "e.g., llama3.1:8b, mistral, codellama"
    }
]

# SQL to add DeepSeek fields (run in ERPNext console if needed)
SQL_MIGRATION = """
-- Add DeepSeek fields to AI Agent Settings
ALTER TABLE `tabAI Agent Settings` 
ADD COLUMN IF NOT EXISTS `default_provider` VARCHAR(140) DEFAULT 'OpenAI',
ADD COLUMN IF NOT EXISTS `fallback_provider` VARCHAR(140),
ADD COLUMN IF NOT EXISTS `deepseek_api_key` TEXT,
ADD COLUMN IF NOT EXISTS `deepseek_model` VARCHAR(140) DEFAULT 'deepseek-chat',
ADD COLUMN IF NOT EXISTS `deepseek_use_reasoning` INT DEFAULT 0;
"""
