import re, sys

content = open('src/agent_server/main.py', encoding='utf-8').read()

# 1. Remove import logging, add uuid
content = content.replace('import logging\n', '')
content = content.replace('import time\n', 'import time\nimport uuid\n')

# 2. Replace logging config import
old_import = "from core.observability import log_queue, metrics  # noqa: E402"
new_import = "from core.config.logging_config import get_logger, bind_trace, unbind_trace  # noqa: E402\nfrom core.observability import log_queue, metrics  # noqa: E402"
content = content.replace(old_import, new_import)
content = content.replace('logger = logging.getLogger(__name__)', 'logger = get_logger(__name__)')

print("Step 1-2 done")
