# Copyright (c) Alibaba, Inc. and its affiliates.

import os
from dataclasses import dataclass, field
from typing import List, Optional

from transformers.training_args import TrainingArguments as HfTrainingArguments
from transformers.training_args_seq2seq import \
    Seq2SeqTrainingArguments as HfSeq2SeqTrainingArguments
from transformers.utils import is_accelerate_available


@dataclass
class SwiftArgumentsMixin:
    # ckpt only save model
    only_save_model: bool = False
    train_sampler_random: bool = True
    push_hub_strategy: str = field(
        default='push_best',
        metadata={
            'choices':
            {'end', 'push_best', 'push_last', 'checkpoint', 'all_checkpoints'}
        })
    acc_strategy: str = field(
        default='token', metadata={'choices': ['token', 'sentence']})
    additional_saved_files: Optional[List[str]] = None

    def __post_init__(self):
        if is_accelerate_available():
            try:
                from accelerate.utils import check_cuda_p2p_ib_support
                if not check_cuda_p2p_ib_support():
                    os.environ['NCCL_P2P_DISABLE'] = '1'
                    os.environ['NCCL_IB_DISABLE'] = '1'
            except ImportError:
                pass
        if self.additional_saved_files is None:
            self.additional_saved_files = []
        super().__post_init__()


@dataclass
class TrainingArguments(SwiftArgumentsMixin, HfTrainingArguments):
    pass


@dataclass
class Seq2SeqTrainingArguments(SwiftArgumentsMixin,
                               HfSeq2SeqTrainingArguments):
    pass
