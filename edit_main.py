import re
content = open("src/agent_server/main.py", encoding="utf-8").read()
# Remove import logging, add import uuid
content = content.replace("import logging
", "")
content = content.replace("import time
", "import time
import uuid
")
print("Step 1 done: imports")
