content = open('src/core/bob_consciousness/autonomic.py', encoding='utf-8').read()

# Replace import logging with structlog
content = content.replace(
    'import logging\nimport threading\nimport time',
    'import threading\nimport time\nfrom core.config.logging_config import get_logger'
)

# Replace logger = logging.getLogger(__name__)
content = content.replace(
    'logger = logging.getLogger(__name__)',
    'logger = get_logger(__name__)'
)

open('src/core/bob_consciousness/autonomic.py', 'w', encoding='utf-8').write(content)
print("autonomic.py converted to structlog")
