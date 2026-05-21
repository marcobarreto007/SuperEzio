"""
Wrapper: apply PEFT WeightConverter monkey-patch, then run merge_qwen36_lora.py.

The PEFT/transformers distriuted_operation version mismatch causes:
  TypeError: WeightConverter.__init__() got an unexpected keyword argument 'distriuted_operation'
This patches WeightConverter to accept (and ignore) the extra kwarg
before loading PEFT adapters.
"""

import sys
import runpy

# Patch BEFORE anything imports PEFT internals
from transformers.core_model_loading import WeightConverter

_orig_wc_init = WeightConverter.__init__


def _patched_wc_init(self, source_patterns, target_patterns, operations, **kwargs):
    _orig_wc_init(self, source_patterns, target_patterns, operations)


WeightConverter.__init__ = _patched_wc_init

# Forward all args to the real merge script
sys.argv = ["merge_qwen36_lora"] + sys.argv[1:]
runpy.run_path("scripts/merge_qwen36_lora.py", run_name="__main__")
