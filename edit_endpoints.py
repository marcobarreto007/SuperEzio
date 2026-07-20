content = open('src/agent_server/endpoints.py', encoding='utf-8').read()

# Replace import logging with structlog
content = content.replace(
    'import logging\nimport os\nimport re\nimport secrets\nimport time',
    'import os\nimport re\nimport secrets\nimport time\nfrom core.config.logging_config import get_logger'
)

# Replace logger = logging.getLogger(__name__)
content = content.replace(
    'logger = logging.getLogger(__name__)',
    'logger = get_logger(__name__)'
)

open('src/agent_server/endpoints.py', 'w', encoding='utf-8').write(content)
print("endpoints.py converted to structlog")
