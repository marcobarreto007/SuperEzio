content = open('src/core/bob_consciousness/body.py', encoding='utf-8').read()

# Replace import logging with structlog
content = content.replace(
    'import json\nimport logging\nimport socket\nimport sqlite3\nimport sys\nimport time',
    'import json\nimport socket\nimport sqlite3\nimport sys\nimport time\nfrom core.config.logging_config import get_logger'
)

# Replace logger = logging.getLogger(__name__)
content = content.replace(
    'logger = logging.getLogger(__name__)',
    'logger = get_logger(__name__)'
)

open('src/core/bob_consciousness/body.py', 'w', encoding='utf-8').write(content)
print("body.py converted to structlog")
