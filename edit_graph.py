content = open('src/core/pipeline/graph.py', encoding='utf-8').read()

# Replace import logging with structlog
content = content.replace(
    'import asyncio\nimport logging\nimport os\nimport uuid\nfrom typing import Any, AsyncGenerator, Generator',
    'import asyncio\nimport os\nimport uuid\nfrom typing import Any, AsyncGenerator, Generator\nfrom core.config.logging_config import get_logger'
)

# Replace logger = logging.getLogger(__name__)
content = content.replace(
    'logger = logging.getLogger(__name__)',
    'logger = get_logger(__name__)'
)

open('src/core/pipeline/graph.py', 'w', encoding='utf-8').write(content)
print("graph.py converted to structlog")
