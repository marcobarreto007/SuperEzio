content = open('src/agent_server/auth.py', encoding='utf-8').read()

# Replace import logging with structlog
content = content.replace(
    'import hashlib\nimport json\nimport logging',
    'import hashlib\nimport json\nfrom core.config.logging_config import get_logger'
)

# Replace logger = logging.getLogger(__name__)
# Find the logger line (could be in a few places, let's replace all)
content = content.replace(
    'logger = logging.getLogger(__name__)',
    'logger = get_logger(__name__)'
)

# Check if there are other logging.xxx references
import re
if re.search(r'logging\.', content):
    print("WARNING: there are still logging. references")
else:
    print("OK: all logging references removed")

open('src/agent_server/auth.py', 'w', encoding='utf-8').write(content)
print("auth.py converted to structlog")
