# Copyright (c) Alibaba, Inc. and its affiliates.
from typing import TYPE_CHECKING

from transformers.trainer_utils import (EvaluationStrategy, FSDPOption,
                                        HPSearchBackend, HubStrategy,
                                        IntervalStrategy, SchedulerType)

from swift.utils.import_utils import _LazyModule

if TYPE_CHECKING:
    from .arguments import Seq2SeqTrainingArguments, TrainingArguments
    from .dpo_trainers import DPOTrainer
    from .trainers import Seq2SeqTrainer, Trainer
else:
    _import_structure = {
        'arguments': ['Seq2SeqTrainingArguments', 'TrainingArguments'],
        'dpo_trainers': ['DPOTrainer'],
        'trainers': ['Seq2SeqTrainer', 'Trainer'],
    }

    import sys

    sys.modules[__name__] = _LazyModule(
        __name__,
        globals()['__file__'],
        _import_structure,
        module_spec=__spec__,
        extra_objects={},
    )

try:
    # https://github.com/huggingface/transformers/pull/25702
    from transformers.trainer_utils import ShardedDDPOption
except ImportError:
    pass
