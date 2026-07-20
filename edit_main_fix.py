content = open('src/agent_server/main.py', encoding='utf-8').read()

# Fix: remove import logging (handling both \n and \r\n)
content = content.replace('import logging\r\n', '')
content = content.replace('import logging\n', '')

# Already has import uuid from previous edit, check
if 'import uuid' not in content:
    content = content.replace('import time\r\n', 'import time\r\nimport uuid\r\n')
    content = content.replace('import time\n', 'import time\nimport uuid\n')

# Add structlog import (after the config imports)
old_seq = 'from core.observability import log_queue, metrics  # noqa: E402'
new_seq = 'from core.config.logging_config import get_logger, bind_trace, unbind_trace  # noqa: E402\r\nfrom core.observability import log_queue, metrics  # noqa: E402'
if old_seq in content:
    content = content.replace(old_seq, new_seq)
    print("Structlog imports added")
else:
    print("WARNING: observability import not found")

# Replace logger = logging.getLogger(__name__)
old_logger = 'logger = logging.getLogger(__name__)'
if old_logger in content:
    content = content.replace(old_logger, 'logger = get_logger(__name__)')
    print("Logger replaced")
else:
    print("WARNING: logger pattern not found")

# Verify no remaining logging references (except in comments/strings)
import re
logging_imports = re.findall(r'^import logging\b', content, re.MULTILINE)
if logging_imports:
    print(f"WARNING: still has {len(logging_imports)} import logging statements")
else:
    print("OK: no import logging remaining")

open('src/agent_server/main.py', 'w', encoding='utf-8').write(content)
print("main.py fixed")
